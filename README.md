# cad2ascope

Turn an Onshape robot assembly into an [AdvantageScope](https://github.com/Mechanical-Advantage/AdvantageScope) 3D robot model whose mechanisms move, plus generated WPILib Java that computes the component poses and camera transforms. Built by FRC Team 1076 Pi Hi Samurai; BSD 3-Clause, free for any team to use.

What it replaces is the manual workflow on the [AdvantageScope custom assets page](https://docs.advantagescope.org/more-features/custom-assets/): exporting each mechanism separately, converting files, and tuning `zeroedRotations` and `zeroedPosition` by trial and error. cad2ascope reads every number from the CAD instead.

## What you get

From one Onshape URDF export and a short `cad/advantagescope.yaml`:

- `assets/advantagescope/Robot_<name>/`: `model.glb`, `model_0.glb` and on, and `config.json`. Every component lines up exactly at zero; meshes are reduced to fit a triangle budget (the 1076 pilots: about 300,000 triangles, 13 to 15 MB).
- `RobotModel.java`: a `Signal` enum, `componentPoses(double[] signals)` that chains nested mechanisms (a hood on a turret), and `Cameras` / `Frames` transforms for PhotonVision, all from CAD. It depends only on WPILib geometry, not on a logging library.
- `RobotModelTest.java`, so `./gradlew test` catches a stale or broken model.
- `RobotVisualizer.java` and `SweepRobotModel.java` once, for your team to own.
- `report.md` (camera movement, warnings, sizes) and preview PNGs, ready to be a pull request body.

## Quick start

Needs [uv](https://docs.astral.sh/uv/) (no admin rights). Run from the robot repo's root.

1. Prepare the assembly in Onshape. The rules are short: one Revolute or Slider mate per moving mechanism named `j_…` with limits, a mate connector `ascope_origin` on the drivetrain, `cam_<NAME>` connectors at camera lenses. See [P1 Season setup](templates/robot-repo/docs/robot-model/P1-season-setup.md).
2. Export it: right-click the assembly tab, Export, URDF with GLTF meshes.
3. Look at what was exported, and write a starter config:
   ```
   uvx --from git+https://github.com/FRC1076/cad2ascope cad2ascope inspect export.zip
   uvx --from git+https://github.com/FRC1076/cad2ascope cad2ascope init export.zip --name "1234 2027"
   ```
4. Edit `cad/advantagescope.yaml` (signal names, ratios, directions), then build everything:
   ```
   uvx --from git+https://github.com/FRC1076/cad2ascope cad2ascope run --zip export.zip
   ```
5. In AdvantageScope, choose App > Use Custom Assets Folder and pick `assets/advantagescope`.

With an Onshape API key (read-only is enough), `cad2ascope run` exports the latest Version itself, cached by Version. In GitHub Actions, the [workflow template](templates/robot-repo/.github/workflows/update-robot-model.yml) turns an update into one click that opens a pull request, or accepts a hand-exported zip dropped into `cad/drops/` with no key at all.

## Commands

| Command | What it does |
| --- | --- |
| `inspect <zip>` | Print the joints, limits and parts in an export, plus notes on grounded or unmated parts and cut loops |
| `init <zip>` | Write a starter `cad/advantagescope.yaml` |
| `build <zip>` | Build the AdvantageScope folder, `manifest.json` and `report.md` |
| `codegen <zip>` | Write `RobotModel.java` and its test |
| `fetch` | Export through the Onshape API (keys from `ONSHAPE_ACCESS_KEY` / `ONSHAPE_SECRET_KEY`) |
| `run` | `fetch` (or `--zip`), then `build` and `codegen` |
| `render <folder>` | Preview PNGs and the zero-pose check |
| `ci` | Everything the GitHub Actions workflow runs |

`cad2ascope <command> --help` lists the options. Errors exit 1 and say what to change in Onshape or in the config; warnings exit 0.

## Documentation

- [Student procedures](templates/robot-repo/docs/robot-model/README.md) (P1 to P5) and [printable lab sheets](templates/robot-repo/docs/robot-model/lab-sheets.html), meant to be copied into a robot repo's `docs/`.
- [Implementation plan](docs/PLAN.md) and [decisions](docs/DECISIONS.md).
- How it was verified: [Phase 0 findings](docs/phase0-findings.md) (Onshape export format, AdvantageScope's math, read from its source), [mesh reduction](docs/phase2-results.md), [API fetch](docs/phase4-notes.md), [generated code](docs/phase3-notes.md), [CI](docs/phase5-notes.md).
- [Items that still need a person](docs/HUMAN-CHECKLIST.md).

## Status

Phases 0 to 6 of the [plan](docs/PLAN.md) (code and documentation) are built and tested against synthetic robots and against real exports of 1076's 2025 and 2026 robots. The pilot runs on those robots (Phase 7) are next. Until the first release tag, `main` may change; pin a commit or tag in robot repos.

## Development

```
uv sync
uv run pytest        # also compiles and runs the generated Java if WPILib is installed
uv run ruff check . && uv run ruff format --check .
```

See [CLAUDE.md](CLAUDE.md) for how the code is laid out and the rules it follows.
