# CLAUDE.md: cad2ascope

`cad2ascope` turns an Onshape robot assembly into an AdvantageScope robot asset with articulated components, plus generated Java that computes component poses and camera transforms. It is built for FRC Team 1076 Pi Hi Samurai and published publicly so other teams can use it.

## Status

Phases 0 to 6 are merged, plus follow-up checks in pull requests #9 to #12 (as of 2026-11-26); PLAN §11 has each phase's exit status. Everything that could be done without a person is done. Phase 7 (pilots) needs the student's Onshape edits, the Onshape secrets in a robot repo, and team decisions. `docs/HUMAN-CHECKLIST.md` lists those 18 items and where to start.

## Read first, in this order

1. `docs/PLAN.md`: the full plan. Sections marked "As built in Phase N" or "Proposed after Phase 0" record what changed from the original plan.
2. `docs/DECISIONS.md`: what is decided and what is still open.
3. `docs/phase0-findings.md`: what the real Onshape export and AdvantageScope's source actually do. Most design choices rest on it.
4. `docs/HUMAN-CHECKLIST.md`: what is blocked on a person.
5. `private/TEAM-CONTEXT.md`: facts about the team's robots, code, Onshape (including the URLs of the working copies), and machines. Not in git.
6. `spec/`: the config example and JSON schema, the camera baseline example, and a summary of AdvantageScope's asset format.

## How we work

- Work one phase at a time, in the order in PLAN §11. Each phase is a branch (`phase-0-spike`, `phase-1-core`, and so on) and ends in a pull request. Then **stop and wait for Bill's review**. Do not start the next phase on your own.
- When a change touches only a few files, show each changed file to Bill one by one before producing a bundle or a large diff.
- When something in the plan turns out wrong (very likely after Phase 0), say so, propose the change, and update `docs/PLAN.md` in the same pull request. Do not quietly work around the plan.
- Open decisions in `docs/DECISIONS.md` are for their owners. If one blocks you, ask; do not decide it.

## Hard rules

- Never modify the team's original Onshape documents. Work only on copies Bill provides. The API key is read-only; keep it that way.
- Never commit, print, or log API keys. Read them from `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY`.
- This repo is public. Never commit team Onshape document URLs, document IDs, or anything else from `private/`. The `private/` folder is gitignored; keep it that way.
- Do not invent Onshape API parameters or AdvantageScope behavior. Verify against the server's OpenAPI spec (`GET /api/openapi`, which is how A1 was answered), real exports, or the AdvantageScope source, and record where you confirmed it. Check parameter limits too: `getDocumentVersions` rejects `limit` above 20.
- Nothing in the tool may need admin rights to install. Students run it from GitHub Actions or with `uv` on team laptops.

## Stack and layout

- Python 3.12, managed with `uv`. Dependencies pinned in `uv.lock`.
- Libraries: numpy, scipy, trimesh, fast-simplification, pyyaml, jsonschema, requests, jinja2. Tests with pytest. Lint and format with ruff.
- License: BSD 3-Clause, copyright Pioneer Robotics: PiHi Samurai, FRC Team 1076, matching the team's robot code.
- Package layout under `src/cad2ascope/`, as built:

