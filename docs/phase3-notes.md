# Phase 3 notes: generated robot code

`cad2ascope codegen <zip>` writes the robot-code side; `cad2ascope run` now fetches, builds, and generates code in one go. Code: `src/cad2ascope/codegen/`, `src/cad2ascope/report.py`.

## What gets written into the robot repo

| File | Written | Who edits it |
| --- | --- | --- |
| `src/main/java/frc/robot/generated/RobotModel.java` (`codegen.output`) | every run | nobody: regenerated |
| `src/test/java/frc/robot/generated/RobotModelTest.java` (`codegen.test_output`) | every run | nobody: regenerated |
| `src/main/java/frc/robot/visualization/RobotVisualizer.java` | first run only | the software subteam |
| `src/main/java/frc/robot/visualization/SweepRobotModel.java` | first run only | the software subteam |
| `assets/advantagescope/Robot_*/report.md` | every build | nobody: it is the pull request body |

**`RobotModel`** depends only on `edu.wpi.first.math` (Pose3d, Transform3d, Rotation3d, Quaternion, Translation3d, VecBuilder). It contains:
- `Signal`: an enum in config order, each with `min` and `max` from the CAD mate limits converted into robot-code units through the ratio, direction and zero offset;
- `componentPoses(double[] signals)`: one pose per component, chaining `parent · jointOrigin · motion`, so a hood on a turret moves with the turret;
- `Cameras` and `Frames`: `Transform3d` constants for connectors on the robot base, and methods taking `signals` for connectors on a moving mechanism;
- `zeroSignals()` and `jointName(i)`.

**`RobotModelTest`** (JUnit 5) checks the Java against poses cad2ascope computes with numpy: at zero (each pose equals its T0) and at three sample positions inside the limits, for every component and every moving camera or frame. It also checks the fixed constants, and that every pose is finite at every signal limit. `./gradlew test` therefore fails on a stale or broken generated file.

**`RobotVisualizer`** is the PLAN §7.2 template plus `override(double[])` / `clearOverride()`. **`SweepRobotModel`** is a command that moves each signal from its minimum to its maximum and back, one at a time, through that override, for the §10.3 item 3 check in simulation. It changes only what is drawn.

## Verification

- **Formula, independently:** for every fixture and five random signal vectors, the numpy poses equal a separate forward-kinematics walk of `robot.urdf` with the joints moved (scipy rotations), including the turret camera that rides on the turret.
- **WPILib usage:** the generated Java is compiled with `javac -Xlint:all -Werror` against WPILib 2026.2.1 jars and its JUnit test is run, for every fixture. Locally the jars come from the WPILib installer's offline Maven repository. In CI, `scripts/fetch-java-deps.py` downloads the same versions (checking each against its published SHA-1), and `CAD2ASCOPE_REQUIRE_JAVA=1` makes a missing JDK or jar a failure rather than a skip.
- **Templates:** `RobotVisualizer` and `SweepRobotModel` compile against `wpilibj` and `wpilibNewCommands` 2026.2.1. CI also compiles `RobotVisualizer` against AdvantageKit 26.0.2's real `Logger` (`akit-java`, the version in the 2026 robot code's vendordep), where the call resolves to `recordOutput(String, T...)` with `T extends StructSerializable`. Verified 2026-11-25. The WPILib installer's offline repository has no AdvantageKit, so a local run without `scripts/fetch-java-deps.py` falls back to a compile-only stand-in `Logger`.
- **Golden files** for `RobotModel.java` and `RobotModelTest.java` per fixture (`tests/golden/`).
- **Real export:** the 2026 manual export (hood mate renamed to `j_hood` in a scratch copy) generates a `RobotModel` that compiles and passes its 6 tests; the hood signal range comes out as −20° to 0°.

## report.md

The first line is a warning when signals were added or removed since the previous build (robot code will not compile until subsystems change, PLAN §7.3). Then:
- how far each camera and frame moved since the previous build (mm and degrees, flagged above 1 mm or 0.1°);
- optionally, each camera compared with hand-typed values from `cameras.baseline` (pass within 10 mm and 1°, PLAN §10.3 item 7). `spec/camera-baseline.example.yaml` has the 2026 PhotonConfig values;
- the components table, the model size, and the warnings.

Camera names are compared without regard to case, because Onshape lowercases names in the URDF.

## Phase 3 exit criterion (PLAN §11): not met yet

§10.3 items 2, 3 and 7 need the 2026 CAD edits (student sheet) and a branch of `FRC1076/2026-Competition` with the visualizer wired in:

- **Item 2** (zero poses look identical to no poses): needs `cad2ascope render` (Phase 5) or a person comparing in AdvantageScope.
- **Item 3** (sweep stays attached): run `SweepRobotModel` in simulation and watch the replay.
- **Item 7** (CAD cameras vs `PhotonConfig`): point `cameras.baseline` at the example file and read report.md.

## Open points

- **WPILib 2027:** the 2027 robot uses WPILib 2027 and SystemCore. Check whether the geometry classes keep their 2026 package names and constructors when the 2027 robot project exists; the template's imports are the only place to change.
- **Logging (DECISIONS #8):** only the two `recordOutput` lines in `RobotVisualizer` depend on AdvantageKit.
