# onshape-env.sh: load the Onshape API key pair from the macOS Keychain into this terminal.
#
#   source scripts/onshape-env.sh
#
# Run it in the terminal where you will start Claude Code, right before 'claude'.
# The keys live only in this shell's environment and disappear when the window closes.
# Store them first with: scripts/setup-mac.sh --store-keys
# Never prints key values.

if [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "Use 'source scripts/onshape-env.sh' so the keys reach this shell."
  exit 2
fi
# shellcheck disable=SC2317  # zsh-only branch
case "${ZSH_EVAL_CONTEXT:-}" in
  toplevel) echo "Use 'source scripts/onshape-env.sh' so the keys reach this shell."; return 2 2>/dev/null || exit 2 ;;
esac

_cad2ascope_loaded=""
_cad2ascope_missing=""
for _name in ONSHAPE_ACCESS_KEY ONSHAPE_SECRET_KEY; do
  _value=$(security find-generic-password -a "${USER:-$(id -un)}" -s "$_name" -w 2>/dev/null)
  if [ -n "$_value" ]; then
    export "$_name=$_value"
    _cad2ascope_loaded="$_cad2ascope_loaded $_name"
  else
    _cad2ascope_missing="$_cad2ascope_missing $_name"
  fi
done
unset _value _name

export ONSHAPE_BASE_URL="https://aaps.onshape.com"

if [ -n "$_cad2ascope_missing" ]; then
  echo "Missing from the Keychain:$_cad2ascope_missing. Run: scripts/setup-mac.sh --store-keys"
else
  echo "Loaded$_cad2ascope_loaded and ONSHAPE_BASE_URL into this terminal."
fi
unset _cad2ascope_loaded _cad2ascope_missing
