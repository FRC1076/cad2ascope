# Decisions

Status as of 2026-11-25 (end of day, after Phases 0 to 6 merged). Six of twelve original decisions are decided; four more (#13 to #16) came up during the build and are open. Claude Code should treat an "Open" item as a question to raise when its phase arrives, not as something to decide alone.

| # | Decision | Owner | Needed by | Status | Answer |
| --- | --- | --- | --- | --- | --- |
| 1 | Who creates and holds the Onshape API key, and the AAPS plan's API call limit | Bill | Phase 0 | Decided | Bill creates and holds a read-only key. No separate limit check; Phase 0 measures calls per run. Key created 2026-11-25 (read access only), held by Bill. Measured: one export is 11 API calls, and a re-run on the same Version is 1. Rotate each August (PLAN §5). |
| 2 | Converter repo name and visibility | Bill | Phase 0 | Decided | Public repo `FRC1076/cad2ascope`, BSD 3-Clause, the team standard since 2025 (2025/2026-Competition, SamuraiLib, SamuraiSight). No team document URLs or keys in it. |
| 3 | Owner of the CAD conventions (PLAN §4) | Bill, Design leads | Phase 0 | Decided | Bill and the Design leads, jointly. |
| 4 | Joint list for each pilot robot | Bill, Design leads | Phase 1 | Decided | Bill and the Design leads set the final list before Phase 1. Starting point is PLAN §10.2. The CAD prep sheet proposes `j_turret`, `j_hood`, `j_slapdown`, `j_climber`, `j_hook` (2026) and `j_elevator_stage1/2/3`, `j_grabber_pivot` (2025), inferred from the exports; the student confirms them in Onshape. |
| 5 | Load-time target for the model on team laptops | Software lead | Phase 2 | Open | Draft target is under 10 seconds. The pilot models are 13 to 15 MB (`docs/phase2-results.md`). On an Apple M5 Mac, AdvantageScope's loader takes about 0.16 s per model (`docs/readiness-checks.md` §4); a team laptop is still to be measured. |
| 6 | Plain commits or Git LFS for model files | Software lead | End of Phase 2 | Open | Decide from the real sizes measured in Phase 2. Measured: about 13 MB (2026) and 15 MB (2025) per update, plus about 0.1 to 1 MB of preview PNGs; an unchanged robot rebuilds to identical files. |
| 7 | Articulate swerve module steering (4 more components) or keep modules fixed | Software lead | Phase 3 | Open | In both pilot CADs the modules are placed with Planar mates, so they are frozen today; animating steering would need a Revolute mate per module. |
| 8 | 2027 logging: AdvantageKit `Logger` or WPILib `Telemetry` | Software lead | Phase 3 | Open | Generated `RobotModel.java` stays logging-free either way. Both options compile against WPILib 2027 alpha-8 (`docs/readiness-checks.md` §3). |
| 9 | Old match logs available for replay tests | Software lead | Phase 3 | Decided | 2026 logs are available. No 2025 logs, so 2025 is checked with the simulation sweep only. |
| 10 | Which laptops may hold local API keys | Bill | Phase 4 | Open | Draft: mentor-managed laptops only. |
| 11 | AdvantageScope on district MacBooks | Bill, with district IT | Phase 6 | Decided | No AdvantageScope on district MacBooks. Viewing happens on team Windows PCs, personal devices, and mentor or faculty computers. MacBooks trigger and review updates in the browser. |
| 12 | Where the shared AdvantageScope layout file lives | Software lead | Phase 6 | Open | P4 tells students to save the layout and points here. |
| 13 | Approve the CAD conventions proposed after Phase 0 (PLAN §4 C1 to C4: suppress, not hide; only the drivetrain Fixed; Revolute or Slider only, with limits; Onshape cuts loops) | Bill, Design leads | Phase 7 | Open | The student prep sheet and P1 already state them as rules. |
| 14 | Camera `fov` written as aspect × true vertical FOV, because AdvantageScope divides `fov` by the aspect ratio despite its docs (Phase 0 B5) | Bill | Phase 7 | Open | Built that way. Reporting the mismatch to AdvantageScope is optional. Still unchanged in v26.0.2 and v27.0.0-beta-1, and no upstream issue exists (2026-11-26). |
| 15 | Release tag for robot repos to pin (`CAD2ASCOPE_REF` in the workflow and Gradle task) | Bill | Before the first robot repo uses the workflow | Open | Both currently install from `main`. |
| 16 | Source of truth for the plan: the Claude Doc or `docs/PLAN.md` | Bill | Any time | Open | `PLAN.md` has many as-built updates since the snapshot. |

Added scope from review: generate PhotonVision robot-to-camera transforms and other measured mount frames from CAD (PLAN §4 C7, §7.4, §10.3 item 7, Phase 3).