| Module | Responsibility |
| --- | --- |
| `cli.py` | Commands: `inspect`, `init`, `build`, `codegen`, `render`, `ci`, `fetch`, `run` |
| `config.py` | Load and validate `cad/advantagescope.yaml`. A copy of the schema ships in `data/`; a test keeps it equal to `spec/` |
| `export.py` | Read a zip, folder or `.urdf`. **Every assumption about Onshape's export layout lives here**, plus `onshape_notes` (grounded, unmated, cut loops) |
| `urdf.py` | Parse standard URDF and check the tree (one root, no link with two parents) |
| `transforms.py` | 4x4 math and AdvantageScope rotation sequences (fixed axes, list order; Phase 0 B1) |
| `grouping.py` | Articulated vs frozen joints, component groups and order, T0, checks on listed joints, warning summaries |
| `cameras.py` | `cam_` and `frame_` connectors, PhotonVision calibration, the FOV rule (Phase 0 B5) |
| `meshes.py` | Load and place meshes in robot frame; write `.glb` with normals and base-color materials |
| `reduce.py` | Filter parts, weld, per-part triangle cap, merge by color, `NOSIMPLIFY` (Phase 2) |
| `ascope.py` | Write `config.json` and `manifest.json` (numbers rounded to 1e-9) |
| `report.py` | `report.md`: breaking-change line, camera and frame movement, baseline comparison |
| `build.py` | Ties the above together; writes nothing unless every check passes |
| `codegen/` | Jinja templates and context for `RobotModel.java`, its test, `RobotVisualizer`, `SweepRobotModel` |
| `onshape.py` | API client: export, poll with backoff, download, cache by version ID, call counter |
| `render.py` | Numpy rasterizer for preview PNGs and the zero-pose check |
| `ci.py` | The robot-repo workflow's job: drop or API, build, codegen, render, report, `$GITHUB_OUTPUT` |

- `templates/robot-repo/`: the workflow, the Gradle task, and the student procedures (`docs/robot-model/`) that teams copy into robot repos.

## Conventions that matter

- Robot frame is WPILib's: +X front, +Y left, +Z up, origin at frame center on the floor. All output geometry is in robot frame, so the robot-level `rotations` is `[]` and `position` is `[0, 0, 0]`.
- Component order is depth-first from the URDF root with children visited in joint-name order. It must be stable across runs.
- A joint's ratio is relative to its parent link in the URDF tree (PLAN §6.5).
- Units: meters and radians internally. Degrees appear only where AdvantageScope's `config.json` wants them.
- Every error message names the mate, part, or link, says what is wrong, and says what to change in Onshape, in words a ninth-grade CAD student understands. Errors exit non-zero; warnings exit zero. When there are many of one kind (frozen joints, default part names), summarize instead of listing each.
- The P5 troubleshooting page quotes fragments of these messages; `tests/test_docs.py` fails if a quoted fragment no longer appears in the source, so update both together.
- Output must be byte-for-byte repeatable and identical across platforms: generated Java numbers use 12 significant digits, JSON numbers 1e-9.

## Testing

- `uv run pytest` must pass on every pull request. Every test runs from its own temporary folder (`tests/conftest.py`), so nothing a test runs can write into this repo.
- `tests/fixtures/make_fixtures.py` builds synthetic URDF robots with independently computed `expected.json`. Treat `expected.json` as the oracle; if the generator changes, regenerate rather than editing outputs by hand.
- Golden files live in `tests/golden/<fixture>/` (`config.json`, `RobotModel.java`, `RobotModelTest.java`). After an intended change, run with `CAD2ASCOPE_UPDATE_GOLDEN=1` and review the diff before committing.
- `tests/ascope_reference.py` ports AdvantageScope's own placement math; transform tests check against it, not an assumed version.
- Generated Java is compiled with `-Werror` against real WPILib jars and its JUnit test is run (`tests/java_harness.py`). Locally it uses the WPILib installer's Maven folder (`~/wpilib/<year>/maven`); CI downloads the pinned jars with `scripts/fetch-java-deps.py` and sets `CAD2ASCOPE_REQUIRE_JAVA=1` so a missing JDK fails instead of skipping. The same tests also run against WPILib 2027 (`codegen.wpilib: 2027`, JDK 25): set `WPILIB_MAVEN_2027` and `JAVA_HOME_2027` locally, and CI sets `CAD2ASCOPE_REQUIRE_JAVA_2027=1`.
- The Onshape client is tested against a fake server (`tests/test_onshape.py`); never call the real API from tests.

## Definition of done for a phase

1. The exit criterion in PLAN §11 is met and shown (test output, screenshots, or numbers).
2. Tests pass and lint is clean.
3. `docs/PLAN.md` and `docs/DECISIONS.md` reflect anything learned.
4. The pull request description says what changed, what was verified and how, and what Bill needs to decide.
