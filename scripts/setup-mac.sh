#!/bin/bash
# setup-mac.sh: prepare a Mac for cad2ascope development (Phases 0 to 3, run locally).
#
#   scripts/setup-mac.sh               Install what can be installed without prompts, check the
#                                      rest, and print a summary. Safe for Claude Code to run.
#                                      Re-run any time; it skips what is already done.
#   scripts/setup-mac.sh --check       Check only. Installs nothing.
#   scripts/setup-mac.sh --store-keys  Save the Onshape API key pair in the macOS Keychain.
#                                      Interactive. Bill runs this himself in Terminal, never
#                                      Claude Code. It refuses to run without a terminal.
#
# Installs without prompts (no sudo, everything under your home folder):
#   uv (Python manager), Python 3.12 through uv, GitHub CLI (Homebrew if present, else ~/.local/bin)
# Checks and tells you what to do for:
#   Xcode command line tools, Claude Code, WPILib 2026, AdvantageScope, gh sign-in,
#   Onshape keys in the Keychain, and that private/ is gitignored in this repo.
#
# Exit code: 0 when everything is ready, 1 when something still needs a person.
# Never prints, logs, or writes API key values.

set -u

MODE="install"
case "${1:-}" in
  "") ;;
  --check) MODE="check" ;;
  --store-keys) MODE="store-keys" ;;
  -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
  *) echo "Unknown option: $1 (try --help)"; exit 2 ;;
esac

USER="${USER:-$(id -un)}"
KEY_NAMES="ONSHAPE_ACCESS_KEY ONSHAPE_SECRET_KEY"
WPILIB_YEAR="2026"
LOCAL_BIN="$HOME/.local/bin"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This script is for macOS. On other systems, follow docs/PLAN.md §8 by hand."
  exit 2
fi

# ---------------------------------------------------------------------------
# --store-keys: interactive, for Bill only
# ---------------------------------------------------------------------------
if [ "$MODE" = "store-keys" ]; then
  if [ ! -t 0 ] || [ ! -t 1 ]; then
    echo "--store-keys must be run by a person in Terminal, not by Claude Code or a script."
    exit 2
  fi
  echo "Saving the Onshape API key pair (read-only key) to your login Keychain."
  echo "Typing is hidden. Press Return on an empty line to keep an existing value."
  for name in $KEY_NAMES; do
    printf "%s: " "$name"
    IFS= read -rs value
    echo
    if [ -z "$value" ]; then
      echo "  kept existing value (if any)"
      continue
    fi
    # -U updates the item if it already exists.
    if security add-generic-password -U -a "$USER" -s "$name" -w "$value" >/dev/null 2>&1; then
      echo "  saved"
    else
      echo "  could not save $name to the Keychain"
    fi
    value=""
  done
  unset value
  echo "Done. Load the keys into a terminal with:  source scripts/onshape-env.sh"
  exit 0
fi

# ---------------------------------------------------------------------------
# Helpers for install and check modes
# ---------------------------------------------------------------------------
REPORT=""
NEEDS_PERSON=0

ok()     { REPORT="${REPORT}  OK      $1\n"; }
action() { REPORT="${REPORT}  ACTION  $1\n"; NEEDS_PERSON=1; }
info()   { echo "-> $1"; }

ensure_local_bin_on_path() {
  case ":$PATH:" in
    *":$LOCAL_BIN:"*) ;;
    *) export PATH="$LOCAL_BIN:$PATH" ;;
  esac
}
ensure_local_bin_on_path

# ---------------------------------------------------------------------------
# 1. Xcode command line tools (git)
# ---------------------------------------------------------------------------
if xcode-select -p >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
  ok "Xcode command line tools and git ($(git --version | awk '{print $3}'))"
else
  if [ "$MODE" = "install" ]; then
    info "Opening the Xcode command line tools installer (a macOS dialog)."
    xcode-select --install >/dev/null 2>&1
  fi
  action "Xcode command line tools: finish the macOS installer dialog (or run 'xcode-select --install'), then re-run this script"
fi

# ---------------------------------------------------------------------------
# 2. Claude Code (cannot install itself from inside a session)
# ---------------------------------------------------------------------------
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code ($(claude --version 2>/dev/null | head -1))"
else
  action "Claude Code: run 'curl -fsSL https://claude.ai/install.sh | bash', open a new terminal, check 'claude --version'"
fi

# ---------------------------------------------------------------------------
# 3. uv and Python 3.12
# ---------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1 && [ "$MODE" = "install" ]; then
  info "Installing uv into $LOCAL_BIN"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  ensure_local_bin_on_path
fi
if command -v uv >/dev/null 2>&1; then
  ok "uv ($(uv --version | awk '{print $2}'))"
  if uv python find 3.12 >/dev/null 2>&1; then
    ok "Python 3.12 (managed by uv)"
  elif [ "$MODE" = "install" ]; then
    info "Installing Python 3.12 with uv"
    if uv python install 3.12 >/dev/null 2>&1; then
      ok "Python 3.12 (installed by uv)"
    else
      action "Python 3.12: 'uv python install 3.12' failed; run it in Terminal to see why"
    fi
  else
    action "Python 3.12: run 'uv python install 3.12'"
  fi
