# Decisions

Status as of 2026-11-25. Six of twelve are decided, including all three that blocked Phase 0. Claude Code should treat an "Open" item as a question to raise when its phase arrives, not as something to decide alone.

| # | Decision | Owner | Needed by | Status | Answer |
| --- | --- | --- | --- | --- | --- |
| 1 | Who creates and holds the Onshape API key, and the AAPS plan's API call limit | Bill | Phase 0 | Decided | Bill creates and holds a read-only key. No separate limit check; Phase 0 measures calls per run. |
| 2 | Converter repo name and visibility | Bill | Phase 0 | Decided | Public repo `FRC1076/cad2ascope`, BSD 3-Clause, the team standard since 2025 (2025/2026-Competition, SamuraiLib, SamuraiSight). No team document URLs or keys in it. |
| 3 | Owner of the CAD conventions (PLAN §4) | Bill, Design leads | Phase 0 | Decided | Bill and the Design leads, jointly. |
| 4 | Joint list for each pilot robot | Bill, Design leads | Phase 1 | Decided | Bill and the Design leads set the final list before Phase 1. Starting point is PLAN §10.2. |
| 5 | Load-time target for the model on team laptops | Software lead | Phase 2 | Open | Draft target is under 10 seconds. |
| 6 | Plain commits or Git LFS for model files | Software lead | End of Phase 2 | Open | Decide from the real sizes measured in Phase 2. |
| 7 | Articulate swerve module steering (4 more components) or keep modules fixed | Software lead | Phase 3 | Open | |
| 8 | 2027 logging: AdvantageKit `Logger` or WPILib `Telemetry` | Software lead | Phase 3 | Open | Generated `RobotModel.java` stays logging-free either way. |
| 9 | Old match logs available for replay tests | Software lead | Phase 3 | Decided | 2026 logs are available. No 2025 logs, so 2025 is checked with the simulation sweep only. |
| 10 | Which laptops may hold local API keys | Bill | Phase 4 | Open | Draft: mentor-managed laptops only. |
| 11 | AdvantageScope on district MacBooks | Bill, with district IT | Phase 6 | Decided | No AdvantageScope on district MacBooks. Viewing happens on team Windows PCs, personal devices, and mentor or faculty computers. MacBooks trigger and review updates in the browser. |
| 12 | Where the shared AdvantageScope layout file lives | Software lead | Phase 6 | Open | |

Added scope from review: generate PhotonVision robot-to-camera transforms and other measured mount frames from CAD (PLAN §4 C7, §7.4, §10.3 item 7, Phase 3).
