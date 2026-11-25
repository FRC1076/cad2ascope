# Onshape to AdvantageScope Pipeline: Implementation Plan

FRC Team 1076 Pi Hi Samurai · Pioneer High School, Ann Arbor · 2026-2027
Exported from the plan doc on 2026-11-25. The doc is the living version; this copy is the Claude Code handoff snapshot.

A student should be able to go from "the robot changed in Onshape" to "the new robot moves in AdvantageScope" in one click and about 15 minutes of waiting, with no hand-tuned numbers. This plan covers the CAD conventions, the converter software, the generated robot code, where it runs, and the student procedures. Items marked [CONFIRM] are decisions for Bill or the named owner (see `DECISIONS.md`).

**Contents**

1. §1 Purpose and scope
2. §2 Current manual workflow
3. §3 Pipeline architecture
4. §4 CAD conventions
5. §5 Onshape API access
6. §6 Converter specification
7. §7 Generated Java and robot code integration
8. §8 Where it runs
9. §9 Student procedures
10. §10 Validation and test plan
11. §11 Implementation phases for Claude Code
12. §12 Open decisions

## §1 Purpose and scope

The goal is a repeatable pipeline that turns the main robot assembly in Onshape into an AdvantageScope robot asset with working articulated components, plus the Java code that drives those components from real or simulated mechanism positions.

**In scope.**

- Export from the team's Onshape Enterprise (aaps.onshape.com), driven by the API or by a manual export as a fallback.
- Automatic split of the robot into a base model and one model per moving mechanism, including nested chains (hood on a turret, wrist on an elevator carriage).
- Exact calculation of every `zeroedRotations` and `zeroedPosition` value, so the calibration steps in the AdvantageScope docs go away.
- A generated Java class that computes the `Pose3d[]` component array from joint values.
- Robot-to-camera transforms for PhotonVision and other measured mount points generated from CAD, replacing hand-typed constants (§7.4).
- Mesh size reduction so the model loads fast on team laptops.
- Runs from a browser (GitHub Actions) for students on district MacBooks, and locally on team Windows laptops.
- Student procedures and acceptance tests against the 2025 Reefscape and 2026 Rebuilt robots.

**Out of scope for now.** Physics simulation (MuJoCo, mass and inertia), field models, joystick assets.

**Success criteria.**

1. A new export of the main assembly reaches the robot repo as a pull request with no file editing by the student.
2. With component poses published, every component lines up with the base model in AdvantageScope with no manual adjustment.
3. Changing a CAD part and re-running the pipeline updates the model with no change to robot code, unless a joint was added or removed.
4. The full robot loads in AdvantageScope in under 10 seconds on a team laptop. [CONFIRM target]

## §2 Current manual workflow

