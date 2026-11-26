# Phase 5 notes: CI in the robot repo

Three pieces make PLAN §9 P2 ("Update the model", about two minutes of clicks) work from a browser:

1. **`cad2ascope ci`** (`src/cad2ascope/ci.py`): the whole job in one tested command.
   - **Source:** exactly one zip in `cad/drops/` (no key needed); otherwise the Onshape API (`robot.version`, `--version NAME`, or `--workspace`). Two zips at once is an error that says to drop one at a time.
   - **Outputs:** builds `assets/advantagescope/Robot_*`, generates `RobotModel.java` and its test, and renders preview PNGs to `cad/previews/`.
   - **Report and cleanup:** writes the pull request body to `build/cad2ascope/report.md` (report plus previews), then deletes the processed zip.
   - **Step outputs** in `$GITHUB_OUTPUT`: `mode`, `title`, `report`, `breaking` (signals added or removed), and `zip_removed`.
2. **`cad2ascope render`** (`src/cad2ascope/render.py`): preview PNGs at zero and at each signal's lowest and highest limit.
   - A small numpy z-buffer rasterizer, with no GPU, display or extra package. It reads only the built folder and places components exactly the way AdvantageScope does: component pose · zeroed transform, from `config.json`.
   - It also runs the **zero-pose check** (PLAN §10.3 item 2), comparing a render with zero poses published against a render with no poses. Any differing pixel means a component would jump when robot code starts publishing poses. `render` exits 1 in that case.
3. **`templates/robot-repo/.github/workflows/update-robot-model.yml`**, which runs `cad2ascope ci`, `./gradlew test`, and then:
   - a zip dropped on a branch other than the default branch: commits the result back onto that branch, so the student's pull request updates;
   - otherwise (Run workflow button, or a drop on the default branch): opens or updates the pull request `robot-model/update` with the report as its body. Nothing merges automatically.
   - If `./gradlew test` fails, the pull request is still opened or updated, then the job fails, with a specific message when signals changed (PLAN §9 P3).
   - Every action is pinned to a full commit SHA (checkout v7.0.1, setup-uv v10.4.0, setup-java v6.3.0, cache v6.1.0, create-pull-request v8.1.3). Each input the workflow passes was checked against that commit's `action.yml`.
   - Workflow inputs reach the shell only through environment variables, so a Version name cannot inject commands (tested).

## Robot repo setup (once per robot repo)

- Copy the workflow to `.github/workflows/update-robot-model.yml`.
- Repository secrets `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY` (the read-only key); repository variable `ONSHAPE_BASE_URL` = `https://aaps.onshape.com`.
- Settings > Actions > General > Workflow permissions: "Read and write permissions", and "Allow GitHub Actions to create and approve pull requests".
- `cad/advantagescope.yaml`, and an empty `cad/drops/` (a `.gitkeep` file) so students can upload into it from the web UI.
- `!cad/drops/*.zip` at the end of `.gitignore`: WPILib's `.gitignore` has `*.zip`, which blocks committing a drop with git (found in the test repo, 2026-11-25).
- `build/` is already ignored in a WPILib project; the report is written there.

## Verified

- 13 tests in `tests/test_ci.py`:
  - drop route end to end in a temporary robot repo (outputs, zip removed, files, preview links);
  - two drops refused; no URL and no drop explained;
  - API route through the fake Onshape server, including the `breaking` flag when a signal comes back;
  - the `--version` override;
  - render colors and PNG encoding;
  - render kinematics against the code generator;
  - the zero-pose check catching a deliberately wrong `zeroedPosition`;
  - the workflow's pinned actions, its no-interpolation rule, and its `cad2ascope ci` arguments.
- Real 2026 model (reduced, 296 k triangles): one preview in about 12 s, zero-pose check 0 pixels.

## Test repo runs (2026-11-25)

`FRC1076/cad2ascope-test-robot` (private) is a minimal WPILib 2026 project: GradleRIO 2026.2.1, the AdvantageKit and command vendordeps, an empty `Robot`, the workflow copied unchanged, and the synthetic `coupled` fixture as its robot. It has no Onshape secrets. Both drop runs installed cad2ascope from `main` and passed, each in about a minute:
- **Drop on a branch** (`drop-test`): the job built, ran `./gradlew test` (the generated `RobotModelTest` passes), removed the zip, and committed 16 files back onto the branch. As expected, the bot's commit started no further run.
- **Drop on `main`:** `create-pull-request` opened `robot-model/update` with `report.md` as its body and the five preview PNGs on that branch.

Two problems found and fixed in the same pull request as these notes:
- WPILib's `.gitignore` has `*.zip`, so `git add` refuses a dropped export. The setup steps now add `!cad/drops/*.zip`.
- The zero-pose check reported 7,199 differing pixels and told the student to re-check the export pose. The cause was `j_wrist`'s deliberate 10° `zero_offset`. Joints with a zero offset are now checked at their export pose, and the report names them.

## Not verified: Phase 5 exit criterion (PLAN §11, "P2 works from a MacBook browser")

Still open after the test repo runs:
- whether the preview images display in the pull request page with `raw/` links. The first run linked them as `blob/<branch>/cad/previews/...`; those did not display (a `blob/` address is the file's web page, not the image), though each opened when clicked. The workflow now links `raw/<branch>/...`, and test-repo pull request #1's body was edited to match by hand;
- the Onshape route (Run workflow), which needs the secrets, `robot.onshape_url` and a Version;
- the export cache restoring, which only the Onshape route uses;
- a student doing P2 from a MacBook browser (the runs above were pushed with git).

Also note: commits pushed by the workflow's `GITHUB_TOKEN` do not start other workflows, so the robot repo's own build check will not rerun on the bot's commit until someone pushes again. That is GitHub's rule to prevent loops.

## Repo size

Each run commits the model (about 13 to 15 MB for the pilots, Phase 2) and the previews (about 10 to 100 KB each). See DECISIONS #6 (Git LFS).
