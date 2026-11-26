# What needs a person

Status as of 2026-11-26, after Phases 0 to 6 merged and the follow-up checks in pull requests #9 to #12. Everything below is blocked on a person, not on code: what could be done without one is done.

## Where to start

Most items wait on items 1 and 2. The Onshape edits on the 2026 copy unblock:
- the Onshape route in CI (5);
- the full robot-code wiring (6);
- the sweep check (7);
- match-log replay (8);
- the camera review (9);
- Phase 0's last two answers.

Tag a release (15) before any robot repo depends on the workflow. The decisions (12 to 16) can be made any time.

## Checklist

**CAD (student and Design leads)**
- [ ] 1. Share the CAD prep sheet with the student
- [ ] 2. Make the Onshape edits on the 2026 copy
- [ ] 3. Make the Onshape edits on the 2025 copy
- [ ] 4. Approve the proposed CAD conventions (PLAN §4 C1 to C4)

**Robot repo and robot code (Bill and Software lead)**
- [ ] 5. Add the Onshape secrets to a robot repo (or the test repo) and run the workflow from the Actions tab; the drop route already passes
- [ ] 6. Wire the visualizer into a branch of the 2026 robot code; the hood alone already works
- [ ] 7. Run the joint sweep in simulation and watch it; the hood alone already passes
- [ ] 8. Replay 2026 match logs with the model
- [ ] 9. Review the 2026 camera comparison with the vision lead

**Checks on a team laptop**
- [ ] 10. Load the model in AdvantageScope on a team laptop and time it
- [ ] 11. Have a new student follow P2 and P4 without help

