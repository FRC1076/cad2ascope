"""`cad2ascope build`: URDF export + team config -> AdvantageScope robot folder (PLAN §6.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cad2ascope.ascope import config_json, manifest_json, write_json
from cad2ascope.cameras import Camera, Frame, find_cameras, find_frames
from cad2ascope.config import Config, load_config
from cad2ascope.errors import CadError
from cad2ascope.export import load_export
from cad2ascope.grouping import Model, build_model
from cad2ascope.meshes import glb_bytes, place_groups
from cad2ascope.reduce import MeshStats, reduce_groups
from cad2ascope.report import load_baseline
from cad2ascope.report import render as render_report

DEFAULT_OUT = "assets/advantagescope"


@dataclass
class BuildResult:
    folder: Path
    model: Model
    cameras: list[Camera]
    frames: list[Frame]
    files: dict[str, int]  # file name -> bytes
    mesh: MeshStats | None = None
    source_name: str = ""
    source_sha256: str = ""

    @property
    def warnings(self) -> list[str]:
        return list(self.model.warnings)


def analyze(export_path: str | Path, config: Config, repo_root: Path) -> tuple[Model, list[Camera], list[Frame]]:
    """Everything except writing files; also what `codegen` will reuse in Phase 3."""
    with load_export(export_path) as export:
        model = build_model(export.robot, config)
        return model, find_cameras(model, repo_root), find_frames(model)


def build(
    export_path: str | Path,
    config_path: str | Path,
    out_root: str | Path = DEFAULT_OUT,
    repo_root: str | Path = ".",
    onshape_source: dict | None = None,
) -> BuildResult:
    """Build the robot folder. Raises CadError for problems the student must fix; nothing is written in that case."""
    config = load_config(config_path)
    repo_root = Path(repo_root)
    export_path = Path(export_path)
    with load_export(export_path) as export:
        model = build_model(export.robot, config)
        cameras = find_cameras(model, repo_root)
        frames = find_frames(model)
        groups = place_groups(model, export)
        reduced, stats = reduce_groups(groups, config.mesh, model.warnings)
        blobs = {g.file: glb_bytes(g.meshes) for g in reduced}
        sha = export.sha256

    folder = Path(out_root) / config.robot.folder
    if folder.exists() and not folder.is_dir():
        raise CadError(f"{folder} exists and is not a folder. Move it out of the way and run again.")
    baseline = None
    if config.cameras.baseline:
        path = repo_root / config.cameras.baseline
        if not path.is_file():
            raise CadError(f"cameras.baseline points at {path}, which does not exist. Fix the path or remove the line.")
        baseline = load_baseline(path)
    folder.mkdir(parents=True, exist_ok=True)
    previous = None
    if (folder / "manifest.json").is_file():
        try:
            previous = json.loads((folder / "manifest.json").read_text())
        except ValueError:
            previous = None
    # Remove only files this tool writes, so a stale model_5.glb cannot linger after a joint is removed.
    for old in [*folder.glob("model*.glb"), folder / "config.json", folder / "manifest.json", folder / "report.md"]:
        if old.is_file():
            old.unlink()
    for name, data in blobs.items():
        (folder / name).write_bytes(data)
    sizes = {name: len(data) for name, data in blobs.items()}
    write_json(folder / "config.json", config_json(model, cameras))
    manifest = manifest_json(model, cameras, frames, reduced, sizes, export_path.name, sha, stats, onshape_source)
    write_json(folder / "manifest.json", manifest)
    # Render from the JSON round trip, so the report reads exactly what the next run will read back.
    (folder / "report.md").write_text(render_report(json.loads(json.dumps(manifest)), previous, baseline))
    return BuildResult(folder, model, cameras, frames, sizes, stats, export_path.name, sha)
