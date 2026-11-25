# Robot model procedures

The robot's 3D model in AdvantageScope comes straight from the Onshape main assembly, built by [cad2ascope](https://github.com/FRC1076/cad2ascope). These pages cover every task students do with it. Printable one-page versions are in [lab-sheets.html](lab-sheets.html): open it in a browser and print.

| Procedure | Who | How often | Time |
| --- | --- | --- | --- |
| [P1. Season setup](P1-season-setup.md) | Design leads with a programmer | once per robot | about 1 hour |
| [P2. Update the model](P2-update-model.md) | any student | whenever the CAD changes | about 2 minutes of clicks |
| [P3. Add or remove a mechanism](P3-add-mechanism.md) | CAD student and programmer together | when a moving part is added or removed | 15 minutes |
| [P4. View the robot in AdvantageScope](P4-view-model.md) | anyone with AdvantageScope | any time | 5 minutes the first time |
| [P5. Troubleshooting](P5-troubleshooting.md) | whoever hit the problem | as needed | |

What lives where in this repo:

- `cad/advantagescope.yaml`: settings (which mates move, signal names, mesh budget, cameras).
- `cad/drops/`: put a hand-exported Onshape zip here to update without an API key (P2, route B).
- `assets/advantagescope/Robot_*/`: the model AdvantageScope loads. Generated; do not edit.
- `src/main/java/frc/robot/generated/RobotModel.java` and its test: generated; do not edit.
- `src/main/java/frc/robot/visualization/`: `RobotVisualizer` and `SweepRobotModel`, written once and then owned by the software subteam.
