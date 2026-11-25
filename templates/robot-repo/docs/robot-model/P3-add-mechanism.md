# P3. Add or remove a mechanism

**Who:** a CAD student and a programmer together. **When:** a moving part is added, removed, or renamed. **Time:** about 15 minutes.

Adding or removing a moving mechanism changes the list of signals robot code must provide. The build breaks on purpose until the code catches up, so nobody forgets to wire the new mechanism in.

1. **CAD student:** add or rename the mate as a Revolute or Slider named `j_…` with limits (P1, step A4). Put the robot at `ascope_zero` and create a Version.
2. **Programmer:** in `cad/advantagescope.yaml`, add the joint under `joints` and its signal under `signals` (or remove both). Commit to a branch.
3. Run [P2](P2-update-model.md) Route A. The pull request's first line says **Robot code changes needed** and names the signal. Its `./gradlew test` check fails. That is expected.
4. **Programmer:** check out `robot-model/update`. In the subsystem that owns the mechanism, add `visualizer.set(Signal.NEW_NAME, positionInMetersOrRadians)` in `periodic()` (or delete the call for a removed signal). Push to the same branch.
5. When `./gradlew test` passes, the pull request goes green. Ask for a review and merge.
