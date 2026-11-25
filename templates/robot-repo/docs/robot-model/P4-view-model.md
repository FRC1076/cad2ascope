# P4. View the robot in AdvantageScope

**Who:** anyone. **Where:** a team Windows PC, a personal device, or a mentor or faculty computer. District MacBooks do not have AdvantageScope. **Time:** 5 minutes the first time.

1. Pull the latest robot code (or download the repo), so you have the newest `assets/advantagescope` folder.
2. In AdvantageScope, choose **App > Use Custom Assets Folder** and select the repo's `assets/advantagescope` folder. You only do this once per computer.
3. Open a log file or connect to the robot or simulator.
4. Add a **3D Field** tab. Choose this season's robot model from the robot list.
5. Drag the robot's pose onto the field: the `Pose2d` or `Pose3d` the drive code logs (ask the software lead for its name).
6. Drag `RobotModel/Measured` onto that robot as its **components**. The mechanisms now move with the logged positions.
7. Optional: drag the robot pose on again as a **ghost**, and give it `RobotModel/Setpoint` as components to see where each mechanism is trying to go.
8. Camera views: in the 3D field's camera menu, each `cam_` connector appears as a fixed camera view. Compare it with the PhotonVision stream to catch a wrong mount angle.

Save the layout so the next person can skip steps 4 to 7. Where the shared layout file lives is still being decided (decision #12).
