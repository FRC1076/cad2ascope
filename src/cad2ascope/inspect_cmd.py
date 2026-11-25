"""`cad2ascope inspect` and `cad2ascope init`: read an export and help students write the team config (PLAN §6.2)."""

from __future__ import annotations

import math
import re
from pathlib import Path

import yaml

from cad2ascope.config import CONFIG_NAME, parse_config
from cad2ascope.errors import CadError
from cad2ascope.export import load_export, onshape_notes
from cad2ascope.urdf import Joint, Robot


def _limits(j: Joint) -> str:
    if j.type == "continuous":
        return "no limits"
    if j.lower is None or j.upper is None:
        return "NO LIMITS SET"
    if j.type == "prismatic":
        return f"{j.lower:.3f} to {j.upper:.3f} m"
    return f"{math.degrees(j.lower):.1f} to {math.degrees(j.upper):.1f} deg"


def describe(
    robot: Robot, origin_frame: str = "ascope_origin", cam_prefix: str = "cam_", frame_prefix: str = "frame_"
) -> str:
    """The kinematic tree as text, with every movable joint, its type, limits, and parts per link."""
    lines = [f"Robot {robot.name!r}: {len(robot.links)} links, {len(robot.joints)} joints", ""]

    def tag(link: str) -> str:
        if link == origin_frame:
            return "  [robot origin]"
        if link.startswith(cam_prefix):
            return "  [camera]"
        if link.startswith(frame_prefix):
            return "  [frame]"
        n = len(robot.links[link].visuals)
        return f"  ({n} mesh{'es' if n != 1 else ''})" if n else ""

    lines.append(f"{robot.root}{tag(robot.root)}")
    depth = {robot.root: 0}
    for j in robot.walk():
        d = depth[j.parent] + 1
        depth[j.child] = d
        if j.movable:
            mark = "MOVES" if j.name.startswith("j_") else "moves, frozen (no j_)"
            how = f" <{j.onshape_kind} {j.name!r}: {mark}, {_limits(j)}"
            if j.mimic:
                how += f", relation: {j.mimic.multiplier:g} x {j.mimic.joint}"
            how += ">"
        else:
            how = ""
        lines.append(f"{'  ' * d}{j.child}{tag(j.child)}{how}")

    movable = [j for j in robot.walk() if j.movable]
    lines += ["", f"Movable joints: {len(movable)}"]
    for j in movable:
        lines.append(f"  {j.name:<32} {j.onshape_kind:<10} {_limits(j)}")
    parts = sum(len(link.visuals) for link in robot.links.values())
    lines.append(f"Mesh files referenced: {parts}")
    notes = onshape_notes(robot, origin_frame)
    if notes:
        lines += ["", "Notes:"] + [f"  - {n}" for n in notes]
    if origin_frame not in robot.links:
        lines.append(f"\nMissing: no {origin_frame!r} frame. Add that mate connector on the drivetrain (PLAN §4 C2).")
    return "\n".join(lines)


def inspect(path: str | Path) -> str:
    if str(path).startswith(("http://", "https://")):
        raise CadError(
            "Reading straight from an Onshape URL is not built yet (Phase 4). In Onshape, right-click the assembly, "
            "choose Export, pick URDF with glTF meshes, and pass the downloaded zip instead."
        )
    with load_export(path) as export:
        return describe(export.robot)


def _signal_name(joint_name: str) -> str:
    s = re.sub(r"[^a-z0-9_]", "_", joint_name.removeprefix("j_").lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "s_" + s
    return s


def init_text(robot: Robot, name: str | None = None, folder: str | None = None, onshape_url: str | None = None) -> str:
    """A starter cad/advantagescope.yaml with one entry per movable j_ mate. Validates against the schema."""
    name = name or robot.name
    folder = folder or "Robot_" + (re.sub(r"[^A-Za-z0-9_\-]", "_", name).strip("_") or "robot")
    movable = [j for j in robot.walk() if j.movable]
    listed = [j for j in movable if re.fullmatch(r"j_[A-Za-z0-9_]+", j.name)]
    others = [j for j in movable if j not in listed]
    listed_names = {j.name for j in listed}

    signal_of: dict[str, str] = {}
    signals: dict[str, str] = {}
    joints_lines = []
    for j in listed:
        if j.mimic and j.mimic.joint in listed_names and j.mimic.joint in signal_of:
            sig = signal_of[j.mimic.joint]
            extra = f", ratio: {j.mimic.multiplier:g}"
            note = f"  # from the Onshape relation with {j.mimic.joint}; check against PLAN §6.5"
        else:
            sig = _signal_name(j.name)
            if sig in signals:
                sig = f"{sig}_{len(signals)}"
            signals[sig] = "m" if j.type == "prismatic" else "rad"
            extra, note = "", ""
        signal_of[j.name] = sig
        joints_lines.append(f"  {j.name}: {{signal: {sig}{extra}}}{note}")

    out = [
        "# cad/advantagescope.yaml: made by 'cad2ascope init'. Edit signals, ratios and directions with the software lead.",
        "# Reference: docs/PLAN.md §6.3 in the cad2ascope repo.",
        "",
        "robot:",
        f"  name: {yaml.safe_dump(name, default_style=chr(34)).strip()}",
        f"  folder: {folder}",
    ]
    out.append(f"  onshape_url: {onshape_url}" if onshape_url else "  # onshape_url: paste the assembly URL here")
    out += [
        '  configuration: "Export=AdvantageScope"',
        "  version: latest",
        "  origin_frame: ascope_origin",
        "",
        "signals:                # values robot code provides, in SI units",
    ]
    out += [f"  {s}: {{units: {u}}}" for s, u in signals.items()] or ["  {}"]
    out += [
        "",
        "joints:                 # only these mates move in AdvantageScope; ratio is relative to the parent part",
    ]
    out += joints_lines or ["  {}"]
    if others:
        out += ["", "# These mates can move in Onshape but are frozen, because their names do not start with j_:"]
        out += [f"#   {j.name} ({j.onshape_kind})" for j in others]
    out += [
        "",
        "mesh:",
        "  triangle_budget: 300000",
        '  exclude_names: ["*screw*", "*bolt*", "*nut*", "*washer*", "*rivet*", "*bhcs*", "*shcs*", "*fhcs*"]',
        "  min_part_size_mm: 6",
        '  keep_detail: ["*bumper*"]           # never simplified, e.g. bumper numbers',
        "",
        "cameras:",
        "  frame_prefix: cam_",
        "  photonvision_calibrations: assets/photonvision",
        "  fallback: {resolution: [1280, 800], fov_deg: 70}",
        "",
        "frames:",
        "  frame_prefix: frame_",
        "",
        "codegen:",
        "  java_package: frc.robot.generated",
        "",
    ]
    text = "\n".join(out)
    parse_config(yaml.safe_load(text), source="the generated config")  # never hand students a file that fails
    return text


def init(path: str | Path, output: str | Path = CONFIG_NAME, force: bool = False, **kw) -> Path:
    output = Path(output)
    if output.exists() and not force:
        raise CadError(f"{output} already exists. Use --force to replace it, or edit it by hand.")
    with load_export(path) as export:
        text = init_text(export.robot, **kw)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    return output
