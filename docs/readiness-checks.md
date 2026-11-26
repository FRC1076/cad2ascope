# Readiness checks that need no CAD edits (2026-11-26)

These are four checks done while Phase 7 waits on the Onshape edits. Nothing in `src/` changed. Results:
- **WPILib 2027:** the generated code works after renaming its imports.
- **AdvantageScope:** every rule cad2ascope relies on holds in the current release and the 2027 beta.
- **Logging:** both 2027 logging options compile.
- **Load time:** the model loads in about a sixth of a second on a fast Mac.

## 1. Generated code against WPILib 2027

**What was checked.** I took the generated `RobotModel.java` and `RobotModelTest.java` for all five valid fixtures, and the `RobotVisualizer` and `SweepRobotModel` templates. With the renames below applied, I compiled them with `javac -Xlint:all -Werror`, the same way the tests do.
- **Libraries:** WPILib `2027.0.0-alpha-8` (the newest release, 2026-10-30), from `https://frcmaven.wpi.edu/artifactory/release` under group `org.wpilib`.
- **JDK:** Temurin 25.0.5.1.
- **Results:** all five `RobotModelTest`s pass, and both templates compile.

**What changes for 2027:**
- **WPILib moved from `edu.wpi.first.*` to `org.wpilib.*`.** The Maven group IDs changed too (`org.wpilib.wpimath`, and so on). Alpha-3 and earlier still used `edu.wpi.first`.
- **The class and constructor names the generated code uses did not change.** Only the import lines differ:

| 2026 import | 2027 alpha-8 import |
| --- | --- |
| `edu.wpi.first.math.geometry.*` (Pose3d, Transform3d, Rotation3d, Quaternion, Translation3d) | `org.wpilib.math.geometry.*` |
| `edu.wpi.first.math.VecBuilder` | `org.wpilib.math.linalg.VecBuilder` (it also moved to a sub-package) |
| `edu.wpi.first.wpilibj.TimedRobot` | `org.wpilib.framework.TimedRobot` |
| `edu.wpi.first.wpilibj2.command.*` (Command, SubsystemBase) | `org.wpilib.command2.*`, from the artifact `org.wpilib.commandsv2:commandsv2-java` |

- **`TimedRobot.kDefaultPeriod` is now `TimedRobot.DEFAULT_PERIOD`** (still 0.02 s). `SweepRobotModel` uses it.
- **Java 25.** The alpha-8 jars are class-file version 69, which needs JDK 25. Alpha-3 needed only Java 21. CI's JDK must be 25 for a 2027 check.
- **One more jar for compiling against commands.** `Command` implements `org.wpilib.tunable.ComplexTunable`, so compiling against `commandsv2` also needs `org.wpilib.tunables:tunables-java`. A robot project's Gradle setup pulls it in by itself; only the bare-`javac` test harness needs it listed.

**Proposed change (not built; Bill decides).** Add a new `wpilib` setting under `codegen` (not in the schema yet) (`2026` or `2027`) that picks the import names and `DEFAULT_PERIOD`. Then extend CI to compile and test against 2027 with JDK 25, next to the existing 2026 check. Until 2027 leaves alpha, its names could still change, so the check should pin one alpha and be updated by hand. PLAN §7.1 is updated to say the generated code is not import-compatible across years.

## 2. AdvantageScope rules, rechecked

Phase 0 Section B was verified at AdvantageScope commit `ea60b46` (main, 2026-11-25). That commit is not a release, so I rechecked against:
- `v26.0.2`, the current stable release and what team laptops run for 2026;
- `v27.0.0-beta-1` (2026-11-25), whose only difference from `ea60b46` is a README screenshot.

**Every rule B1 to B6 holds in both, with only line numbers moved.** That covers:
- fixed-axis rotation order;
- position after rotation;
- `robot pose · P_i · zeroed_i` placement;
- the no-component-poses branch;
- camera axes;
- the `fov / aspect` vertical FOV;
- the mesh rules.

Line numbers in `v26.0.2`:
- `geometry.ts:127-139`;
- `RobotManager.ts:355-377`;
- `Field3dRendererImpl.ts:917` (FOV);
- `OptimizeGeometries.ts:13-17, 138-165, 188, 208`;
- `assetUtil.ts:309-310`.

**Changes in v27 that do not affect cad2ascope:**
- `config.json` gains an optional `locales` field (`assetUtil.ts:21-44`). Leaving it out stays valid.
- The old numeric-array source for component poses is removed. `RobotVisualizer` logs `Pose3d[]`, which remains.
- The default field coordinate system is now `center-red`. That changes field poses, not robot-relative components or cameras.

**New detail for B6:** `loadRobot.ts:62-63` keeps only the normal meshes, so a robot mesh whose name contains "carpet" is not drawn at all. cad2ascope is not exposed, because merged meshes are named by group and color, never by part.

**FOV mismatch (decision #14):** unchanged in every version, and the docs still say horizontal. No upstream issue or pull request about it exists. The nearest, #454, is about camera rotation.

## 3. Logging for 2027 (decision #8)

Both versions of `RobotVisualizer` compile with `-Werror` against WPILib 2027 alpha-8:
- **AdvantageKit:** unchanged except for imports, against `akit-java 27.0.0-alpha-7` (the newest, 2026-10-23).
- **WPILib Telemetry:** `org.wpilib.telemetry.Telemetry`. The two logging lines become:

```java
Telemetry.log("RobotModel/Measured", RobotModel.componentPoses(shown), Pose3d.struct);
Telemetry.log("RobotModel/Setpoint", RobotModel.componentPoses(setpoints.clone()), Pose3d.struct);
```

The import `org.littletonrobotics.junction.Logger` is replaced by `org.wpilib.telemetry.Telemetry` and `org.wpilib.math.geometry.Pose3d`. `Telemetry.log(String, T[], Struct<? super T>)` is in `telemetry/src/main/java/org/wpilib/telemetry/Telemetry.java` at tag `v2027.0.0-alpha-8`.

**Not checked:** that AdvantageScope shows what `Telemetry` publishes. That needs a running robot program, and the native libraries were not set up for it. AdvantageKit also has a 2027 alpha, so neither option is blocked.

## 4. Load time on a Mac (decision #5, rough)

**Setup:**
- AdvantageScope `v26.0.2` (macOS arm64), run from a scratch copy with its own settings folder;
- the Phase 2 models (2026 at 13.0 MB with `keep_detail`, 2025 at 14.6 MB);
- the Mac this was run on (Apple M5, 16 GB).

**Method.** Over the remote-debugging port, I ran AdvantageScope's own robot loader worker (`bundles/shared$loadRobot.js`) in the hub window, with the same inputs the 3D tab gives it. The worker fetches the `.glb` files, parses them, and runs AdvantageScope's mesh optimizer. I ran four loads per detail mode, the first one cold.

| Model | standard | cinematic | low-power | Triangles AdvantageScope kept |
| --- | --- | --- | --- | --- |
| 2026 (two files) | 159 to 176 ms | 158 to 165 ms | 157 to 163 ms | 278,994 + 16,477 of 279,902 + 16,477 |
| 2025 (one file) | 155 to 159 ms | 155 to 161 ms | 153 to 199 ms | 292,455 of 292,846 |

**What this leaves out:**
- building the meshes on the main thread and the first render, which are not timed here;
- AdvantageScope's own start-up.

A team Windows laptop will be slower, possibly several times slower. Even so, this suggests the 10-second draft target has a wide margin. Decision #5 still needs the measurement on a team laptop (HUMAN-CHECKLIST item 10), including how the model looks.
