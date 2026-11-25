# Phase 0 findings

Status on 2026-11-25: **section B (AdvantageScope) is done. Section A (Onshape export) has not started**, because it needs the Onshape keys and a copy of the 2026 robot, and neither is available yet. The decision gate below is filled in only where section B can answer it. What Bill needs to provide for section A is listed at the end.

## Decision gate (summary for Bill)

1. **Export route: not decided yet.** It depends on A4 to A6 (nested mates, mate names, mate connectors), and none of those has been tested. The plan's primary route (native URDF export) stands until section A runs. onshape-to-robot remains the fallback.
2. **Changes to PLAN §4 (CAD conventions): none from section B.** Section A may change C2, C3, C5 and C7, depending on how the exporter names joints and frames and whether it carries relations.
3. **Changes to PLAN §6 (converter), from section B. All are proposed in this pull request:**
   - The rotation rule is confirmed. Steps turn about fixed axes, in list order, and position applies after rotation. The composition is robot pose · component pose · zeroed. The PLAN §6.4 math (zeroed = T0⁻¹) is correct as written. The "must be confirmed" paragraph is replaced with the confirmed rule.
   - **Camera FOV needs a correction.** AdvantageScope's docs call `fov` the horizontal field of view, but the renderer computes the vertical FOV as `fov / aspect` (a linear division, not the trigonometric conversion). Writing the true horizontal FOV makes the view too narrow. For the 2026 FRONT_LEFT camera, writing 69.5° renders a 65.0° horizontal view. The converter should write `fov = aspect × true vertical FOV`, which is 75.0° for that camera, so the rendered view matches the real camera. This only changes how the AdvantageScope camera view looks. The generated `Transform3d` values are not affected. See B5.
   - **Mesh output rules for Phase 2.** AdvantageScope discards any mesh without normals, ignores vertex colors and textures (color comes only from the material's base color), and treats meshes with "carpet" in the name specially. The `.glb` writer must emit normals and one material per color. See B6.
4. **Fixtures:** the frame representation (mate connectors as dummy links on fixed joints) is still an unverified assumption until A6 runs. One generator bug is fixed in this pull request: URDF numbers were written with 6 significant digits, so the origin yaw of π/2 became 1.5708 and the URDF disagreed with `expected.json` by about 4 µrad and 1 µm. Numbers are now written at full precision. `expected.json` did not change.
5. **Export time, size, and API calls:** not measured yet (A10).

## Section B: AdvantageScope semantics

Source: https://github.com/Mechanical-Advantage/AdvantageScope at commit `ea60b46` (2026-11-25). Paths below are relative to that repo. Each rule is also encoded in `tests/ascope_reference.py`, a port of this code that `tests/test_transforms.py` checks `cad2ascope.transforms` against.

### B1. Rotation sequences use fixed (extrinsic) axes, applied in list order

`src/shared/geometry.ts:128-139`, `rotationSequenceToQuaternion`: starts from the identity quaternion and, for each entry, calls `quaternion.premultiply(axisAngle)` (line 135). Premultiplying puts each new rotation on the left, so `[r1, r2, …, rn]` gives `R = Rn · … · R2 · R1`. Each step turns about the original (fixed) axes. The same function is used for the robot-level `rotations`, `zeroedRotations`, and camera `rotations`.

Consequence for the writer: emitting `[x roll, y pitch, z yaw]` produces `Rz(yaw)·Ry(pitch)·Rx(roll)`. That is the same matrix as URDF `rpy` and WPILib `Rotation3d(roll, pitch, yaw)`.

### B2. Position is applied after rotation, in the parent frame

`src/shared/renderers/field3d/objectManagers/RobotManager.ts:369-370`: the rotation and the `position` are set on the same three.js `Object3D` (`dummyConfigPose`). three.js builds an object's local matrix as `Translate(position) · Rotate(quaternion)`, so a point is rotated first and then shifted. This matches the docs. For the base model the same happens in `src/shared/renderers/field3d/workers/loadRobot.ts:45-46`.

### B3. Composition with component poses published

`RobotManager.ts:65-67` nests three objects: `dummyRobotPose` ⊃ `dummyUserPose` ⊃ `dummyConfigPose`. Lines 346-375 set them per frame:

```
component world = RobotPose · ComponentPose · Translate(zeroedPosition) · Rotate(zeroedRotations)
mesh vertex in world = component world · v
```

- The component pose is **robot-relative**. It sits under the robot pose. `src/hub/controllers/Field3dController.ts:346-348` passes the logged poses through unchanged.
- **The robot-level `rotations` and `position` are not applied to components** when component poses are published. Line 366 picks `zeroedRotations` instead of `rotations`, and line 368 picks `zeroedPosition` instead of `position`. Since cad2ascope writes `rotations: []` and `position: [0, 0, 0]`, this makes no difference for us.
- So with zeroed = T0⁻¹ and a published pose of T0 at q = 0, the mesh lands exactly where it was exported. PLAN §6.4 is correct. Tested in `test_published_t0_draws_component_where_it_was_exported`.

### B4. Composition with no component poses published

Same code. When a component has no published pose, `userPose` is null (line 356). The middle object is then set to identity, and the config object gets the robot-level `rotations` and `position` instead of the zeroed values (lines 357-368):

```
component world = RobotPose · Translate(position) · Rotate(rotations)
```

This is the same transform as the base model (`loadRobot.ts:45-46` plus `meshes[0].setPoses(robot poses)` at line 343). Component meshes exported in robot frame at their export pose therefore line up with the base model. Tested in `test_no_published_poses_uses_robot_level_config`.

Note: this choice is made per component index. If code publishes fewer poses than there are components, the extra components fall back to the robot-level transform. `RobotModel.componentPoses` always returns the full array, so this does not come up.

### B5. Camera entries look along +X with +Z up, and FOV is used linearly

`src/shared/renderers/Field3dRendererImpl.ts:82-91` defines `CAMERA_ROTATION` as the sequence `[z −90°, y −90°]`. At line 983 the camera's orientation is `rotationSequenceToQuaternion(camera.rotations) · CAMERA_ROTATION`. A three.js camera looks down its own −Z with +Y up. `CAMERA_ROTATION` maps −Z to +X and +Y to +Z. **A `cameras` entry therefore looks along its frame's +X with +Z up**, which is exactly the WPILib camera frame in PLAN §7.4. A `cam_` connector's transform can be written straight into `rotations` and `position` with the same writer as components. Tested in `test_camera_entry_looks_along_plus_x_with_plus_z_up`.

FOV: `Field3dRendererImpl.ts:963` sets `fov = cameraConfig.fov / aspectRatio`, and line 1013 assigns that to the three.js camera's `fov`, which three.js treats as the **vertical** FOV. The docs (`docs/docs/more-features/custom-assets/index.md:59`) call the field "Horizontal field of view in degrees". Dividing by the aspect ratio is a linear approximation of the vertical FOV. For a 1280 × 800 camera with fx = fy ≈ 922.66 (2026 FRONT_LEFT):

| Value | Degrees |
| --- | --- |
| True horizontal FOV, 2·atan(640 / fx) | 69.5 |
| True vertical FOV, 2·atan(400 / fy) | 46.9 |
| Vertical FOV AdvantageScope uses if we write 69.5 | 43.4 |
| Horizontal view that renders | 65.0 |
| Value to write so the vertical (and horizontal) view is correct: 1.6 × 46.9 | 75.0 |

Proposed rule: `fov = (width / height) × 2·atan(height / (2·fy))`, in degrees. This makes AdvantageScope's camera view match the PhotonVision stream, which is the point of PLAN §7.4's "compare by eye" step. It could be reported upstream to AdvantageScope as a docs or code mismatch. That is for Bill to decide.

### B6. Limits, simplification, and mesh requirements

From `src/shared/renderers/field3d/OptimizeGeometries.ts` (used by `loadRobot.ts` on desktop) and the XR branch of `RobotManager.ts:186-232`:

- **No component-count limit** was found in `RobotManager.ts` or `src/main/assetUtil.ts` (config parsing). Each `.glb` is merged into at most one opaque and one transparent mesh (`loadRobot.ts:47-58`), so draw calls stay low however many parts a component has.
- **Automatic simplification drops whole meshes, not triangles.** It drops each glTF mesh whose vertices all lie within a radius of their centroid (world space) below 2 cm (cinematic), 4 cm (standard), or 8 cm (low-power and XR) (lines 13-16, 186-197). FTC robots use a quarter of those radii. A mesh is kept when `disableSimplification` is true or its name contains `NOSIMPLIFY` (line 186). `disableSimplification` is read from `config.json` in `src/main/assetUtil.ts:353-354`. Because Phase 2 merges each group's parts by color into a few large meshes, the AdvantageScope simplifier will rarely remove anything from our models. Our own `min_part_size_mm` and `exclude_names` filters do the real removal.
- **Meshes without normals are discarded** (line 137). All attributes except `position` and `normal` are deleted, so **vertex colors and textures are dropped**. The color is taken from the material's base color only (lines 146-165), and a mesh with several materials gets no color. A material with opacity below 0.75 goes to the transparent pass (line 150).
- Meshes whose name contains "carpet" (any case) are handled as carpet (line 206). The converter should warn if a part name contains "carpet".
- Implication for the Phase 2 writer: every output mesh needs a `NORMAL` attribute and a material with `baseColorFactor`. The synthetic fixture meshes in `tests/fixtures/` have neither (they carry `COLOR_0` vertex colors and no material). That is fine for tests of the transform logic, but they would render as nothing in AdvantageScope. Built models must be checked in AdvantageScope itself, as the Phase 1 exit criterion already requires.

### Rotation helper

`src/cad2ascope/transforms.py`: `matrix_to_sequence`, `sequence_to_matrix`, `to_config`, `from_config`, `zeroed_config`, `invert`. The writer always emits `[x, y, z]` steps and handles gimbal lock (pitch = ±90°).

`tests/test_transforms.py` checks it against the port in `tests/ascope_reference.py`:

- It round-trips 1,000 uniformly random transforms through config values and AdvantageScope's quaternion math. The worst element error is 3.6 × 10⁻¹⁵, well inside the 1 × 10⁻⁹ requirement.
- It also checks arbitrary-length random sequences against the port, the gimbal-lock cases, the B3 and B4 compositions, that every fixture's zeroed values rebuild `expected.json`, and the camera view axis.

## Section A: Onshape native URDF export (in progress)

Copies of the 2025 and 2026 main assemblies now exist (their URLs are in `private/`, not here). Manual exports from the Onshape UI are under way. No API keys are set yet, so A1, A8 and A10 (API request, Named Positions, timing and call counts) are still open.

### A2 (partial): export dialog options, from the Onshape UI on 2026-11-25

Right-click the assembly tab → Export. The dialog was the same on the 2025 and 2026 copies:

| Field | Value seen | Notes |
| --- | --- | --- |
| Format | URDF | |
| Geometry format | GLTF (selected) | Other choices not recorded yet. PLAN §5 lists OBJ, STL and glTF. |
| Resolution | Medium (default) | Other levels not recorded yet. |
| Options | Download | The other choice(s) in this dropdown are not recorded yet. |
| Export rigid subassemblies as a single link | off (default) | This is the October 2026 merge option. It may decide whether we get one link per part or one per rigid group (A3). |
| Include hidden instances in export | **on, and greyed out** | Hiding a part in Onshape does **not** keep it out of the export. Parts must be suppressed, which is what PLAN §4 C1's `Export=AdvantageScope` configuration does. |

No configuration selector appeared in the dialog. Neither copy appears to have configurations yet, so it is still unknown whether the UI export lets you pick one (C1).

Also seen in the screenshots: the 2026 assembly places its top-level subassemblies with **Planar** and Fastened mates, and both assemblies show error or warning markers on some instances. A Planar mate is not a joint cad2ascope animates. If Onshape exports it as a URDF `planar` joint, the converter freezes it at its export position (it is not one of the Revolute/Slider types that can move). Whether those mates export cleanly is part of A3/A4.

One thing the checklist leaves out: **A5, A6 and A7 require editing the copy** (rename a mate to `j_test`, add `ascope_origin` and `cam_TEST` mate connectors, add a linear relation). The API key is read-only by design, so Claude Code cannot make those edits. Bill or a Design lead makes them in the Onshape UI on the copy, and Claude Code then re-exports through the API.

### What Bill needs to provide

1. **Store the read-only key pair:** run `scripts/setup-mac.sh --store-keys` in Terminal. Claude Code then loads the keys into each command with `source scripts/onshape-env.sh`, which reads them from the Keychain and never prints them. If macOS asks whether `security` may read the item, allow it. Alternatively, start `claude` from a terminal after sourcing the script.
2. **A copy of the 2026 Rebuilt main assembly,** shared with the key owner's account, with its URL saved in `private/` (never in the repo). Keep the copy's mates as they are for A1 to A4. A5 to A7 come after.
3. **Edits on that copy for A5 to A7** (after the first export): rename one moving mate to `j_test`; add mate connectors `ascope_origin` (drivetrain, center of frame perimeter, floor plane, +X forward, +Z up) and `cam_TEST` (on any camera); add a linear relation between two sliders if none exists. Then create a new Version.
4. **A copy of the 2025 Reefscape main assembly** for the A10 timing comparison (and later the 2025 pilot).
5. Optional: a manual URDF export zip of the 2026 copy, downloaded from the Onshape UI with glTF meshes, for comparison with the API export.
