# P1. Season setup

**Who:** Design leads with a programmer. **When:** once per robot, early in the season. **Time:** about 1 hour.

This teaches the main assembly a few habits so every later update is one click. Do it in the main assembly the whole team uses; nothing here changes how the robot looks in the normal design view.

## A. In Onshape (Design leads)

1. **Export configuration.** Add a configuration input named `Export` with the values `Full` and `AdvantageScope`. In `AdvantageScope`, **suppress** (do not just hide) game pieces, field elements, wiring, chain, belts, and cosmetic parts. Hidden parts still get exported.
2. **Robot origin.** On the drivetrain, add a mate connector named `ascope_origin` at the center of the frame perimeter, on the floor plane (bottom of the wheels), with +X toward the robot front and +Z up.
3. **One Fixed part.** Only one part on the drivetrain may be Fixed. Every other part must be mated to something; Fastened is fine.
4. **Moving mates.** For each mechanism that should move in AdvantageScope, use one **Revolute** or **Slider** mate (not Planar, Cylindrical, Parallel, or Ball). Name it `j_` plus a lowercase name with underscores, like `j_elevator_stage1`, unique in the whole assembly. Give it mate limits.
5. **No loops.** If a moving mechanism is a closed loop (a four-bar), fasten all but one of its joints in the `AdvantageScope` configuration.
6. **Linked stages.** Where one motor drives several stages, link the stage Sliders with an Onshape linear relation.
7. **Cameras and measured points.** At each camera's lens center, add a mate connector `cam_` plus its PhotonVision name (+X out of the lens, +Z up). At points the code measures from, add `frame_` plus a name, like `frame_turret_pivot`.
8. **Zero pose and Version.** Move every `j_` mate to the position the robot code calls zero. Save it as a Named Position `ascope_zero`. Create a Version.

## B. On a team laptop (programmer)

Needs [uv](https://docs.astral.sh/uv/) (no admin rights) and the robot repo.

1. In Onshape, with the `AdvantageScope` configuration selected, right-click the assembly tab, choose **Export**, pick **URDF**, geometry **GLTF**, resolution **Medium**, leave "Export rigid subassemblies as a single link" **off**, and download the zip.
2. List what the export contains:
   ```
   uvx --from git+https://github.com/FRC1076/cad2ascope cad2ascope inspect export.zip
   ```
   Every `j_` mate should show as "MOVES". The Notes at the end flag grounded or unmated parts and cut loops; fix those in Onshape (P5).
3. Write a starter config:
   ```
   uvx --from git+https://github.com/FRC1076/cad2ascope cad2ascope init export.zip --name "1076 2027"
   ```
   It writes `cad/advantagescope.yaml` with one signal per `j_` mate.
4. Edit `cad/advantagescope.yaml` with the software lead: signal names that match the code, `ratio` (relative to the part it rides on), `direction: -1` where CAD and code disagree, and `zero_offset_deg` or `zero_offset_m` if needed. Paste the assembly URL into `robot.onshape_url` and set `robot.configuration: "Export=AdvantageScope"`.
5. Build once locally to check: `uvx --from git+https://github.com/FRC1076/cad2ascope cad2ascope run --zip export.zip`. It writes the model, `RobotModel.java`, and, the first time only, `RobotVisualizer.java` and `SweepRobotModel.java`.
6. Wire `RobotVisualizer` into `RobotContainer` and add `visualizer.set(Signal.X, position)` in each subsystem's `periodic()`. Run `./gradlew test`.
7. **Repo settings (a mentor, once):**
   - Copy `update-robot-model.yml` into `.github/workflows/`.
   - Add the repository secrets `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY` (read-only key) and the variable `ONSHAPE_BASE_URL`.
   - Under Settings > Actions > General, allow read and write permissions and allow Actions to create pull requests.
   - Add an empty `cad/drops/.gitkeep`.
8. Commit everything, then do [P2](P2-update-model.md) once to confirm the workflow works.
