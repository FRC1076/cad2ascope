"""Generate RobotModel.java and RobotModelTest.java (PLAN §7, Phase 3).

The generated class needs only WPILib geometry (edu.wpi.first.math), not AdvantageKit, so it works whatever the
team logs with. Component i is drawn at

    P_i(signals) = P_parent(i) · J_i · M_i(q_i),    q_i = scale_i · (signal - zero_offset_i)

where J_i is joint i's frame in its parent component's root frame at q = 0 (inverse(T0_parent) · T0_i), M_i is the
motion about or along the joint axis, and scale_i = direction · ratio (PLAN §6.5). At zero signals P_i = T0_i, which
is what AdvantageScope's zeroed transform expects (Phase 0, B3).

The test file checks the Java against poses computed here with numpy (``fk``), at zero and at sample positions.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import jinja2
import numpy as np

from cad2ascope import __version__
from cad2ascope.cameras import Camera, Frame
from cad2ascope.errors import Warnings
from cad2ascope.grouping import Model
from cad2ascope.transforms import invert, make_transform

TEMPLATES = Path(__file__).parent / "templates"
SAMPLE_FRACTIONS = (0.25, 0.6, 0.9)


# WPILib classes the generated code and templates use, by WPILib year. 2027 moved everything from edu.wpi.first to
# org.wpilib (checked against 2027.0.0-alpha-8; docs/readiness-checks.md section 1).
_GEOMETRY = ("Pose3d", "Quaternion", "Rotation3d", "Transform3d", "Translation3d")
WPILIB_CLASSES = {
    2026: {
        "VecBuilder": "edu.wpi.first.math.VecBuilder",
        **{c: f"edu.wpi.first.math.geometry.{c}" for c in _GEOMETRY},
        "TimedRobot": "edu.wpi.first.wpilibj.TimedRobot",
        "Command": "edu.wpi.first.wpilibj2.command.Command",
        "SubsystemBase": "edu.wpi.first.wpilibj2.command.SubsystemBase",
    },
    2027: {
        "VecBuilder": "org.wpilib.math.linalg.VecBuilder",
        **{c: f"org.wpilib.math.geometry.{c}" for c in _GEOMETRY},
        "TimedRobot": "org.wpilib.framework.TimedRobot",
        "Command": "org.wpilib.command2.Command",
        "SubsystemBase": "org.wpilib.command2.SubsystemBase",
    },
}
DEFAULT_PERIOD = {2026: "kDefaultPeriod", 2027: "DEFAULT_PERIOD"}  # TimedRobot's loop period constant (0.02 s)


def _wpilib_ctx(year: int) -> dict:
    """Template helpers that write WPILib names for one WPILib year."""
    classes = WPILIB_CLASSES[year]
    return {
        "wpilib": year,
        "wpi_name": lambda c: classes[c],
        "wpi_imports": lambda *names: "\n".join(sorted(f"import {classes[n]};" for n in names)),
        "default_period": DEFAULT_PERIOD[year],
    }


def java_const(name: str) -> str:
    """UPPER_SNAKE Java identifier from a signal, camera or frame name."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    if not s or not (s[0].isalpha() or s[0] == "_"):
        s = "N_" + s
    return s


def java_method(name: str) -> str:
    """lowerCamelCase Java method name."""
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    if not parts:
        return "unnamed"
    s = parts[0].lower() + "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    return s if s[0].isalpha() else "n" + s


SIG_DIGITS = 12  # far below a nanometer at robot scale; hides last-digit differences between platforms


def num(x: float) -> str:
    """A Java double literal, rounded so the generated file is identical on macOS, Linux and Windows."""
    v = float(x)
    if not math.isfinite(v):
        raise ValueError(f"non-finite number in generated code: {v}")
    if abs(v) < 1e-12:
        return "0.0"
    text = f"{v:.{SIG_DIGITS}g}"
    if not any(c in text for c in ".eE"):
        text += ".0"
    return text