else
  action "uv: run 'curl -LsSf https://astral.sh/uv/install.sh | sh', then open a new terminal"
fi

# ---------------------------------------------------------------------------
# 4. GitHub CLI and sign-in
# ---------------------------------------------------------------------------
install_gh_without_brew() {
  local arch_tag tag ver url tmp
  tag=$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest 2>/dev/null \
        | sed -n 's/.*"tag_name": *"\(v[^"]*\)".*/\1/p' | head -1)
  [ -n "$tag" ] || return 1
  ver="${tag#v}"
  arch_tag="universal"
  url="https://github.com/cli/cli/releases/download/${tag}/gh_${ver}_macOS_${arch_tag}.zip"
  tmp=$(mktemp -d)
  curl -fsSL "$url" -o "$tmp/gh.zip" || { rm -rf "$tmp"; return 1; }
  unzip -q "$tmp/gh.zip" -d "$tmp" || { rm -rf "$tmp"; return 1; }
  mkdir -p "$LOCAL_BIN"
  cp "$tmp"/gh_*/bin/gh "$LOCAL_BIN/gh" && chmod +x "$LOCAL_BIN/gh"
  rm -rf "$tmp"
  command -v gh >/dev/null 2>&1
}

if ! command -v gh >/dev/null 2>&1 && [ "$MODE" = "install" ]; then
  if command -v brew >/dev/null 2>&1; then
    info "Installing GitHub CLI with Homebrew"
    brew install gh >/dev/null 2>&1
  else
    info "Installing GitHub CLI into $LOCAL_BIN"
    install_gh_without_brew
  fi
fi
if command -v gh >/dev/null 2>&1; then
  ok "GitHub CLI ($(gh --version | head -1 | awk '{print $3}'))"
  if gh auth status >/dev/null 2>&1; then
    ok "GitHub CLI signed in"
  else
    action "GitHub sign-in: run 'gh auth login' yourself in Terminal (it opens a browser)"
  fi
else
  action "GitHub CLI: install from https://cli.github.com, then run 'gh auth login'"
fi

# ---------------------------------------------------------------------------
# 5. WPILib 2026 (JDK + Gradle for the 2026 robot repo) and AdvantageScope
# ---------------------------------------------------------------------------
WPILIB_DIR="$HOME/wpilib/$WPILIB_YEAR"
if [ -d "$WPILIB_DIR/jdk" ]; then
  ok "WPILib $WPILIB_YEAR ($WPILIB_DIR)"
else
  action "WPILib $WPILIB_YEAR: download the macOS installer from the WPILib GitHub releases and run it (GUI installer)"
fi

ascope=""
for candidate in /Applications/AdvantageScope*.app "$HOME/Applications"/AdvantageScope*.app; do
  [ -d "$candidate" ] && ascope="$candidate" && break
done
if [ -z "$ascope" ] && [ -d "$WPILIB_DIR" ]; then
  ascope=$(find "$WPILIB_DIR" -maxdepth 3 -iname "AdvantageScope*.app" -print -quit 2>/dev/null)
fi
if [ -n "$ascope" ]; then
  ok "AdvantageScope ($ascope)"
else
  action "AdvantageScope: comes with the WPILib installer, or download it from its GitHub releases"
fi

# ---------------------------------------------------------------------------
# 6. Onshape API keys in the Keychain (existence only; values never read here)
# ---------------------------------------------------------------------------
missing_keys=""
for name in $KEY_NAMES; do
  if ! security find-generic-password -a "$USER" -s "$name" >/dev/null 2>&1; then
    missing_keys="$missing_keys $name"
  fi
done
if [ -z "$missing_keys" ]; then
  ok "Onshape key pair is in the Keychain"
else
  action "Onshape keys missing from the Keychain:${missing_keys}. Bill runs 'scripts/setup-mac.sh --store-keys' in Terminal"
fi

# ---------------------------------------------------------------------------
# 7. This repo: private/ must never be committed
# ---------------------------------------------------------------------------
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  repo_root=$(git rev-parse --show-toplevel)
  if [ -n "$(git -C "$repo_root" ls-files private 2>/dev/null)" ]; then
    action "private/ is tracked by git. Run 'git rm -r --cached private' and commit BEFORE pushing"
  elif git -C "$repo_root" check-ignore -q "private/TEAM-CONTEXT.md"; then
    ok "private/ is gitignored and untracked"
  else
    action "private/ is not ignored. Add 'private/' to .gitignore before the first commit"
  fi
  if [ -f "$repo_root/private/TEAM-CONTEXT.md" ]; then
    ok "private/TEAM-CONTEXT.md is present"
  else
    action "private/TEAM-CONTEXT.md is missing. Copy it from the handoff zip"
  fi
else
  action "Not inside a git repo. Clone FRC1076/cad2ascope, unzip the handoff into it, and re-run from there"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "cad2ascope Mac setup ($MODE mode)"
printf "%b" "$REPORT"
echo
if [ "$NEEDS_PERSON" -eq 0 ]; then
  echo "Ready. Load the keys with 'source scripts/onshape-env.sh', then start 'claude' from the repo root."
  exit 0
else
  echo "Some items need a person (see ACTION lines). Re-run this script after doing them."
  exit 1
fi
