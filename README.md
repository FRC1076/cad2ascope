# cad2ascope handoff package

Starting materials for building `cad2ascope`, the Onshape to AdvantageScope pipeline for FRC Team 1076 Pi Hi Samurai. Prepared 2026-11-25 from the implementation plan doc.

## How to start

1. Install Claude Code on the Mac: `curl -fsSL https://claude.ai/install.sh | bash`, then open a new terminal.
2. Run the standalone copy of `setup-mac.sh` (it is also in this zip under `scripts/`): `bash setup-mac.sh`. It installs uv, Python 3.12, and the GitHub CLI without prompts, checks everything else, and lists what still needs a person (Xcode tools, WPILib 2026 with AdvantageScope, `gh auth login`). Repo checks show SKIP until the repo exists. Re-run until every other line says OK.
3. Bill, in Terminal (not through Claude Code): `bash setup-mac.sh --store-keys` to put the read-only Onshape key pair in the macOS Keychain.
4. Create the public GitHub repo `FRC1076/cad2ascope` (empty, no README), clone it, and unzip this package into the clone, so `CLAUDE.md` sits at the repo root.
5. From the repo root, run `scripts/setup-mac.sh --check` once more. The repo lines must say OK: `private/` is gitignored and untracked. `private/TEAM-CONTEXT.md` holds the team's Onshape document links and must never be pushed to the public repo.
6. In the terminal where you will work: `source scripts/onshape-env.sh`, then `claude` from the repo root, and paste the prompt from `prompts/KICKOFF.md`.
7. Before section A of Phase 0, Bill shares a copy of the 2026 robot document with the key owner's account.

## What's here

| Path | What it is | Goes in the public repo? |
| --- | --- | --- |
| `CLAUDE.md` | Standing instructions for Claude Code: rules, layout, conventions, definition of done | Yes |
| `README.md` | This file. Replace it with a user-facing README in Phase 6 | Yes, rewritten later |
| `docs/PLAN.md` | Full implementation plan, snapshot of the living plan doc | Yes |
| `docs/DECISIONS.md` | Decided and open decisions with owners | Yes |
| `docs/PHASE0-CHECKLIST.md` | The verification spike, question by question | Yes |
| `private/TEAM-CONTEXT.md` | Team facts: Onshape links, robot code details, camera baseline values | **No** (gitignored) |
| `spec/advantagescope.example.yaml` | Example team config file for a robot repo | Yes |
| `spec/advantagescope.schema.json` | JSON Schema for that config (the example validates against it) | Yes |
| `spec/ADVANTAGESCOPE-FORMAT.md` | Summary of AdvantageScope's robot asset format, with open points for Phase 0 | Yes |
| `templates/robot-repo/` | Files that go into each robot repo: the GitHub Actions workflow (Phase 5, runs `cad2ascope ci`) and the `updateRobotModel` Gradle task. (`RobotVisualizer.java` moved into the package in Phase 3; `cad2ascope codegen` writes it.) | Yes, as templates |
| `tests/fixtures/` | Seven synthetic URDF robots (zip and unpacked), each with a team config and either `expected.json` (an independent oracle) or `expected_error.txt`, plus `make_fixtures.py` to regenerate them | Yes |
| `prompts/KICKOFF.md` | The first prompt for Claude Code | Yes |
| `scripts/setup-mac.sh` | Mac setup and check script; `--store-keys` mode for Bill only | Yes |
| `scripts/onshape-env.sh` | Loads the Onshape keys from the Keychain into one terminal | Yes |
| `LICENSE` | BSD 3-Clause, copyright Pioneer Robotics: PiHi Samurai, FRC Team 1076, same text as the 2026 robot code | Yes |
| `.gitignore` | Keeps `private/`, caches, and secrets out of git | Yes |

## Fixtures at a glance

| Fixture | Tests |
| --- | --- |
| `single_revolute` | One arm on a revolute joint, origin frame deliberately offset and rotated |
| `prismatic` | One slider |
| `nested_chain` | Turret, hood on turret, a camera on each, a measured frame (like 2026) |
| `coupled` | Two-stage cascade with a mimic relation and a wrist on the carriage (like 2025) |
| `frozen` | An unlisted movable joint that must merge into the base |
| `invalid_two_parents` | A closed linkage; must fail and name the link |
| `missing_origin` | No `ascope_origin`; must fail with a fix-it message |

One assumption is baked into the fixtures: Onshape mate connectors arrive as dummy links on fixed joints. Phase 0 checks this against a real export, and the generator gets updated if it is wrong.

## Keeping the plan in sync

The living plan is the Claude Doc "Onshape to AdvantageScope Pipeline: Implementation Plan". `docs/PLAN.md` is a snapshot of it. When Claude Code changes the plan in a pull request, carry the change back to the doc, or retire the doc and treat `docs/PLAN.md` as the source from then on. [CONFIRM which]