def quaternion(r: np.ndarray) -> tuple[float, float, float, float]:
    """(w, x, y, z) for a rotation matrix, normalized with w >= 0 so output is stable."""
    m = np.asarray(r, dtype=float)
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        w, x, y, z = 0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w, x, y, z = (m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w, x, y, z = (m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w, x, y, z = (m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s
    q = np.array([w, x, y, z])
    q /= np.linalg.norm(q)
    if q[0] < 0:
        q = -q
    return tuple(round(float(v), 15) + 0.0 for v in q)  # type: ignore[return-value]


@dataclass
class JointCode:
    index: int
    name: str
    parent: int
    origin: np.ndarray  # J_i
    axis: tuple[float, float, float]
    prismatic: bool
    signal: int
    scale: float
    zero_offset: float  # in signal units (m or rad)


@dataclass
class SignalCode:
    name: str
    const: str
    units: str
    min: float
    max: float


def _joints(model: Model, signal_index: dict[str, int]) -> list[JointCode]:
    out = []
    for c in model.components:
        parent_t0 = np.eye(4) if c.parent is None else model.components[c.parent].T0
        jc = c.config
        prismatic = c.joint.type == "prismatic"
        if prismatic:
            offset = float(jc.zero_offset_m or 0.0)
        else:
            offset = math.radians(jc.zero_offset_deg or 0.0)
        out.append(
            JointCode(
                c.index,
                c.joint.name,
                -1 if c.parent is None else c.parent,
                invert(parent_t0) @ c.T0,
                tuple(float(v) for v in c.joint.axis),  # type: ignore[arg-type]
                prismatic,
                signal_index[jc.signal],
                float(jc.direction) * float(jc.ratio),
                offset,
            )
        )
    return out


def _signals(model: Model, warnings: Warnings) -> list[SignalCode]:
    out = []
    for name, units in model.config.signals.items():
        lo, hi = -math.inf, math.inf
        for c in model.components:
            if c.config.signal != name or c.joint.type == "continuous":
                continue
            if c.joint.lower is None or c.joint.upper is None:
                continue
            scale = float(c.config.direction) * float(c.config.ratio)
            if c.joint.type == "prismatic":
                off = float(c.config.zero_offset_m or 0.0)
            else:
                off = math.radians(c.config.zero_offset_deg or 0.0)
            a, b = c.joint.lower / scale + off, c.joint.upper / scale + off
            lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
        if lo > hi:
            warnings.add(
                f"Signal {name!r} drives joints whose mate limits do not overlap, so no single value keeps them all "
                "inside their limits. Check the ratios and limits."
            )
            lo, hi = hi, lo
        if not math.isfinite(lo) or not math.isfinite(hi):
            lo, hi = (-math.pi, math.pi) if units == "rad" else (0.0, 0.0)
        out.append(SignalCode(name, java_const(name), units, lo, hi))
    return out


def _motion(j: JointCode, q: float) -> np.ndarray:
    a = np.array(j.axis)
    if j.prismatic:
        return make_transform(np.eye(3), a * q)
    # Rotation by q about unit axis a (Rodrigues), independent of the WPILib implementation.
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    r = np.eye(3) + math.sin(q) * k + (1 - math.cos(q)) * (k @ k)
    return make_transform(r)


def fk(joints: list[JointCode], signals: list[float]) -> list[np.ndarray]:
    """Component poses in robot frame for signal values (the numpy reference for the Java test)."""
    poses: list[np.ndarray] = []
    for j in joints:
        parent = np.eye(4) if j.parent < 0 else poses[j.parent]
        q = j.scale * (signals[j.signal] - j.zero_offset)
        poses.append(parent @ j.origin @ _motion(j, q))
    return poses


def _pose_literal(t: np.ndarray, kind: str = "Transform3d") -> str:
    w, x, y, z = quaternion(t[:3, :3])
    p = t[:3, 3]
    return (
        f"new {kind}(new Translation3d({num(p[0])}, {num(p[1])}, {num(p[2])}), "
        f"new Rotation3d(new Quaternion({num(w)}, {num(x)}, {num(y)}, {num(z)})))"
    )


def _attachments(model: Model, items, cls: str):
    fixed, moving = [], []
    for it in items:
        if it.component is None:
            fixed.append(
                {"cls": cls, "const": java_const(it.name), "name": it.name, "literal": _pose_literal(it.T), "T": it.T}
            )
        else:
            comp = model.components[it.component]
            local = invert(comp.T0) @ it.T
            moving.append(
                {
                    "cls": cls,
                    "const": java_const(it.name),
                    "method": java_method(it.name),
                    "name": it.name,
                    "component": it.component,
                    "joint": comp.joint.name,
                    "local": _pose_literal(local),
                    "local_T": local,
                    "T": it.T,
                }
            )
    return fixed, moving


def _expect(t: np.ndarray) -> dict:
    w, x, y, z = quaternion(t[:3, :3])
    return {
        "x": num(t[0, 3]),
        "y": num(t[1, 3]),
        "z": num(t[2, 3]),
        "qw": num(w),
        "qx": num(x),
        "qy": num(y),
        "qz": num(z),
    }


def generate(
    model: Model,
    cameras: list[Camera],
    frames: list[Frame],
    source: str,
    warnings: Warnings | None = None,
) -> tuple[str, str]:
    """Return (RobotModel.java, RobotModelTest.java) source text."""
    warnings = warnings if warnings is not None else model.warnings
    cfg = model.config
    signals = _signals(model, warnings)
    signal_index = {s.name: i for i, s in enumerate(signals)}
    joints = _joints(model, signal_index)
    cams_fixed, cams_moving = _attachments(model, cameras, "Cameras")
    frames_fixed, frames_moving = _attachments(model, frames, "Frames")
    for item in cams_fixed + frames_fixed:
        item["expect"] = _expect(item["T"])

    samples = [[0.0] * len(signals)]
    for k, frac in enumerate(SAMPLE_FRACTIONS):
        row = []
        for i, s in enumerate(signals):
            f = (frac + 0.31 * i + 0.17 * k) % 1.0
            row.append(s.min + f * (s.max - s.min))
        samples.append(row)
    expected = [[_expect(p) for p in fk(joints, sig)] for sig in samples]
    moving_expected = [
        [_expect(fk(joints, sig)[m["component"]] @ m["local_T"]) for m in cams_moving + frames_moving]
        for sig in samples
    ]

    env = _env()
    ctx = {
        "version": __version__,
        "source": source,
        "package": cfg.codegen.java_package,
        "robot_name": cfg.robot.name,
        "signals": signals,
        "joints": [
            {
                "index": j.index,
                "name": j.name,
                "parent": j.parent,
                "origin": _pose_literal(j.origin),
                "axis": [num(v) for v in j.axis],
                "prismatic": "true" if j.prismatic else "false",
                "signal": j.signal,
                "scale": num(j.scale),
                "zero_offset": num(j.zero_offset),
            }
            for j in joints
        ],
        "num": num,
        "cams_fixed": cams_fixed,
        "cams_moving": cams_moving,
        "frames_fixed": frames_fixed,
        "frames_moving": frames_moving,
        "samples": [[num(v) for v in row] for row in samples],
        "expected": expected,
        "moving_expected": moving_expected,
        "moving_all": cams_moving + frames_moving,
        "fixed_all": cams_fixed + frames_fixed,
        **_wpilib_ctx(cfg.codegen.wpilib),
    }
    return env.get_template("RobotModel.java.j2").render(ctx), env.get_template("RobotModelTest.java.j2").render(ctx)


def source_description(onshape: dict | None, input_name: str, sha256: str) -> str:
    if onshape and onshape.get("kind") == "version":
        return f'Onshape version "{onshape.get("version_name")}" (v={onshape.get("version_id", "")[:8]})'
    if onshape and onshape.get("kind") == "workspace":
        return f"Onshape workspace preview (microversion {onshape.get('microversion', '')[:8]})"
    return f"{input_name} (sha256 {sha256[:12]})"


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=jinja2.StrictUndefined,
    )


def visualizer_package(java_package: str) -> str:
    """frc.robot.generated -> frc.robot.visualization (the hand-owned files sit next to the generated package)."""
    head = java_package.rsplit(".", 1)[0] if "." in java_package else java_package
    return f"{head}.visualization"


def robot_code_templates(java_package: str, wpilib: int = 2026) -> dict[str, str]:
    """RobotVisualizer.java and SweepRobotModel.java (written once; the team owns them after that)."""
    ctx = {"package": java_package, "visualizer_package": visualizer_package(java_package), **_wpilib_ctx(wpilib)}
    env = _env()
    return {
        name: env.get_template(f"{name}.j2").render(ctx) for name in ("RobotVisualizer.java", "SweepRobotModel.java")
    }


@dataclass
class Written:
    generated: list[Path]
    created: list[Path]  # hand-owned files written for the first time
    kept: list[Path]  # hand-owned files that already existed and were left alone


def write(java: str, test: str, cfg, repo_root: Path) -> Written:
    """Write the generated files (always) and the hand-owned templates (only if missing)."""
    out_java, out_test = repo_root / cfg.codegen.output, repo_root / cfg.codegen.test_output
    for path, text in ((out_java, java), (out_test, test)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    vis_dir = out_java.parent.parent / "visualization"
    created, kept = [], []
    for name, text in robot_code_templates(cfg.codegen.java_package, cfg.codegen.wpilib).items():
        path = vis_dir / name
        if path.exists():
            kept.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            created.append(path)
    return Written([out_java, out_test], created, kept)


__all__ = [
    "robot_code_templates",
    "visualizer_package",
    "fk",
    "generate",
    "java_const",
    "java_method",
    "quaternion",
    "source_description",
    "write",
]
