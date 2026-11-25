"""report.md: the summary a person reads before merging a model update (PLAN §6.4 step 8, §7.3, §7.4, §10.3 item 7).

Order matters. The first lines say whether robot code will stop compiling (a joint or signal was added or removed),
then how far each camera moved, because a moved camera silently changes every vision pose estimate.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import yaml

from cad2ascope.errors import CadError

TOLERANCE_MM = 10.0  # PLAN §10.3 item 7
TOLERANCE_DEG = 1.0
INCH = 0.0254


def _matrix(m) -> np.ndarray:
    return np.array(m, dtype=float)


def _delta(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """(distance in mm, rotation angle in degrees) between two 4x4 transforms."""
    dist = float(np.linalg.norm(a[:3, 3] - b[:3, 3])) * 1000.0
    r = a[:3, :3].T @ b[:3, :3]
    angle = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(r) - 1.0) / 2.0))))
    return dist, angle


def load_baseline(path: Path) -> dict[str, np.ndarray]:
    """Hand-typed camera transforms: NAME: {x, y, z (inches), roll, pitch, yaw (degrees)}, as in PhotonConfig.

    Rotation follows WPILib's Rotation3d(roll, pitch, yaw): about fixed X, then Y, then Z.
    """
    try:
        data = yaml.safe_load(path.read_text()) or {}
        out = {}
        for name, v in data.items():
            roll, pitch, yaw = (math.radians(float(v[k])) for k in ("roll", "pitch", "yaw"))
            cr, sr, cp, sp, cy, sy = (
                math.cos(roll),
                math.sin(roll),
                math.cos(pitch),
                math.sin(pitch),
                math.cos(yaw),
                math.sin(yaw),
            )
            rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
            ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
            rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
            t = np.eye(4)
            t[:3, :3] = rz @ ry @ rx
            t[:3, 3] = [float(v["x"]) * INCH, float(v["y"]) * INCH, float(v["z"]) * INCH]
            out[str(name).upper()] = t
        return out
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError, AttributeError):
        raise CadError(
            f"{path} is not a camera baseline cad2ascope can read. Each entry needs x, y, z in inches and roll, "
            "pitch, yaw in degrees, for example: FRONT_LEFT: {x: 9.278, y: 12.916, z: 9.168, roll: 0, pitch: 20, yaw: 50}"
        ) from None


def _signals(manifest: dict) -> list[str]:
    return list(manifest.get("signals") or [])


def render(manifest: dict, previous: dict | None, baseline: dict[str, np.ndarray] | None = None) -> str:
    lines: list[str] = []
    src = manifest["source"]
    onshape = src.get("onshape") or {}
    if onshape.get("kind") == "version":
        what = f"Onshape version **{onshape.get('version_name')}**"
    elif onshape.get("kind") == "workspace":
        what = "the Onshape **workspace** (preview, not a Version)"
    else:
        what = f"`{src['input']}`"

    # 1. Will robot code still compile?
    if previous is not None:
        old, new = set(_signals(previous)), set(_signals(manifest))
        added, removed = sorted(new - old), sorted(old - new)
        if added or removed:
            parts = []
            if added:
                parts.append("added " + ", ".join(f"`{s}`" for s in added))
            if removed:
                parts.append("removed " + ", ".join(f"`{s}`" for s in removed))
            lines.append(
                f"> **Robot code changes needed:** signals {'; '.join(parts)}. The build will fail until each "
                "subsystem calls `visualizer.set(...)` for the new signals and drops the removed ones (PLAN §9 P3)."
            )
            lines.append("")
    lines.append(f"# Robot model update: {manifest['robot']['name']}")
    lines.append("")
    lines.append(f"Built from {what} by cad2ascope {manifest['tool_version']}.")
    lines.append("")

    # 2. Cameras and frames
    def section(kind: str, key: str):
        new = {c["name"].upper(): c for c in manifest.get(key, [])}
        old = {c["name"].upper(): c for c in (previous or {}).get(key, [])}
        if not new and not old:
            return
        lines.append(f"## {kind}")
        lines.append("")
        if previous is None:
            lines.append(f"First build, so there is nothing to compare {kind.lower()} against yet.")
            lines.append("")
        else:
            lines.append("| Name | Moved since last build | Turned | Notes |")
            lines.append("| --- | --- | --- | --- |")
            for name in sorted(set(new) | set(old)):
                if name not in old:
                    lines.append(f"| {name} | new | | |")
                elif name not in new:
                    lines.append(f"| {name} | removed | | |")
                else:
                    d, a = _delta(_matrix(old[name]["T"]), _matrix(new[name]["T"]))
                    flag = "check with the vision lead before merging" if d > 1.0 or a > 0.1 else ""
                    lines.append(f"| {name} | {d:.1f} mm | {a:.2f}° | {flag} |")
            lines.append("")

    section("Cameras", "cameras")
    section("Frames", "frames")

    if baseline:
        cams = {c["name"].upper(): c for c in manifest.get("cameras", [])}
        lines.append("## Cameras compared with the hand-typed values")
        lines.append("")
        lines.append(
            f"Pass: within {TOLERANCE_MM:g} mm and {TOLERANCE_DEG:g}° (PLAN §10.3 item 7). Anything else needs a reason: a CAD error or a code error."
        )
        lines.append("")
        lines.append("| Camera | Distance | Angle | Result |")
        lines.append("| --- | --- | --- | --- |")
        for name in sorted(set(baseline) | set(cams)):
            if name not in cams:
                lines.append(f"| {name} | | | no `cam_` connector in CAD |")
            elif name not in baseline:
                lines.append(f"| {name} | | | not in the baseline file |")
            else:
                d, a = _delta(baseline[name], _matrix(cams[name]["T"]))
                ok = d <= TOLERANCE_MM and a <= TOLERANCE_DEG
                lines.append(f"| {name} | {d:.1f} mm | {a:.2f}° | {'pass' if ok else '**check**'} |")
        lines.append("")

    # 3. Components
    lines.append("## Moving components")
    lines.append("")
    comps = manifest.get("components", [])
    if comps:
        lines.append("| File | Joint | Type | Signal | Rides on | Triangles |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for c in comps:
            parent = "base" if c["parent_component"] is None else f"model_{c['parent_component']}"
            lines.append(
                f"| {c['file']} | `{c['joint']}` | {c['type']} | {c['signal']} | {parent} | {c['triangles']:,} |"
            )
    else:
        lines.append("None: the whole robot is one solid model.")
    lines.append("")
    mesh = manifest.get("mesh") or {}
    total_mb = (manifest["base"]["bytes"] + sum(c["bytes"] for c in comps)) / 1e6
    lines.append(
        f"Model: {manifest['triangles_total']:,} triangles (budget {mesh.get('triangle_budget', 0):,}), {total_mb:.1f} MB. "
        f"Frozen joints: {len(manifest.get('frozen_joints', []))}."
    )
    lines.append("")

    # 4. Warnings
    warnings = manifest.get("warnings", [])
    lines.append(f"## Warnings ({len(warnings)})")
    lines.append("")
    lines += [f"- {w}" for w in warnings] or ["None."]
    lines.append("")
    return "\n".join(lines)
