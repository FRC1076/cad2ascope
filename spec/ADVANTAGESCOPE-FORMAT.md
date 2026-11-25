# AdvantageScope robot asset format (summary)

Paraphrased from https://docs.advantagescope.org/more-features/custom-assets/ on 2026-11-25 (2027 docs). Treat the docs and the AdvantageScope source as authoritative. Phase 0 confirms the open points marked below.

## Folder

- One folder per robot named `Robot_<NAME>`. The NAME part is not shown in the app.
- `config.json`, `model.glb` (base robot, no articulated components), and `model_0.glb`, `model_1.glb`, ... (one per articulated component, in the order of the `components` array).
- Models must be binary glTF (`.glb`) with all resources embedded.
- A custom assets folder can be chosen in the app (App > Use Custom Assets Folder). It is the *parent* folder holding `Robot_*` subfolders. The docs suggest this for keeping assets in version control next to robot code.

## config.json fields used by cad2ascope

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | Display name. Must be unique among robot assets. |
| `isFTC` | boolean | Leave false. |
| `disableSimplification` | boolean | Turns off AdvantageScope's automatic model simplification for the whole robot. |
| `rotations` | array of `{axis: "x" \| "y" \| "z", degrees: number}` | Robot-level rotation sequence. cad2ascope writes `[]` because geometry is already in robot frame. |
| `position` | `[x, y, z]` meters | Robot-level offset, applied after rotation. cad2ascope writes `[0, 0, 0]`. |
| `cameras` | array | Fixed camera views: `name`, `rotations`, `position` (meters, robot-relative, after rotation), `resolution` `[w, h]` px, `fov` horizontal degrees. |
| `components` | array | One entry per `model_N.glb`: `zeroedRotations` (same shape as `rotations`) and `zeroedPosition` `[x, y, z]` meters, applied after rotation. |

## Behavior that matters

- Robot origin matches the published robot pose, which usually sits on the floor plane (height zero), not the belly pan.
- With **no** component poses published, component models render using the robot-level rotations and position, so they must be exported in their default positions.
- With component poses published, the zeroed rotations and position move each component to the robot origin, then the published pose places it. Example from the docs: an arm segment's zeroed transform puts its pivot at the origin pointing along +X, and the published pose sits at the joint pointing along the segment.
- Mesh names containing `NOSIMPLIFY` are never removed by automatic simplification.

## Open points for Phase 0 (see PHASE0-CHECKLIST.md, section B)

- Whether a rotation sequence uses fixed or moving axes.
- The exact composition order of robot pose, component pose, zeroed transform, and robot-level transform.
- Which axis a `cameras` entry looks along.
