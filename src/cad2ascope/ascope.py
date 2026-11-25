"""Write AdvantageScope's config.json and cad2ascope's manifest.json (PLAN §6.4 step 8).

Numbers are rounded to 1e-9 (meters and degrees) so files are stable across runs and platforms; that is far below
anything visible and well inside the 1e-6 m tolerance in PLAN §10.1.
"""

from __future__ import annotations

import json
from pathlib import Path

from cad2ascope import __version__
from cad2ascope.cameras import Camera, Frame
from cad2ascope.grouping import Model
from cad2ascope.meshes import GroupMesh
from cad2ascope.transforms import to_config, zeroed_config

DIGITS = 9


def _num(x: float) -> float:
    v = round(float(x), DIGITS)
    return 0.0 if v == 0 else v  # no "-0.0" in the files


def _rotations(seq) -> list[dict]:
    return [{"axis": s["axis"], "degrees": _num(s["degrees"])} for s in seq]


def _matrix(m) -> list[list[float]]:
    return [[_num(v) for v in row] for row in m]


def config_json(model: Model, cameras: list[Camera]) -> dict:
    """AdvantageScope config.json. Geometry is already in robot frame, so robot-level rotations/position are identity."""
    cams = []
    for cam in cameras:
        rot, pos = to_config(cam.T)
        cams.append(
            {
                "name": cam.name,
                "rotations": _rotations(rot),
                "position": [_num(v) for v in pos],
                "resolution": [int(cam.resolution[0]), int(cam.resolution[1])],
                "fov": _num(cam.fov_deg),
            }
        )
    comps = []
    for comp in model.components:
        rot, pos = zeroed_config(comp.T0)
        comps.append({"zeroedRotations": _rotations(rot), "zeroedPosition": [_num(v) for v in pos]})
    return {
        "name": model.config.robot.name,
        "isFTC": False,
        "disableSimplification": False,
        "rotations": [],
        "position": [0.0, 0.0, 0.0],
        "cameras": cams,
        "components": comps,
    }


def manifest_json(
    model: Model,
    cameras: list[Camera],
    frames: list[Frame],
    groups: list[GroupMesh],
    sizes: dict[str, int],
    source_name: str,
    source_sha256: str,
) -> dict:
    """Record of what made this model. No timestamps, so an unchanged input gives an unchanged file."""
    cfg = model.config
    by_file = {g.file: g for g in groups}
    base = by_file["model.glb"]
    return {
        "tool": "cad2ascope",
        "tool_version": __version__,
        "source": {
            "input": source_name,
            "sha256": source_sha256,
            "onshape_url": cfg.robot.onshape_url,
            "configuration": cfg.robot.configuration,
            "version": cfg.robot.version,
        },
        "robot": {"name": cfg.robot.name, "folder": cfg.robot.folder, "origin_frame": cfg.robot.origin_frame},
        "base": {"file": base.file, "links": base.links, "triangles": base.triangles, "bytes": sizes[base.file]},
        "components": [
            {
                "index": c.index,
                "file": c.file,
                "joint": c.joint.name,
                "type": c.joint.type,
                "signal": c.config.signal,
                "ratio": c.config.ratio,
                "direction": c.config.direction,
                "parent_component": c.parent,
                "axis": [_num(v) for v in c.joint.axis],
                "limits": [c.joint.lower, c.joint.upper] if c.joint.type != "continuous" else None,
                "T0": _matrix(c.T0),
                "links": c.links,
                "triangles": by_file[c.file].triangles,
                "bytes": sizes[c.file],
            }
            for c in model.components
        ],
        "frozen_joints": [j.name for j in model.frozen],
        "cameras": [
            {
                "name": cam.name,
                "link": cam.link,
                "component": cam.component,
                "resolution": list(cam.resolution),
                "fov_written": _num(cam.fov_deg),
                "hfov_true": _num(cam.hfov_deg),
                "source": cam.source,
                "T": _matrix(cam.T),
            }
            for cam in cameras
        ],
        "frames": [{"name": f.name, "link": f.link, "component": f.component, "T": _matrix(f.T)} for f in frames],
        "triangles_total": sum(g.triangles for g in groups),
        "warnings": list(model.warnings),
    }


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")
