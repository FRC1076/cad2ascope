# P5. Troubleshooting

Find the message, or the symptom, and do what the right column says. Errors stop the run; warnings let it finish but should be fixed. Every message names the mate or part involved.

## Messages from cad2ascope

| Message contains | What it means | Fix |
| --- | --- | --- |
| `is not in the export. Add a mate connector named` | The `ascope_origin` connector is missing or on a suppressed part | Add it on the drivetrain (P1 A2) and create a new Version |
| `exports as several joints (Planar, Cylindrical, Parallel, or` | A `j_` mate is a Planar, Cylindrical, Parallel, or Ball mate | Change it to a Revolute or Slider mate |
| `Change it to Revolute or Slider in Onshape` | A listed `j_` mate is Fastened (or another type that cannot move) | Change the mate type, or remove it from `cad/advantagescope.yaml` |
| `is grounded (Fixed) in Onshape` | A part that is not on the drivetrain is Fixed, so things mounted on it stop moving with their mechanism | Unfix it and mate it (P1 A3) |
| `are not mated to anything` | Some parts have no mates, so they stay stuck to the base | Mate them (Fastened is fine) or suppress them in `AdvantageScope` |
| `closed loop(s) of mates to export a tree` | Onshape cut closed loops; a mechanism may come apart when it moves | Fasten all but one joint of the loop in `AdvantageScope` (P1 A5) |
| `can move in Onshape but is not a j_ mate` | A mate moves in CAD but is frozen in the model | Expected for mates you do not animate; otherwise rename it `j_…` and add it to the config |
| `Did you mean` | A joint name in the config does not match any mate | Fix the spelling in `cad/advantagescope.yaml` or in Onshape |
| `turns, so its signal must be in rad` | A joint and its signal disagree on units | Use `rad` for Revolutes and `m` for Sliders under `signals` |
| `has no mate limits` | A `j_` mate has no limits | Set limits on the mate in Onshape |
| `was exported outside its own mate limits` | The robot was not at `ascope_zero` when the Version was made | Pose at `ascope_zero` and create a new Version |
| `has no Versions yet` | The document has no Version to export | Create a Version (P2 A1), or run with the workspace box ticked for a preview |
| `There is no Version named` | The Version name typed in Run workflow (or in the config) is wrong | Check the name in Onshape's version history |
| `rejected the API key` | The repo's Onshape key is wrong or expired | A mentor updates the repository secrets |
| `could not open the document` | Wrong URL, or the document is not shared with the key's owner | Check `robot.onshape_url`; share the document |
| `could not export the assembly as URDF` | Onshape failed to export | Fix red errors in the assembly's feature list, then make a new Version |
| `Drop one Onshape export at a time` | More than one zip is in `cad/drops/` | Delete the extra zips on your branch and push |
| `over mesh.triangle_budget` | The model is too detailed to load fast | Add patterns to `mesh.exclude_names`; `manifest.json` lists the largest parts |
| `Robot code changes needed` | A mechanism was added or removed | Do [P3](P3-add-mechanism.md) |

## Symptoms

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| A mechanism does not move | Its mate has no `j_` prefix, is not in the config, or rides on a grounded part | Check the run's warnings; rename the mate and add it to the config |
| A mechanism moves the wrong way | CAD and code disagree on direction | Set `direction: -1` for that joint |
| A mechanism is offset at zero | The Version was not made at `ascope_zero`, or code zero differs from CAD zero | Re-export from `ascope_zero`, or set `zero_offset_deg` / `zero_offset_m` |
| A mechanism comes apart when it moves | A closed loop was cut by Onshape | Fasten all but one joint of the loop (P1 A5) |
| Zero-pose check is not Pass | A component would jump when poses are published | Pose at `ascope_zero`, make a new Version, rerun |
| Model loads slowly or parts are missing | Too many triangles, or small parts dropped | Tune `mesh.triangle_budget`, `mesh.exclude_names`, `mesh.keep_detail` |
| A camera moved a lot in the report | The `cam_` connector or the camera mount changed in CAD | Check with the vision lead before merging |
| The pull request fails `./gradlew test` | A joint or signal changed | Do [P3](P3-add-mechanism.md) |
