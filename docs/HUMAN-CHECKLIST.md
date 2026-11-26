# What needs a person

Everything below is blocked on a person, not on code. Status as of 2026-11-25, after Phases 0 to 6 merged. Details for each item follow the checklist.

## Checklist

**CAD (student and Design leads)**
- [ ] 1. Share the CAD prep sheet with the student
- [ ] 2. Make the Onshape edits on the 2026 copy
- [ ] 3. Make the Onshape edits on the 2025 copy
- [ ] 4. Approve the proposed CAD conventions (PLAN §4 C1 to C4)

**Robot repo and robot code (Bill and Software lead)**
- [ ] 5. Set up the workflow in a robot repo (or a test repo) and run it once
- [ ] 6. Wire the visualizer into a branch of the 2026 robot code
- [ ] 7. Run the joint sweep in simulation and watch it
- [ ] 8. Replay 2026 match logs with the model
- [ ] 9. Review the 2026 camera comparison with the vision lead

**Checks on a team laptop**
- [ ] 10. Load the model in AdvantageScope and time it
- [ ] 11. Have a new student follow P2 and P4 without help

**Decisions**
- [ ] 12. Software lead: open decisions #5, #6, #7, #8, #12
- [ ] 13. Bill: decision #10 (which laptops may hold the key)
- [ ] 14. Bill: plan doc or `PLAN.md` as the source of truth (decision #16)
- [ ] 15. Bill: tag a cad2ascope release for robot repos to pin (decision #15)
- [ ] 16. Bill: agree to the camera FOV rule, and optionally report the mismatch upstream (decision #14)

---

## 1. Share the CAD prep sheet with the student

The step-by-step sheet is [Onshape Prep for cad2ascope](https://claude.ai/artifact/VwTk4VQcTpsBsVr2LFaz5b). It is private until you share it from its Share menu. Steps marked "check this" were inferred from the exports, so the student should confirm them in Onshape and report anything that differs.

## 2. Make the Onshape edits on the 2026 copy

Work only in the copy in the Onshape folder `cad2ascope` (its URL is in `private/TEAM-CONTEXT.md`, which is not in the repo).
- Unfix `fixed_turret_plate_neo` so the hood rides on the turret.
- Change the turret's Planar mate to a Revolute `j_turret`.
- Name the hood, slapdown, climber and hook mates `j_…`, with limits.
- Add `ascope_origin`, four `cam_…` connectors and `frame_turret_pivot`.
- Add the `Export` configuration, then pose at `ascope_zero` and create the Version `ascope pilot 1`.

This also answers Phase 0 A5 to A7 (mate names, connectors, relations). See [phase0-findings.md](phase0-findings.md).

## 3. Make the Onshape edits on the 2025 copy

The elevator stages in "Three Stage w Grabber Pivot" are Planar mates. They become Sliders `j_elevator_stage1/2/3`, linked with relations. The pivot becomes `j_grabber_pivot`; both need limits. Also add the origin, the camera connectors (the 2025 CAD has camera mounts but no camera bodies) and the export configuration. The mate table is in [phase0-findings.md](phase0-findings.md) under A4.

## 4. Approve the proposed CAD conventions

[PLAN.md §4](PLAN.md) C1 to C4 carry changes marked "Proposed after Phase 0", learned from the real exports:
- suppress (not hide) what the model leaves out, including game pieces;
- only the drivetrain is Fixed, and every part is mated;
- Revolute or Slider mates only, always with limits;
- Onshape cuts closed loops itself.

Bill and the Design leads own these conventions (DECISIONS #3; open as #13). Once approved, remove the "Proposed" markers and add them to the team's CAD standards.

## 5. Set up the workflow in a robot repo and run it once

This is Phase 5's exit check: PLAN §9 P2 working from a MacBook browser. Follow the setup list in [phase5-notes.md](phase5-notes.md):
- the workflow file from [templates/robot-repo](../templates/robot-repo/.github/workflows/update-robot-model.yml);
- the secrets `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY`, and the variable `ONSHAPE_BASE_URL`;
- the two Actions permission settings;
- `cad/advantagescope.yaml` and `cad/drops/`.

Then run it once from the Actions tab, and once by dropping a zip. Watch the pull request body and its preview images load. It works best after item 2, so there is a Version to export.

The drop route already passed in the test repo [FRC1076/cad2ascope-test-robot](https://github.com/FRC1076/cad2ascope-test-robot) (private; see [phase5-notes.md](phase5-notes.md)). Open its [pull request #1](https://github.com/FRC1076/cad2ascope-test-robot/pull/1) and check that the five preview images display.

## 6. Wire the visualizer into a branch of the 2026 robot code

On a branch of [FRC1076/2026-Competition](https://github.com/FRC1076/2026-Competition), run `cad2ascope run` (or `./gradlew updateRobotModel`, from [updateRobotModel.gradle](../templates/robot-repo/updateRobotModel.gradle)). That writes `RobotModel`, `RobotVisualizer` and `SweepRobotModel`. Then:
- create the visualizer in `RobotContainer`;
- add `visualizer.set(Signal.X, …)` in each subsystem's `periodic()`;
- use `RobotModel.Cameras` in place of the hand-typed `PhotonConfig` transforms once item 9 agrees.

A trial of this for the hood alone worked (2026-11-25). Its six lines of wiring and what to watch for are in [phase3-notes.md](phase3-notes.md), under "Trial on the 2026 robot code".

## 7. Run the joint sweep in simulation and watch it

Schedule `SweepRobotModel` in simulation (with `CommandScheduler.getInstance().schedule(…)`) and open the log in AdvantageScope with the custom assets folder set to `assets/advantagescope`. Every component must stay attached at its joint through its whole range (PLAN §10.3 item 3). The build already checks item 2 automatically, by comparing zero poses against no poses in the previews.

## 8. Replay 2026 match logs with the model

Using the branch from item 6 and AdvantageKit replay, replay real 2026 match logs. Check that the mechanisms move correctly against what happened in the match (PLAN §10.3 item 4). 2025 has no logs, so 2025 relies on item 7 only.

## 9. Review the 2026 camera comparison with the vision lead

Point `cameras.baseline` in the robot repo's config at a copy of [camera-baseline.example.yaml](../spec/camera-baseline.example.yaml) (the current `PhotonConfig` values). The next build's `report.md` then compares each CAD camera against them. Anything beyond 10 mm or 1° needs a reason, traced to either the CAD or the code (PLAN §10.3 item 7). Watch in particular the non-mirrored yaws (50° vs −61°, −147° vs 140°) and the two different rear heights.

## 10. Load the model in AdvantageScope and time it

On a team Windows laptop (not a district MacBook), point AdvantageScope's custom assets folder at the built model and time the load. Also check that it looks right, including transparent panels and bumper numbers. The draft target is under 10 seconds (DECISIONS #5, PLAN §1 criterion 4). The built models are 13 to 15 MB ([phase2-results.md](phase2-results.md)).

## 11. Have a new student follow P2 and P4 without help

A student who did not help build the tool runs "Update the model" and "View the robot in AdvantageScope" from the printed [lab sheets](../templates/robot-repo/docs/robot-model/lab-sheets.html) (PLAN §10.3 item 6), after the sheets are copied into the robot repo. Note anything they get stuck on and fix the procedure.

## 12. Software lead: open decisions

From [DECISIONS.md](DECISIONS.md):
- **#5** load-time target (see item 10);
- **#6** plain commits or Git LFS: each update adds about 13 to 15 MB;
- **#7** whether to animate swerve steering;
- **#8** AdvantageKit `Logger` or WPILib `Telemetry` for 2027 (only two lines in `RobotVisualizer` depend on it);
- **#12** where the shared AdvantageScope layout file lives.

## 13. Bill: decision #10

Decide which laptops may hold the local API key (draft: mentor-managed laptops only), per [DECISIONS.md](DECISIONS.md) #10. The key's owner and creation date are now recorded under decision #1; rotate it each August (PLAN §5).

## 14. Bill: plan doc or `PLAN.md` as the source of truth (decision #16)

The [README](../README.md) leaves open whether the living Claude Doc plan or `docs/PLAN.md` is authoritative. `PLAN.md` has had many Phase 0 to 5 updates since the snapshot. Either copy those changes back into the doc, or retire the doc.

## 15. Bill: tag a cad2ascope release (decision #15)

The workflow template and the Gradle task install cad2ascope from `main` (`CAD2ASCOPE_REF: main`). Before a robot repo depends on it, tag a release (for example `v0.1.0`) and set that tag in both files. Then a later change to `main` cannot break a robot repo mid-season.

## 16. Bill: the camera FOV rule (decision #14)

AdvantageScope's docs describe a camera's `fov` as horizontal, but the renderer uses `fov / aspect` as the vertical FOV, so the view is narrower than documented. cad2ascope compensates (Phase 0 B5, in [phase0-findings.md](phase0-findings.md)). Reporting it to [Mechanical-Advantage/AdvantageScope](https://github.com/Mechanical-Advantage/AdvantageScope) is your call.
