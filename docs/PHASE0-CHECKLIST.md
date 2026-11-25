# Phase 0 checklist: verification spike

Phase 0 writes no product code. It answers the questions the design rests on, records the answers in `docs/phase0-findings.md`, and stops for Bill's review. Expect one to two working sessions.

Inputs you need from Bill before starting:

- [ ] A copy of the 2026 Rebuilt main assembly document, shared with the API key owner. Bill makes the copy, never the original.
- [ ] `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY` in your local environment (read-only key).
- [ ] Optional: a manual URDF export zip of the same assembly, downloaded from the Onshape UI, for comparison.
- [ ] For A5 to A7: Bill or a Design lead edits the copy in the Onshape UI (rename a mate, add connectors, add a relation) and creates a new Version. The API key is read-only, so Claude Code cannot make these edits.

Base URL is `https://aaps.onshape.com`. Enterprise accounts replace `cad` in API URLs with the company domain.

## A. Onshape native URDF export

| # | Question | How to answer | Record |
| --- | --- | --- | --- |
| A1 | Which endpoint and payload export an assembly as URDF with glTF meshes? | API Explorer on aaps.onshape.com; `getAllTranslatorFormats`; try the assembly translation endpoint with `formatName: URDF`, `urdfMeshFormat: GLTF` (from an Onshape staff forum post, March 2026). | Exact request JSON that worked |
| A2 | What are the parameter names for configuration, version vs workspace, mesh resolution, and "export rigid subassemblies as a single link"? | Same, plus the export dialog in the UI for option names. | Parameter table |
| A3 | Does the zip structure match what onshape-to-robot produces? One link per part, or per rigid group? Mesh frame = link frame? | Unzip, read the URDF, open a mesh in a viewer. | Tree printout and notes |
| A4 | Are mates inside flexible subassemblies exported as joints? | Compare the URDF joint list to the moving mechanisms Bill names. | Yes / no / partial, with examples |
| A5 | Do URDF joint names equal Onshape mate names? | Rename one mate to `j_test` in the copy and re-export. | Yes / no, name mangling rules |
| A6 | Are mate connectors exported as frames? Under what names? | Add `ascope_origin` and one `cam_TEST` connector in the copy, re-export. | How frames appear (dummy link, fixed joint, name) |
| A7 | Do Onshape relations become `<mimic>` elements? | Add a linear relation between two sliders in the copy if none exists. | Yes / no, ratio and sign convention |
| A8 | Can an export target a Named Position, or only the current mate values? | API docs and a test export. | Answer, and the fallback if no |
| A9 | Are part colors and appearances kept in the glTF meshes? | Open the meshes. | Yes / no |
| A10 | How long does the export take, how big is the zip, and how many API calls does one run make? | Time it for the 2026 robot, then the 2025 robot. | Seconds, MB, call count |

If A4, A5, or A6 fail, try the same assembly with onshape-to-robot (`dof_` naming) and record the same table. That result decides the export route.

## B. AdvantageScope semantics

Answer from the source at https://github.com/Mechanical-Advantage/AdvantageScope (search for `zeroedRotations`, `zeroedPosition`, and where robot `rotations` are applied in the 3D field renderer).

| # | Question | Record |
| --- | --- | --- |
| B1 | Is a `rotations` sequence applied about fixed (extrinsic) axes or about the already-rotated (intrinsic) axes? In what order? | Rule, with the file and line |
| B2 | Is `position` applied after rotation in the parent frame, as the docs say? | Confirm with file and line |
| B3 | With component poses published, what is the exact composition: robot pose × component pose × zeroed transform × mesh? Are the robot-level `rotations`/`position` also applied to components? | Formula with file and line |
| B4 | With no component poses published, how are component meshes placed? | Formula |
| B5 | How are `cameras` entries interpreted (which axis is the view direction)? | Rule |
| B6 | Any limits on component count or model size, and how `NOSIMPLIFY` and `disableSimplification` behave in the current release? | Notes |

Then write the Python helper that turns a 4x4 transform into the AdvantageScope rotation sequence, and a test that reproduces AdvantageScope's math from B1 to B3 and round-trips 1,000 random transforms within 1e-9.

## C. Decision gate

Write a one-page summary at the top of `docs/phase0-findings.md`:

1. Export route: native URDF or onshape-to-robot, and why.
2. Changes needed to PLAN §4 (CAD conventions) and §6 (converter) given what the exporter really does.
3. Anything that changes the fixtures in `tests/fixtures/` (frame representation, mesh frames, mimic format).
4. Measured export time, size, and API calls.

Stop and ask Bill to review before Phase 1.
