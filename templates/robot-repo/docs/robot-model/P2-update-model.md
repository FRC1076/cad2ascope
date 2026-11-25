# P2. Update the model

**Who:** any student. **When:** whenever the robot changes in Onshape. **Time:** about 2 minutes of clicks, then 5 to 15 minutes of waiting.

## Route A: Run workflow (normal)

1. In Onshape, put the robot in the `ascope_zero` Named Position, and create a **Version** with a clear name, like "Week 4, new intake plates".
2. In the robot repo on GitHub, open **Actions**, choose **Update robot model**, and click **Run workflow**. Leave the boxes empty to use the newest Version, or type a Version name.
3. Wait for the run to finish. It opens or updates a pull request named "Update robot model from Onshape version …" on the branch `robot-model/update`.
4. Open the pull request and read it from the top:
   - If the first line says **Robot code changes needed**, a mechanism was added or removed. Do [P3](P3-add-mechanism.md).
   - Look at the preview images. Every mechanism should be attached and in the right place.
   - Check that the **zero-pose check** says Pass.
   - Read the camera table. Any camera that moved needs a look from the vision lead.
   - Read the warnings.
5. Ask the software lead or a mentor to review and merge. Nothing merges by itself.

## Route B: drop a zip (no API key needed)

1. In Onshape, select the `AdvantageScope` configuration and the `ascope_zero` position. Right-click the assembly tab, choose **Export**, pick **URDF**, geometry **GLTF**, resolution **Medium**, and download the zip.
2. On GitHub, make a new branch, open `cad/drops/`, and choose **Add file > Upload files**. Upload the zip (exactly one) and commit it to your branch.
3. The workflow runs by itself. When it finishes, it has replaced your zip with the new model on your branch. The report is on the run's summary page in Actions.
4. Open a pull request from your branch and ask for a review.

If the run fails, open it in **Actions**, find the step marked with a red X, and look up the message in [P5](P5-troubleshooting.md).