**Decisions**
- [ ] 12. Software lead: open decisions #5, #6, #7, #8, #12
- [ ] 13. Bill: decision #10 (which laptops may hold the key)
- [ ] 14. Bill: plan doc or `PLAN.md` as the source of truth (decision #16)
- [ ] 15. Bill: tag a cad2ascope release for robot repos to pin (decision #15)
- [ ] 16. Bill: agree to the camera FOV rule, and optionally report the mismatch upstream (decision #14)

**At and after the 2027 kickoff**
- [ ] 17. Set up the 2027 robot repo with `wpilib: 2027` under `codegen`
- [ ] 18. Ask for the WPILib 2027 pin to be updated when a new alpha, beta or the release comes out

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

This also answers Phase 0 A6 and A7 (mate connectors, relations). See [phase0-findings.md](phase0-findings.md).

## 3. Make the Onshape edits on the 2025 copy

The elevator stages in "Three Stage w Grabber Pivot" are Planar mates.
- **Elevator:** the stages become Sliders `j_elevator_stage1/2/3`, linked with relations.
- **Pivot:** it becomes `j_grabber_pivot`.
- **Limits:** the stages and the pivot all need mate limits.
- **Also add:**
  - the origin;
  - the camera connectors (the 2025 CAD has camera mounts but no camera bodies);
  - the export configuration.

The mate table is in [phase0-findings.md](phase0-findings.md) under A4.

## 4. Approve the proposed CAD conventions

[PLAN.md §4](PLAN.md) C1 to C4 carry changes marked "Proposed after Phase 0", learned from the real exports:
- suppress (not hide) what the model leaves out, including game pieces;
- only the drivetrain is Fixed, and every part is mated;
- Revolute or Slider mates only, always with limits;
- Onshape cuts closed loops itself.

Bill and the Design leads own these conventions (DECISIONS #3; open as #13). Once approved, remove the "Proposed" markers and add them to the team's CAD standards.

## 5. Run the workflow's Onshape route

This is the rest of Phase 5's exit check: PLAN §9 P2 working from a MacBook browser.

**Already done (2026-11-25 and 26):** in the test repo [FRC1076/cad2ascope-test-robot](https://github.com/FRC1076/cad2ascope-test-robot) (private), both drop routes pass, and its [pull request #1](https://github.com/FRC1076/cad2ascope-test-robot/pull/1) shows the five preview images. See [phase5-notes.md](phase5-notes.md).

**What is left needs a person:**
- Add the secrets `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY` and the variable `ONSHAPE_BASE_URL` to the repo. Use the read-only key, and enter it yourself.
- Set `robot.onshape_url` in its `cad/advantagescope.yaml`.
- Run the workflow once from the Actions tab. That checks the Onshape route and the export cache.
- Have a student run P2 from a MacBook browser.

This works best after item 2, so there is a Version to export. For a new robot repo, the full setup list is in [P1-season-setup.md](../templates/robot-repo/docs/robot-model/P1-season-setup.md), part B, step 7.

## 6. Wire the visualizer into a branch of the 2026 robot code

**Already done (2026-11-25):** a trial with the hood alone, on a local branch of [FRC1076/2026-Competition](https://github.com/FRC1076/2026-Competition) that was not pushed. Its six lines of wiring and what to watch for are in [phase3-notes.md](phase3-notes.md), under "Trial on the 2026 robot code".

**After item 2**, on a branch of the 2026 code, run `cad2ascope run` (or `./gradlew updateRobotModel`, from [updateRobotModel.gradle](../templates/robot-repo/updateRobotModel.gradle)). Then:
- create the visualizer in `RobotContainer`;
- add `visualizer.set(Signal.X, …)` in each subsystem's `periodic()`;
- use `RobotModel.Cameras` in place of the hand-typed `PhotonConfig` transforms once item 9 agrees;
- confirm the hood direction. `direction: -1` was a guess: hood up should look up.

## 7. Run the joint sweep in simulation and watch it

Schedule `SweepRobotModel` in simulation (with `CommandScheduler.getInstance().schedule(…)`) and open the log in AdvantageScope, with the custom assets folder set to `assets/advantagescope`. Every component must stay attached at its joint through its whole range (PLAN §10.3 item 3).
- **Already passes:** the hood alone.
- **Waits on item 2:** the turret, slapdown, climber and hooks.

The build already checks item 2 of §10.3 automatically, by comparing zero poses against no poses in the previews.

## 8. Replay 2026 match logs with the model

Using the branch from item 6 and AdvantageKit replay, replay real 2026 match logs. Check that the mechanisms move correctly against what happened in the match (PLAN §10.3 item 4). 2025 has no logs, so 2025 relies on item 7 only.

## 9. Review the 2026 camera comparison with the vision lead

Point `cameras.baseline` in the robot repo's config at a copy of [camera-baseline.example.yaml](../spec/camera-baseline.example.yaml), which holds the current `PhotonConfig` values. The next build's `report.md` then compares each CAD camera against them. Anything beyond 10 mm or 1° needs a reason, traced to either the CAD or the code (PLAN §10.3 item 7).

Watch in particular:
- the non-mirrored yaws (50° vs −61°, −147° vs 140°);
- the two different rear heights.

This needs the `cam_…` connectors from item 2.

## 10. Load the model in AdvantageScope on a team laptop and time it

**Already done (2026-11-26):** on an Apple M5 Mac, AdvantageScope v26.0.2's own model loader takes about 0.16 s per robot ([readiness-checks.md](readiness-checks.md) §4). So the 10-second draft target (DECISIONS #5, PLAN §1 criterion 4) looks comfortable.

**Still needed:** a team Windows laptop, not a district MacBook. Point AdvantageScope's custom assets folder at the built model and time the load from opening the 3D tab to seeing the robot. Also check that the model looks right, including the transparent panels and bumper numbers. The built models are 13 to 15 MB ([phase2-results.md](phase2-results.md)).

## 11. Have a new student follow P2 and P4 without help

A student who did not help build the tool runs "Update the model" and "View the robot in AdvantageScope" from the printed [lab sheets](../templates/robot-repo/docs/robot-model/lab-sheets.html) (PLAN §10.3 item 6), after the sheets are copied into the robot repo. Note anything they get stuck on and fix the procedure.

## 12. Software lead: open decisions

From [DECISIONS.md](DECISIONS.md):
- **#5 load-time target:** the Mac measurement is in; the team laptop measurement is item 10.
- **#6 plain commits or Git LFS:** each update adds about 13 to 15 MB.
- **#7 whether to animate swerve steering.**
- **#8 AdvantageKit `Logger` or WPILib `Telemetry` for 2027:** both compile against WPILib 2027 alpha-8. The generated 2027 `RobotVisualizer` uses AdvantageKit, and its header comment gives the two `Telemetry` lines to swap in ([readiness-checks.md](readiness-checks.md) §3).
- **#12 where the shared AdvantageScope layout file lives.**

## 13. Bill: decision #10

Decide which laptops may hold the local API key (draft: mentor-managed laptops only), per [DECISIONS.md](DECISIONS.md) #10. The key's owner and creation date are now recorded under decision #1; rotate it each August (PLAN §5).

## 14. Bill: plan doc or `PLAN.md` as the source of truth (decision #16)

The [README](../README.md) leaves open whether the living Claude Doc plan or `docs/PLAN.md` is authoritative. `PLAN.md` has had many updates through 2026-11-26 since the snapshot. Either copy those changes back into the doc, or retire the doc.

## 15. Bill: tag a cad2ascope release (decision #15)

The workflow template and the Gradle task install cad2ascope from `main` (`CAD2ASCOPE_REF: main`). Before a robot repo depends on it, tag a release (for example `v0.1.0`) and set that tag in both files. Then a later change to `main` cannot break a robot repo mid-season.

## 16. Bill: the camera FOV rule (decision #14)

AdvantageScope's docs describe a camera's `fov` as horizontal, but the renderer uses `fov / aspect` as the vertical FOV, so the view is narrower than documented. cad2ascope compensates (Phase 0 B5, in [phase0-findings.md](phase0-findings.md)).
- **Still true** in AdvantageScope v26.0.2 and v27.0.0-beta-1.
- **Not reported upstream:** no issue about it exists yet ([readiness-checks.md](readiness-checks.md) §2).

Reporting it to [Mechanical-Advantage/AdvantageScope](https://github.com/Mechanical-Advantage/AdvantageScope) is your call.

## 17. Set up the 2027 robot repo with `wpilib: 2027`

At kickoff, follow [P1-season-setup.md](../templates/robot-repo/docs/robot-model/P1-season-setup.md) for the 2027 robot. WPILib 2027 renamed its Java packages, so add `wpilib: 2027` under `codegen` in `cad/advantagescope.yaml`. Without it, the generated code will not compile.

## 18. Ask for the WPILib 2027 pin to be updated

cad2ascope's CI tests the generated code against WPILib 2027 alpha-8 (`scripts/fetch-java-deps.py`). When WPILib publishes a newer alpha, a beta, or the 2027 release, ask Claude Code to move the pin and rerun the tests. A rename like the one in alpha-8 then shows up in cad2ascope's CI, not in the robot code.
