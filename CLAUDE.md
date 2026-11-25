# CLAUDE.md: cad2ascope

`cad2ascope` turns an Onshape robot assembly into an AdvantageScope robot asset with articulated components, plus generated Java that computes component poses and camera transforms. It is built for FRC Team 1076 Pi Hi Samurai and published publicly so other teams can use it.

## Read first, in this order

1. `docs/PLAN.md`: the full plan. §6 (converter), §7 (generated Java), and §11 (phases) are the parts you implement.
2. `docs/DECISIONS.md`: what is decided and what is still open.
3. `private/TEAM-CONTEXT.md`: facts about the team's robots, code, Onshape, and machines.
4. `docs/PHASE0-CHECKLIST.md`: your first task.
5. `spec/`: the team config example and JSON schema, and a summary of AdvantageScope's asset format.

## How we work

- Work one phase at a time, in the order in PLAN §11. Each phase is a branch (`phase-0-spike`, `phase-1-core`, and so on) and ends in a pull request. Then **stop and wait for Bill's review**. Do not start the next phase on your own.
- When a change touches only a few files, show each changed file to Bill one by one before producing a bundle or a large diff.
- When something in the plan turns out wrong (very likely after Phase 0), say so, propose the change, and update `docs/PLAN.md` in the same pull request. Do not quietly work around the plan.
- Open decisions in `docs/DECISIONS.md` are for their owners. If one blocks you, ask; do not decide it.

## Hard rules

- Never modify the team's original Onshape documents. Work only on copies Bill provides. The API key is read-only; keep it that way.
- Never commit, print, or log API keys. Read them from `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY`.
- This repo is public. Never commit team Onshape document URLs, document IDs, or anything else from `private/`. The `private/` folder is gitignored; keep it that way.
- Do not invent Onshape API parameters or AdvantageScope behavior. Verify against the API Explorer, real exports, or the AdvantageScope source, and record where you confirmed it.
- Nothing in the tool may need admin rights to install. Students run it from GitHub Actions or with `uv` on team laptops.

## Stack and layout

- Python 3.12, managed with `uv`. Dependencies pinned in `uv.lock`.
- Libraries: numpy, scipy, trimesh, fast-simplification, pyyaml, jsonschema, requests, jinja2. Tests with pytest. Lint and format with ruff.
- License: BSD 3-Clause, copyright Pioneer Robotics: PiHi Samurai, FRC Team 1076, matching the team's robot code.
- Suggested package layout under `src/cad2ascope/` (change it if a better split appears):

| Module | Responsibility |
| --- | --- |
| `cli.py` | Commands: `inspect`, `init`, `fetch`, `build`, `codegen`, `run`, `render` |
| `config.py` | Load and validate `cad/advantagescope.yaml` against `spec/advantagescope.schema.json` |
| `urdf.py` | Parse URDF, build and check the tree (one root, no link with two parents) |
| `transforms.py` | 4x4 math, AdvantageScope rotation sequences, FK at q = 0 |
| `grouping.py` | Articulated vs frozen joints, link groups, stable component order |
| `meshes.py` | Load, place, filter, merge, decimate, write `.glb` |
| `cameras.py` | `cam_` and `frame_` frames, PhotonVision calibration parsing, FOV |
| `ascope.py` | Write `config.json` and `manifest.json` |
| `codegen/` | Jinja templates for `RobotModel.java` and `RobotModelTest.java` |
| `onshape.py` | API client: async translation, polling with backoff, cache by version ID, call counter |
| `report.py` | `report.md` for the pull request body, including camera transform changes |

## Conventions that matter

- Robot frame is WPILib's: +X front, +Y left, +Z up, origin at frame center on the floor. All output geometry is in robot frame, so the robot-level `rotations` is `[]` and `position` is `[0, 0, 0]`.
- Component order is depth-first from the URDF root with children visited in joint-name order. It must be stable across runs.
- A joint's ratio is relative to its parent link in the URDF tree (PLAN §6.5).
- Units: meters and radians internally. Degrees appear only where AdvantageScope's `config.json` wants them.
- Every error message names the mate, part, or link, says what is wrong, and says what to change in Onshape, in words a ninth-grade CAD student understands. Errors exit non-zero; warnings exit zero.

## Testing

- `uv run pytest` must pass on every pull request.
- `tests/fixtures/make_fixtures.py` builds synthetic URDF robots with independently computed `expected.json` (component order, T0, zeroed, cameras, frames, frozen joints). Treat `expected.json` as the oracle. If Phase 0 shows Onshape represents frames differently, update the generator and regenerate rather than editing outputs by hand.
- Add golden files for `config.json` and `RobotModel.java` per fixture once Phase 1 and Phase 3 produce them.
- The transform round-trip test must reproduce AdvantageScope's own math, as confirmed in Phase 0, not an assumed version of it.

## Definition of done for a phase

1. The exit criterion in PLAN §11 is met and shown (test output, screenshots, or numbers).
2. Tests pass and lint is clean.
3. `docs/PLAN.md` and `docs/DECISIONS.md` reflect anything learned.
4. The pull request description says what changed, what was verified and how, and what Bill needs to decide.