The documented process takes a few hours per robot, and most of that time goes to two manual steps that software can do exactly. The AdvantageScope custom assets page (https://docs.advantagescope.org/more-features/custom-assets/) and its Onshape conversion page (https://docs.advantagescope.org/more-features/custom-assets/gltf-convert) describe it this way:

1. Hide every moving mechanism and export the rest of the main assembly to STEP.
2. Export each moving mechanism separately to STEP, in its default position.
3. Convert each STEP file to `.glb` in CAD Assistant, one file at a time, with "merge faces within the same part" turned on.
4. Create a `Robot_<name>` folder with `model.glb`, `model_0.glb`, `model_1.glb` and so on, then hand-write `config.json`.
5. Publish a zeroed robot pose and adjust the robot's `rotations` and `position` by trial and error until it sits at the origin.
6. Publish an array of zeroed component poses and adjust each component's `zeroedRotations` and `zeroedPosition` by trial and error until it sits at the origin, pointed along +X.
7. Write robot code that computes each component's real pose, including the chain math for nested mechanisms.

Steps 5 to 7 are where teams give up. The AdvantageScope docs themselves warn that articulated components are complex and point teams to Mechanism2d instead, which is what the 2025 robot code did (`SuperstructureVisualizer.java`). Every one of those numbers already exists in the CAD as mate positions and axes. The pipeline reads them instead of guessing them.

Two facts from the team repos shape the design. Both robots are Java with AdvantageKit. The 2026 robot has a turret with a hood mounted on it, so the code needs chained transforms, not only independent poses. Neither repo publishes 3D component poses today.

## §3 Pipeline architecture

Onshape's native URDF export already contains the mesh for each moving body and the exact frame of each joint. The pipeline only has to regroup that data into AdvantageScope's format and generate matching code.

```
Onshape main assembly (Export=AdvantageScope config, ascope_origin, j_ mates, Version)
        |                                   |
Onshape API export                   Manual URDF export
(Actions or laptop, read-only key)   (zip dropped in cad/drops/, no key)
        \                                   /
         URDF + glTF meshes          cad/advantagescope.yaml
         (joint frames, axes, limits) (signals, ratios, mesh budget)
                    \                  /
              cad2ascope build + codegen
        (group links, zeroed transforms, decimate)
              /                        \
  Robot_1076_2027/                 RobotModel.java
  model.glb, model_N.glb,          Pose3d[] from joints,
  config.json                      camera transforms, JUnit test
              \                        /
           Pull request, human review
        (report, preview renders, gradlew test)
              /                        \
  AdvantageScope 3D field  <---  Robot code (RobotVisualizer
  (custom assets folder in repo)  logs RobotModel/Measured and /Setpoint)
```

Both export routes produce the same zip, so the converter has one input format. Every change reaches the robot repo as a pull request that a person merges, the same way code changes do. The converter is the only custom software. Onshape, GitHub Actions, and AdvantageScope are used as they ship.

## §4 CAD conventions

The pipeline needs seven habits from the CAD subteam, and most of them are already true because mechanisms move in the main assembly today. Bill and the Design leads own these conventions and add them to the CAD standards.

**C1. One export configuration on the main assembly.** Add an Onshape configuration input named `Export` with values `Full` and `AdvantageScope`. The `AdvantageScope` value suppresses fasteners, wiring, chain, belts, and cosmetic parts, and swaps closed linkages for a single joint (C4). The API export passes this configuration (`Export=AdvantageScope`), so the design view students work in never changes. This one habit removes most mesh weight and most export errors. *[Proposed after Phase 0, for Bill and the Design leads:]* Hidden parts are always exported (the export dialog's "Include hidden instances" cannot be turned off), so the `AdvantageScope` value must **suppress** what it leaves out, including game pieces and field elements.

**C2. A robot origin frame.** Place a mate connector named `ascope_origin` on the drivetrain subassembly at the center of the frame perimeter, on the floor plane (bottom of the wheels), with +X pointing toward the robot front and +Z up. This frame becomes the AdvantageScope robot origin, matching the WPILib robot coordinate system. With it, the robot-level `rotations` and `position` in `config.json` are computed, never guessed. *[Proposed after Phase 0:]* In the export configuration, the drivetrain must be the **only grounded (Fixed) instance**, and every other instance must be mated (Fastened is fine). Onshape's export bolts the grounded instance and any unmated instance straight to the base and ignores their mates, so a grounded turret plate keeps the hood from riding on the turret.

**C3. Named joint mates.** Every mate that should move in AdvantageScope gets a name starting with `j_`, for example `j_elevator_stage1`, `j_elevator_carriage`, `j_wrist`, `j_turret`, `j_hood`, `j_slapdown`. Use Revolute or Slider mates only. *[Proposed after Phase 0:]* Planar, Cylindrical, Parallel and Ball mates export as chains of several joints and cannot be animated; a turret placed with a Planar mate must become a Revolute mate. Mate names arrive lowercased with punctuation turned into `_`, and repeats get `_1`, `_2` suffixes, so write `j_` names in lowercase with underscores and keep them unique across the whole assembly. A Revolute mate without limits exports as `continuous`. Mates without the prefix are treated as frozen and merged into their parent at their current position. Set mate limits on every `j_` mate. The limits drive the sweep test in §10.

**C4. No loops in exported motion.** URDF cannot describe a four-bar or any closed linkage. *[Learned in Phase 0:]* Onshape does not refuse loops; it cuts each one and names the cut `*_loop_closure`, so an unhandled loop shows up as a mechanism that comes apart when it moves. In the `AdvantageScope` configuration, fasten all but one joint of a closed linkage, or replace it with an equivalent single revolute. Flag these in a short note on the mate so the next student knows why.

**C5. Coupled stages use relations.** A cascade or continuous elevator has several stages driven by one motor. Connect stage sliders with an Onshape linear relation (for example, carriage travel = 2 × stage 1 travel). The converter maps relations to followers (§6.5). If the exporter does not carry relations, the ratio goes in the pipeline config instead.

**C6. Export in the code-zero pose.** Before creating the Onshape Version used for export, put each `j_` mate at the position the robot code calls zero (elevator down, wrist at its zero angle). Save that as a Named Position called `ascope_zero`. The converter treats the export pose as zero for every joint. Any mismatch is fixed with a per-joint offset in the pipeline config, not by moving CAD.

**C7. Camera and mount frames.** Put a mate connector named `cam_<NAME>` at each camera's lens center, +X out of the lens and +Z up, with NAME matching the PhotonVision camera name. Put a `frame_<name>` connector at any point robot code measures from, such as the turret pivot. Model the camera body accurately enough that the lens center is right to a millimeter or two, since vision accuracy depends on it (§7.4).

Good part and subassembly names ("Elevator Carriage", not "Part 14") make the reports and generated code readable. The converter warns about default names.

## §5 Onshape API access

One mentor-owned, read-only API key pair, stored only as GitHub repository secrets, covers every student. Students never see or handle the key.

**Export route.** Onshape added native URDF export in March 2026 (https://www.onshape.com/en/resource-center/what-is-new/urdf-export-control-point-edit-curve-g3-support-connection-analysis). Later releases added mate limits, frames, and adjustable mesh resolution (1.215, https://www.onshape.com/en/resource-center/what-is-new/mate-connectors-explicit-lights-render-studio-advanced-urdf-mate-limit-support-robotics-applications), then OBJ, STL, and glTF mesh formats (August 2026, https://www.onshape.com/en/blog/cloud-native-cad-features-connecting-design-data), then merging fastened components into a single link (October 30, 2026, https://forum.onshape.com/discussion/32040/improvements-to-onshape-october-30-2026). An Onshape staff post in the March 2026 forum thread (https://forum.onshape.com/discussion/30410/improvements-to-onshape-march-13-2026) shows the API translation payload takes `formatName: URDF`, `urdfMeshFormat: GLTF`, and a `configuration` string. That is the primary route. *[Confirmed in Phase 0, A1:]* the request works with a read-only key and returns the same zip content as the UI export; exact request in `docs/phase0-findings.md`. onshape-to-robot (https://onshape-to-robot.readthedocs.io/en/latest/design.html) is the fallback if Phase 0 finds the native exporter drops nested subassembly mates or relations.

**Setup, done once by Bill, who holds the key.**

1. Sign in to aaps.onshape.com and create an API key in the Onshape developer portal under the AAPS enterprise, with read permission only.
2. In the robot repo on GitHub, add secrets `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY`, and a variable `ONSHAPE_BASE_URL` = `https://aaps.onshape.com`.
3. Share the robot CAD documents with the key owner's account if they are not already shared.
4. Record the key owner and creation date in the decisions doc. Rotate the key each August.

**Rules for the converter.**

- Export from an Onshape Version, not the live workspace, by default. Versions do not change, so the manifest can point to the exact CAD that made each model. A workspace export stays available as an option for quick previews.
- Use the async translation endpoint with exponential-backoff polling, and cache downloads by version ID so a re-run on the same version makes no API calls.
- Keep a call count in the run log. Education and Enterprise plans have API usage limits. Phase 0 measures the calls each run makes. There is no separate limit check up front; if usage looks high, Bill raises it with the district Onshape admin.
- Never write keys to disk, logs, or artifacts. Local runs read them from environment variables or the OS keychain.

**No-key fallback.** Any student can right-click the assembly in Onshape, choose Export, pick URDF with glTF meshes, and download a zip. The converter accepts that zip directly (§8). This path needs no API access and keeps the pipeline usable if the key expires at a bad time.

## §6 Converter specification

The converter is a Python command-line tool named `cad2ascope`. It turns a URDF export plus one small team config file into a ready AdvantageScope robot folder and a Java source file. It lives in its own repo, `FRC1076/cad2ascope`, so every season's robot repo uses the same tool. The repo is public, under the same BSD 3-Clause license as the team's robot code, so other teams can use it. Nothing team-specific, such as document URLs or keys, lives in it.

### 6.1 Stack

Python 3.12 managed by `uv`, with `numpy`, `scipy` (rotations), `trimesh` (mesh load, transform, merge, export), `fast-simplification` (quadric decimation), `pyyaml`, `requests`, `jinja2` (code generation), and `pytest`. Pin every version in `uv.lock`. Install with `uv tool install git+https://github.com/FRC1076/cad2ascope`.

### 6.2 Commands

| Command | What it does |
| --- | --- |
| `cad2ascope inspect <zip or url>` | Prints the kinematic tree, joint names, types, limits, and part counts. Students use it to fill in the config. |
| `cad2ascope init` | Writes a starter `cad/advantagescope.yaml` from the tree, one entry per movable joint. |
| `cad2ascope fetch` | Exports through the Onshape API and caches the URDF zip by version ID. |
| `cad2ascope build` | Builds the robot asset folder from a cached or manual zip. |
| `cad2ascope codegen` | Writes `RobotModel.java` and its unit test. |
| `cad2ascope run` | Runs fetch, build, and codegen, then writes the report. This is what CI calls. |
| `cad2ascope render` | Writes preview PNGs of the model at zero and at each joint's limits (Phase 5). |

### 6.3 Team config file

Each robot repo holds `cad/advantagescope.yaml`. Signals are the values robot code provides, in SI units. Joints map CAD mates to signals. The full example is `spec/advantagescope.example.yaml` and its schema is `spec/advantagescope.schema.json`.

```yaml
robot:
  name: "1076 2027"                 # shown in AdvantageScope's robot list
  folder: Robot_1076_2027
  onshape_url: https://aaps.onshape.com/documents/<did>/w/<wid>/e/<eid>
  configuration: "Export=AdvantageScope"
  version: latest                   # or an Onshape version name
  origin_frame: ascope_origin

signals:
  elevator: {units: m}
  wrist:    {units: rad}

joints:                             # only listed j_ mates become components
  j_elevator_stage1:   {signal: elevator, ratio: 0.5}
  j_elevator_carriage: {signal: elevator, ratio: 0.5}   # travel relative to stage 1
  j_wrist:             {signal: wrist, direction: -1, zero_offset_deg: 0}

mesh:
  triangle_budget: 300000
  exclude_names: ["*screw*", "*bolt*", "*nut*", "*washer*", "*rivet*", "*bhcs*", "*shcs*", "*fhcs*"]
  min_part_size_mm: 6
  keep_detail: ["*bumper*"]          # adds NOSIMPLIFY to these mesh names

cameras:                            # mate connectors named cam_<NAME>
  frame_prefix: cam_
  photonvision_calibrations: assets/photonvision   # resolution and FOV per camera
  fallback: {resolution: [1280, 800], fov_deg: 70}  # used when no calibration file matches

frames:                             # mate connectors named frame_<name>
  frame_prefix: frame_              # each becomes a Transform3d in RobotModel.Frames

codegen:
  java_package: frc.robot.generated
  output: src/main/java/frc/robot/generated/RobotModel.java
```

### 6.4 Build algorithm

1. **Load and check.** Parse the URDF, resolve mesh paths, and confirm the tree has one root and no loops. Fail with a plain-English message that names the mate when a check fails.
2. **Pick the frame.** Find `origin_frame` and compute the transform from CAD world to robot frame. All geometry is written in robot frame, so the robot-level `rotations` is empty and `position` is `[0, 0, 0]`.
3. **Classify joints.** A joint listed under `joints` is articulated. Any other movable joint is frozen at its export position, and the report lists it so students notice a missed mechanism. A listed joint missing from the URDF is an error.
4. **Group links.** Walk the tree from the root. A link joined to its parent by a fixed or frozen joint joins the parent's group. A link joined by an articulated joint starts a new component group. The root group becomes `model.glb`. Component indices follow a stable depth-first order by joint name.
5. **Build meshes.** For each group, place each link's visual meshes at their export pose in robot frame, drop parts matching `exclude_names` or smaller than `min_part_size_mm`, merge by material color, and decimate so the whole robot lands under `triangle_budget`. Each group's share of the budget is proportional to its triangle count. Write one `.glb` per group with embedded materials. *[As built in Phase 2, see `docs/phase2-results.md`:]* each mesh file is first welded at 0.1 mm with repeated triangles removed; then one per-part triangle cap is chosen so the robot fits the budget, parts under the cap are left exactly as they are, and only heavy parts are reduced (quadric decimation, then vertex clustering where that stalls, then a box as a last resort); `keep_detail` parts are never capped and their meshes are named `NOSIMPLIFY`. Merged meshes are named by group and color, so no CAD part name reaches AdvantageScope. Every mesh must carry normals and a material base color: AdvantageScope discards meshes without normals and ignores vertex colors and textures (Phase 0, B6). (The carpet warning planned here is not needed: merged meshes never carry part names.)
6. **Compute zeroed transforms.** For component *i*, let T0 be its root link frame in robot frame at the export pose. Each component `.glb` stays in robot frame at that pose, so it renders correctly when no poses are published. The zeroed transform is the inverse of T0, written as rotations then position.
7. **Cameras.** Each frame named `cam_<name>` becomes a `cameras` entry with exact position and rotations, using the WPILib camera convention (+X out of the lens). Resolution and field of view come from that camera's PhotonVision calibration file. AdvantageScope divides `fov` by the aspect ratio to get the vertical FOV (Phase 0, B5), so the converter writes `fov = (width / height) × true vertical FOV`, with the vertical FOV computed from fy. That makes the rendered view match the real camera. A camera on a moving mechanism (like a turret) still gets a `cameras` entry, but AdvantageScope fixes camera views to the robot, so the view shows the exported position only; the build warns, and the generated code moves the camera correctly (§7.4). Each `frame_<name>` connector becomes a named transform. Both also feed the generated code (§7.4).
8. **Write outputs.** `config.json`, `model.glb`, `model_0.glb` and on, `manifest.json` (source document, version ID, configuration, tool version, link list per component, triangles, file sizes, warnings), and `report.md` (the pull request body).

The math in step 6, with P the pose the robot code publishes and v a vertex of the component's exported mesh:

```
zeroed_i = T0_i^-1
rendered(v) = P_i(q) · T0_i^-1 · v
P_i(0) = T0_i  =>  rendered(v) = v
```

**Rotation rule (confirmed in Phase 0 from the AdvantageScope source, see `docs/phase0-findings.md` B1 to B4).** A `rotations` list turns about fixed axes, in list order (`[r1, …, rn]` gives `Rn·…·R1`), and `position` applies after rotation. With component poses published, AdvantageScope draws component *i* at `robot pose · P_i · zeroed_i`, and the robot-level `rotations` and `position` are not used for components. With none published, components get the robot-level transform, like the base model. The converter writes every rotation as `[x roll, y pitch, z yaw]`, the same matrix as URDF `rpy` and WPILib `Rotation3d`. `tests/test_transforms.py` round-trips random transforms through a port of AdvantageScope's own code.

### 6.5 Coupled joints

A joint's CAD value is computed from its signal:

```
q_cad = direction × ratio × (q_code − zero_offset)
```

If the URDF carries `<mimic>` elements from Onshape relations, `init` pre-fills the ratios from them. Otherwise students type the ratio. A ratio is always relative to the joint's parent link. In a two-stage cascade with the carriage mated to stage 1, both joints use 0.5. If the carriage were mated straight to the drivetrain instead, its ratio would be 1.0.

### 6.6 Error messages

Students will hit errors, so every message names the mate or part, says what is wrong, and says what to do in Onshape. One example: `j_wrist is a Fastened mate. Change it to Revolute, or remove it from cad/advantagescope.yaml.` The CLI exits non-zero on errors and zero with warnings, so CI can tell the two apart.

## §7 Generated Java and robot code integration

Robot code only has to report each mechanism's position in SI units. A generated class does all the transform math, so nobody writes chain math for a hood on a turret again.

### 7.1 Generated file

`RobotModel.java` is regenerated on every pipeline run and never edited by hand. It depends only on WPILib geometry classes, not on AdvantageKit, so it works under WPILib 2027 whatever logging the team uses.

```java
// GENERATED by cad2ascope 1.0 from Onshape version "Week 4 practice" (v=8c1f...). Do not edit.
package frc.robot.generated;

public final class RobotModel {
  public enum Signal { ELEVATOR, WRIST }          // from cad/advantagescope.yaml
  public static final int kComponentCount = 3;     // model_0.glb .. model_2.glb

  /** Joint origins, axes, parents, ratios, offsets as constants (generated). */

  /** Returns poses in component index order, ready for AdvantageScope. */
  public static Pose3d[] componentPoses(double[] signals) { ... }

  public static final class Cameras { /* Transform3d per cam_ frame (§7.4) */ }
  public static final class Frames  { /* Transform3d per frame_ connector (§7.4) */ }
}
```

The generator also writes `RobotModelTest.java`, a JUnit test that checks two things. With all signals at zero, each pose equals its T0 from the CAD. At every joint limit, every pose is finite. `./gradlew test` then catches a stale or broken generated file before it reaches the robot.

### 7.2 Hand-written visualizer

`cad2ascope init` writes `RobotVisualizer.java` once, and the software subteam owns it after that (template in `templates/robot-repo/`). *[As built in Phase 3:]* `codegen` (and `run`) writes `RobotVisualizer.java` and `SweepRobotModel.java` the first time and never overwrites them; the templates live in `src/cad2ascope/codegen/templates/` so they pick up the configured Java package. See `docs/phase3-notes.md`. Subsystems push their measured position into it. Once per loop it logs the component poses.

```java
// In ElevatorSubsystem.periodic()
visualizer.set(Signal.ELEVATOR, inputs.positionMeters);

// In RobotVisualizer.periodic()
Logger.recordOutput("RobotModel/Measured", RobotModel.componentPoses(measured));
Logger.recordOutput("RobotModel/Setpoint", RobotModel.componentPoses(setpoints));
```

Logging setpoints next to measured positions gives a ghost robot in AdvantageScope that shows where each mechanism is trying to go. Drive coaches and programmers can read that during replay. In simulation the same code shows the simulated mechanisms, so it doubles as a sim visualizer and can retire the Mechanism2d code.

### 7.3 When the CAD changes

A geometry-only change (new part, moved bracket) changes the `.glb` files and constants, and robot code compiles unchanged. Adding or removing a joint changes the `Signal` enum, so the build fails where a subsystem must add or remove a `set` call. That compile error is deliberate. The pull request report states it in its first line so the software lead is not surprised.

The 2027 code base may use the new WPILib `Telemetry` API instead of AdvantageKit's `Logger`. Only the two `recordOutput` lines in `RobotVisualizer` change. [CONFIRM 2027 logging choice with the software lead]

### 7.4 Camera and mount transforms from CAD

The pipeline also generates the robot-to-camera transforms that vision code needs, so nobody measures them with a tape again. In the 2026 code, the four PhotonVision transforms are typed by hand in inches and degrees (`PhotonConfig` in `PhysicalConstants.java`), and so is the turret location (`kBotRelativeTurretPose`). A sign slip or a stale measurement there shifts every vision pose estimate and looks like a tuning problem. One example is the +20° pitch on each camera, which in WPILib's convention means tilted down. That is easy to get backwards.

- **CAD.** Each camera gets a mate connector named `cam_<NAME>` at the lens center, with +X out of the lens, +Y left, and +Z up, which is the WPILib camera frame. NAME matches the PhotonVision camera name, for example `cam_FRONT_LEFT`. Other measured points use `frame_<name>`, for example `frame_turret_pivot` or `frame_shooter_exit`.
- **Generated code.** Each camera becomes a `Transform3d` constant under `RobotModel.Cameras`, and vision code uses it in place of the hand-typed values. A camera on a moving mechanism gets a method that takes signal values instead, since its transform changes as the mechanism moves. Each `frame_` connector becomes a `Transform3d` constant under `RobotModel.Frames`.
- **AdvantageScope.** The same frames become fixed camera views in `config.json`. Resolution and field of view come from the calibration files in `assets/photonvision`. For the 2026 FRONT_LEFT camera (1280 × 800, focal length near 923 px) the true horizontal FOV is about 69.5°, but the converter writes `fov` = 75.0°, because AdvantageScope treats `fov / aspect` as the vertical FOV (§6.4 step 7, Phase 0 B5). A student tuning vision can switch the 3D field to a camera's view and compare it with the PhotonVision stream to catch a wrong mount angle by eye.
- **Change report.** Each pull request lists how far every camera transform moved since the last run, in millimeters and degrees. The first run on the 2026 robot compares CAD against the current hand-typed values (§10.3 item 7).
- **CAD is the single source.** When a camera's real mount disagrees with CAD, fix the CAD or the mount. Do not add an override in code, because overrides are how the hand-typed values drifted in the first place.

## §8 Where it runs

GitHub Actions is the main route because it works from any browser, including district MacBooks where students cannot install software. Team Windows laptops get a local route for fast iteration while setting up the CAD conventions.

| Machine | How a student runs it | Needs installed | Uses the API key |
| --- | --- | --- | --- |
| District MacBook | GitHub, Actions tab, "Update robot model", Run workflow | Nothing | Yes, through repo secrets |
| District MacBook, no API | Upload an Onshape URDF zip to `cad/drops/` on a branch in the GitHub web UI | Nothing | No |
| Team Windows laptop | `./gradlew updateRobotModel`, or `cad2ascope run` in a terminal | WPILib, `uv` | Optional; a manual zip works without it |
| Team Windows PC, personal device, or mentor or faculty computer (viewing) | Pull the repo, point AdvantageScope at `assets/advantagescope` | AdvantageScope | No |

### 8.1 GitHub Actions workflow

`.github/workflows/update-robot-model.yml` in the robot repo (draft in `templates/robot-repo/`):

1. Triggers on `workflow_dispatch` with optional inputs (Onshape version name, workspace preview toggle), and on a push that adds a zip under `cad/drops/`.
2. Installs `uv` and the pinned `cad2ascope` version.
3. Runs `cad2ascope run`, using the dropped zip when one triggered the run.
4. Runs `./gradlew test` so the generated Java must compile and pass its test.
5. Opens or updates a pull request on branch `robot-model/update` with `report.md` as the body and preview renders attached once Phase 5 adds them. The pull request stays open for a person to review and merge. Nothing merges automatically.
6. Deletes the dropped zip in the same pull request so drops do not pile up.

*[As built in Phase 5, see `docs/phase5-notes.md`:]* the workflow runs one command, `cad2ascope ci`, then `./gradlew test`. A zip dropped on a branch other than the default branch is processed and the result committed back onto that branch, so the student's own pull request updates; every other run opens or updates `robot-model/update`. If `./gradlew test` fails the pull request still opens and the job then fails, because an added or removed joint is meant to break the build until the subsystems catch up (§9 P3). Preview renders and the zero-pose check (§10.3 item 2) are in the pull request body.

A typical run should take 5 to 15 minutes, almost all of it Onshape's translation time. *[Phase 0 measured]* the 2026 robot's API export at 63 s of translation and 74 s including download, so most of a CI run will be installing tools and running `./gradlew test`.

### 8.2 Local route on team laptops

A Gradle task `updateRobotModel` in the robot repo calls `uv run cad2ascope run`, so programmers already in VS Code use a familiar command. It reads API keys from environment variables if present and otherwise asks for a URDF zip path. Keys should live only on mentor-managed laptops, not on shared ones. [CONFIRM which laptops]

### 8.3 Where the files live

The asset folder sits in the robot repo at `assets/advantagescope/Robot_1076_2027/`. In AdvantageScope, App, then Use Custom Assets Folder, point at `assets/advantagescope`. Then every student who pulls the repo sees the model that matches the code they are running. The AdvantageScope docs recommend this setup for keeping assets under version control.

Model files are binary, and each update adds roughly the size of the whole model to repo history. With the triangle budget in §6.3 a model should stay near 10 to 20 MB, so a season of 20 to 30 updates is manageable without Git LFS. [CONFIRM after Phase 2 measures real sizes]

District MacBooks will not get AdvantageScope. MacBook students trigger and review updates in the browser, then view the model on a team Windows PC, a personal device, or a mentor or faculty computer.

## §9 Student procedures

Five short procedures cover every student task. Each one becomes a page in the robot repo's `docs/` folder and a one-page printout for the lab. Claude Code writes them in Phase 6 from this outline.

### P1. Season setup (Design leads with a programmer, once per robot, about 1 hour)

1. In the main assembly, add the `Export` configuration and set up its `AdvantageScope` value (C1).
2. Add the `ascope_origin` mate connector on the drivetrain (C2).
3. Rename each moving mate with the `j_` prefix and set mate limits (C3). Fix any closed linkages in the export configuration (C4).
4. Add `cam_` and `frame_` connectors (C7).
5. Pose the robot at code zero, save the Named Position `ascope_zero`, and create an Onshape Version (C6).
6. Run `cad2ascope inspect` with the assembly URL, then `cad2ascope init` to make the starter config. Fill in signal names, ratios, and directions with the software lead.
7. Paste the assembly URL into `cad/advantagescope.yaml`, commit, and run P2.

### P2. Update the model (any student, about 2 minutes of clicks)

1. In Onshape, put the robot in the `ascope_zero` position and create a Version with a clear name ("Week 4, new intake plates").
2. In the robot repo on GitHub, open Actions, choose "Update robot model", and click Run workflow.
3. Wait for the pull request. Read the report's warnings and look at the preview images.
4. Ask the software lead or a mentor to review and merge.

### P3. Add or remove a mechanism (CAD student and programmer together)

1. CAD student adds or renames the `j_` mate and creates a Version.
2. Programmer adds the joint and its signal to `cad/advantagescope.yaml`.
3. Run P2. The pull request will not compile until the subsystem calls `visualizer.set` for the new signal.
4. Programmer adds the `set` call in the subsystem on the same branch, and the pull request goes green.

### P4. View the robot in AdvantageScope

1. On a team Windows PC, a personal device, or a mentor or faculty computer (not a district MacBook), pull the latest robot code.
2. In AdvantageScope, choose App, then Use Custom Assets Folder, and select `assets/advantagescope` in the repo. This is needed once per laptop.
3. Open a 3D Field tab, pick robot "1076 2027", drag the robot pose onto it, then drag `RobotModel/Measured` onto it as component poses. Add `RobotModel/Setpoint` as a ghost if wanted.
4. Save the layout to the repo so the next student skips step 3. [CONFIRM layout file location]

### P5. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Run fails with "origin frame not found" | `ascope_origin` missing or inside a suppressed part | Add it on the drivetrain (C2) |
| A mechanism does not move | Its mate is missing the `j_` prefix or is not in the config | Rename the mate (C3), add it to the config |
| A mechanism moves the wrong way | Direction mismatch between CAD and code | Set `direction: -1` for that joint |
| A mechanism is offset at zero | Robot exported away from code zero | Re-export from `ascope_zero`, or set `zero_offset` |
| Export fails with a loop error | Closed linkage in the export configuration | Fasten all but one of its joints (C4) |
| Model loads slowly | Too many triangles or fasteners left in | Lower `triangle_budget`, extend `exclude_names` |
| Pull request fails to compile | A joint was added or removed | Follow P3 |
| Camera transform moved a lot in the report | `cam_` connector moved or camera mount changed in CAD | Check the CAD change with the vision lead before merging |

## §10 Validation and test plan

The 2025 and 2026 robots are the acceptance tests. Between them they cover a multi-stage elevator, a nested turret and hood, pivots, and a climber. If both work with no hand edits, the 2027 robot will too.

### 10.1 Automated tests in the converter repo

- **Synthetic URDFs.** Small fixtures (starter set in `tests/fixtures/`): one revolute, one prismatic, a two-level chain with a camera, a coupled pair, a frozen joint, a link with two parents that must fail, and a missing origin frame that must fail.
- **Transform math.** For random T0 values, apply the zeroed transform and the FK pose at zero and check that vertices come back within 1e-6 m. Round-trip random rotations through the rotation-sequence writer using AdvantageScope's confirmed rule (§6.4).
- **Golden files.** `config.json` and `RobotModel.java` for each fixture are checked in, and any difference fails the test.
- **Mesh budget.** The built model never exceeds `triangle_budget`, and excluded name patterns never appear in the output.

### 10.2 Pilot robots

Work on copies of the 2025 and 2026 Onshape documents, so the season archives stay untouched, and on branches of the 2025 and 2026 code repos.

| Robot | Joints to articulate | What it proves |
| --- | --- | --- |
| 2026 Rebuilt | Turret, hood on turret, slapdown intake, climber, hook | Nested chain, several independent mechanisms, four cameras |
| 2025 Reefscape | Elevator stages, carriage, wrist on carriage | Coupled stages, a joint riding on a moving stage |

Names are taken from the subsystem folders in each code repo. The CAD may split mechanisms differently. Bill and the Design leads set the final list for each robot before Phase 1.

### 10.3 Pass criteria for each pilot

1. P2 runs from a MacBook browser and opens a pull request with no file edits.
2. With component poses at zero, the model looks identical to the model with no poses published. A screenshot diff from `cad2ascope render` checks this.
3. A simulation command sweeps each joint from its lower to its upper mate limit. In AdvantageScope every component stays attached at its joint through the whole sweep, checked by a student watching a replay.
4. For 2026, real match logs replay with mechanisms moving correctly, using a code branch with the visualizer added and AdvantageKit replay. No 2025 logs are available, so the 2025 robot is checked with the simulation sweep only.
5. The model loads in AdvantageScope on a team laptop within the §1 target.
6. A student who did not help build the tool completes P2 and P4 from the printed procedure without help.
7. For 2026, the generated camera transforms match the hand-measured `PhotonConfig` values in `PhysicalConstants.java` within 10 mm and 1°, or each difference is traced to a CAD or code error.

## §11 Implementation phases for Claude Code

Build it in eight phases, each ending in a pull request and a stop for Bill's review. Phase 0 matters most, because two facts the design rests on are unverified. The goal is Phases 0 to 5 done before the January 2027 kickoff, so the 2027 robot uses the pipeline from its first assembly. [CONFIRM target]

1. **Phase 0, verification spike.** Answer these with real exports of the 2026 robot copy, and write the answers to `docs/phase0-findings.md` (checklist in `docs/PHASE0-CHECKLIST.md`).
    - The exact Onshape API call for URDF with glTF meshes on aaps.onshape.com, including the parameters for configuration, version, mesh resolution, and merging rigid subassemblies. Use the API Explorer and `getAllTranslatorFormats`.
    - Whether the native exporter includes mates inside flexible subassemblies, keeps mate names as joint names, exports mate connectors as frames, and turns relations into `<mimic>`.
    - Whether an export can target a Named Position.
    - Export time and zip size for both pilot robots.
    - From the AdvantageScope source, how a rotation sequence is applied (fixed or moving axes) and the order in which robot, zeroed, and component poses combine.
    - **Decision gate.** Native exporter, or onshape-to-robot as fallback. Update §4 and §6 to match what the exporter really does.
2. **Phase 1, core build from a zip.** `inspect`, `init`, and `build` working from a manual zip, with the grouping, frame, and zeroed-transform logic and all §10.1 tests except the mesh budget. Exit when the 2026 pilot builds and its components line up at zero in AdvantageScope.
3. **Phase 2, mesh reduction.** Filtering, merging by material, decimation, and `NOSIMPLIFY` tagging. Exit when both pilots meet the size and load-time targets, with sizes recorded for the Git LFS decision.
4. **Phase 3, code generation.** `RobotModel.java`, `RobotModelTest.java`, the `RobotVisualizer` template, and a joint-sweep simulation command. Add the camera and frame transforms (§7.4). Wire them into a branch of the 2026 code repo. Exit when §10.3 items 2, 3, and 7 pass.
5. **Phase 4, Onshape API.** `fetch` with versioned caching, backoff, and call counting. Exit when `run` works end to end from a URL.
6. **Phase 5, CI.** The GitHub Actions workflow, zip drops, pull request creation, and preview renders. Exit when P2 works from a MacBook browser.
7. **Phase 6, documentation.** Procedures P1 to P5 in the robot repo, the printable lab sheets, and an updated `CLAUDE.md` in the converter repo.
8. **Phase 7, pilots and handover.** Run §10.3 on both robots, fix what students trip on, then set up the 2027 robot at kickoff.

**Working rules for Claude Code.**

- Never edit the original season Onshape documents. Work on copies, and keep the API key read-only.
- Never commit or print API keys. Use repo secrets in CI and environment variables locally.
- When a phase changes only a few files, show the changed files one by one before producing a full bundle.
- Check the team's real code and CAD before assuming hardware or structure. Both repos are public on GitHub as `FRC1076/2025-Competition` and `FRC1076/2026-Competition`.
- Pin tool versions, and keep the converter free of anything that needs admin rights to install.
- Write error messages for a ninth-grade CAD student, not a programmer.

## §12 Open decisions

See `DECISIONS.md` for the current table. Six of twelve are decided, including all three that blocked Phase 0.
