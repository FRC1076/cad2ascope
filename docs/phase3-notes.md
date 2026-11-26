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
- **WPILib usage:** the generated Java is compiled with `javac -Xlint:all -Werror` against WPILib 2026.2.1 jars and its JUnit test is run, for every fixture. Locally the jars come from the WPILib installer's offline Maven repository. In CI, `scripts/fetch-java-deps.py` downloads the same versions (checking each against its published SHA-1), and `CAD2ASCOPE_REQUIRE_JAVA=1` makes a missing JDK or jar a failure rather than a skip. CI also runs the same tests against WPILib 2027 alpha-8 with JDK 25 (`--wpilib 2027`, `CAD2ASCOPE_REQUIRE_JAVA_2027=1`).
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
- **Item 3** (sweep stays attached): run `SweepRobotModel` in simulation and watch the replay. Done for the hood in the trial below; the other joints wait for the CAD edits.
- **Item 7** (CAD cameras vs `PhotonConfig`): point `cameras.baseline` at the example file and read report.md.

## Trial on the 2026 robot code (2026-11-25)

A dry run of HUMAN-CHECKLIST items 6 and 7 before the CAD edits. It used a local branch of `FRC1076/2026-Competition` (nothing pushed) and the 2026 manual export with the hood mate renamed `j_hood` in a scratch copy. The config listed one joint, `j_hood: {signal: hood, direction: -1}`.

**Wiring took six lines:**
- `RobotContainer` creates one `RobotVisualizer` and passes it to `HoodSubsystem`'s constructor;
- `HoodSubsystem.periodic()` calls `visualizer.set(Signal.HOOD, inputs.angleRadians)` right after `Logger.processInputs`;
- in simulation only, `RobotContainer` schedules the sweep with `CommandScheduler.getInstance().schedule(new SweepRobotModel(m_visualizer))`. `Command.schedule()` is deprecated for removal in WPILib 2026, and `-Werror` builds would fail on it.

**Results:**
- `./gradlew build` passes, and it runs the generated `RobotModelTest` (the robot project already has JUnit 5).
- In `./gradlew simulateJava`, the sweep logged 200 hood poses (4 s at one per loop), from 0° to 20° and back. Each pose matches cad2ascope's own kinematics (`render.component_poses`) to within 6e-5. A close-up render at 0°, 10° and 20° shows the hood turning about its pivot and staying attached (§10.3 item 3, for the hood only).
- The moving hood component has 63 parts, including its wheels, belts and 300-tooth gear.

**Found and fixed:** `SweepRobotModel` used the clock. The simulator's first loops take about 2 s, so the first run drew only the second half of the sweep. The template now advances one 20 ms loop per call. This affects only new robot repos, since the file is written once.

**For the pilot:**
- **Hood direction is a guess.** The code's hood angle runs 0 to 0.25 rad (soft stops in `HoodConstants`), and the CAD limits are −20° to 0°. So `direction: -1` was assumed. Confirm it on the robot or in a match log: hood up should look up.
- **The CAD range (20°) is wider than the code's soft stops (14.3°).** This is not wrong, but the sweep shows positions the robot never reaches.
- **The robot code's `SystemConstants.kMode` is `REAL`.** So `simulateJava` uses the real IO layers. In `SIM` mode, AdvantageKit only publishes to NetworkTables and writes no log file. Watch the sweep live by connecting AdvantageScope to the simulator, or add a `WPILOGWriter` to the `SIM` branch of `Robot.java` (the trial did both: `SIM` mode plus a writer, and a headless simulator).

## Open points

- **WPILib 2027:** checked against 2027 alpha-8 (2026-11-26, `docs/readiness-checks.md` §1). The packages moved from `edu.wpi.first` to `org.wpilib`, `TimedRobot.kDefaultPeriod` became `DEFAULT_PERIOD`, and Java 25 is required. With those renamed, every fixture's generated test passes. `codegen.wpilib: 2027` now writes the 2027 names, and CI tests both years.
- **Logging (DECISIONS #8):** only the two `recordOutput` lines in `RobotVisualizer` depend on AdvantageKit.
