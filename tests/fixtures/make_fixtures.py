"""Generate synthetic URDF fixtures for cad2ascope tests.

Each fixture is a folder with robot.urdf, meshes/*.glb (colored boxes), a team
config (advantagescope.yaml), and, for valid fixtures, expected.json. The same
folder is also zipped, because the converter's input is a zip.

expected.json is computed here by plain matrix products, independently of the
converter, so it works as a test oracle:
  - component order (depth-first from the root, children sorted by joint name)
  - T0 for each component: its root link frame in ROBOT frame at q = 0
  - zeroed transform = inverse(T0)
  - camera and frame transforms in robot frame
  - frozen joints (movable but not listed in the config)

ASSUMPTION to re-check after Phase 0: Onshape mate connectors arrive as
massless dummy links attached by fixed joints (onshape-to-robot style), named
after the connector. If the native exporter does it differently, change
`frame()` below and regenerate.

Run:  uv run python tests/fixtures/make_fixtures.py   (needs numpy, trimesh)
"""

from __future__ import annotations

import json
import math
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).parent


# ---------------------------------------------------------------- math helpers

def rpy_matrix(r: float, p: float, y: float) -> np.ndarray:
    """URDF rpy: fixed-axis roll about X, then pitch about Y, then yaw about Z."""
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def transform(xyz=(0, 0, 0), rpy=(0, 0, 0)) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = rpy_matrix(*rpy)
    t[:3, 3] = xyz
    return t


def fmt(v) -> str:
    return " ".join(f"{x:.6g}" for x in v)


# ---------------------------------------------------------------- model

@dataclass
class Link:
    name: str
    box: tuple[float, float, float] | None = None       # size in meters, None = no visual
    box_xyz: tuple[float, float, float] = (0, 0, 0)     # visual origin in link frame
    color: tuple[int, int, int, int] = (128, 128, 128, 255)


@dataclass
class Joint:
    name: str
    kind: str                     # fixed | revolute | prismatic | continuous
    parent: str
    child: str
    xyz: tuple = (0, 0, 0)
    rpy: tuple = (0, 0, 0)
    axis: tuple = (0, 0, 1)
    limits: tuple | None = None   # (lower, upper)
    mimic: tuple | None = None    # (joint, multiplier, offset)


@dataclass
class Fixture:
    name: str
    description: str
    links: list[Link] = field(default_factory=list)
    joints: list[Joint] = field(default_factory=list)
    config: str = ""
    expect_error: str | None = None   # substring the converter's error must mention

    def link(self, *a, **k):
        self.links.append(Link(*a, **k))

    def joint(self, *a, **k):
        self.joints.append(Joint(*a, **k))

    def frame(self, name: str, parent: str, xyz=(0, 0, 0), rpy=(0, 0, 0)):
        """A mate connector, represented as a dummy link on a fixed joint (ASSUMPTION)."""
        self.link(name)
        self.joint(f"{name}_frame", "fixed", parent, name, xyz, rpy)


# ---------------------------------------------------------------- writers

def write_urdf(fx: Fixture, out: Path) -> None:
    lines = ['<?xml version="1.0"?>', f'<robot name="{fx.name}">']
    for ln in fx.links:
        lines.append(f'  <link name="{ln.name}">')
        if ln.box:
            lines += [
                "    <visual>",
                f'      <origin xyz="{fmt(ln.box_xyz)}" rpy="0 0 0"/>',
                f'      <geometry><mesh filename="meshes/{ln.name}.glb"/></geometry>',
                "    </visual>",
            ]
        lines.append("  </link>")
    for j in fx.joints:
        lines.append(f'  <joint name="{j.name}" type="{j.kind}">')
        lines.append(f'    <parent link="{j.parent}"/>')
        lines.append(f'    <child link="{j.child}"/>')
        lines.append(f'    <origin xyz="{fmt(j.xyz)}" rpy="{fmt(j.rpy)}"/>')
        if j.kind != "fixed":
            lines.append(f'    <axis xyz="{fmt(j.axis)}"/>')
        if j.limits:
            lines.append(f'    <limit lower="{j.limits[0]:.6g}" upper="{j.limits[1]:.6g}" effort="0" velocity="0"/>')
        if j.mimic:
            lines.append(f'    <mimic joint="{j.mimic[0]}" multiplier="{j.mimic[1]:.6g}" offset="{j.mimic[2]:.6g}"/>')
        lines.append("  </joint>")
    lines.append("</robot>")
    (out / "robot.urdf").write_text("\n".join(lines) + "\n")


def write_meshes(fx: Fixture, out: Path) -> None:
    md = out / "meshes"
    md.mkdir(exist_ok=True)
    for ln in fx.links:
        if not ln.box:
            continue
        mesh = trimesh.creation.box(extents=ln.box)
        mesh.visual.face_colors = np.tile(np.array(ln.color, dtype=np.uint8), (len(mesh.faces), 1))
        mesh.metadata["name"] = ln.name
        mesh.export(md / f"{ln.name}.glb")


def expected(fx: Fixture) -> dict:
    """Independent oracle: FK at q = 0 by walking joint origins."""
    children: dict[str, list[Joint]] = {}
    parent_of: dict[str, Joint] = {}
    for j in fx.joints:
        children.setdefault(j.parent, []).append(j)
        parent_of[j.child] = j
    root = next(ln.name for ln in fx.links if ln.name not in parent_of)

    world: dict[str, np.ndarray] = {root: np.eye(4)}
    order: list[str] = []

    import yaml  # local import: only needed when generating
    cfg = yaml.safe_load(fx.config)
    articulated = set(cfg.get("joints", {}))

    def walk(link: str) -> None:
        for j in sorted(children.get(link, []), key=lambda jj: jj.name):
            world[j.child] = world[link] @ transform(j.xyz, j.rpy)
            if j.name in articulated:
                order.append(j.name)
            walk(j.child)

    walk(root)

    origin_name = cfg["robot"]["origin_frame"]
    robot_from_world = np.linalg.inv(world[origin_name])

    def in_robot(name: str) -> list[list[float]]:
        return np.round(robot_from_world @ world[name], 9).tolist()

    movable = {j.name for j in fx.joints if j.kind != "fixed"}
    joint_by_name = {j.name: j for j in fx.joints}
    comps = []
    for i, jn in enumerate(order):
        j = joint_by_name[jn]
        t0 = robot_from_world @ world[j.child]
        comps.append({
            "index": i,
            "joint": jn,
            "type": j.kind,
            "child_link": j.child,
            "T0": np.round(t0, 9).tolist(),
            "zeroed": np.round(np.linalg.inv(t0), 9).tolist(),
            "axis_in_child_frame": list(j.axis),
        })
    cam_prefix = cfg.get("cameras", {}).get("frame_prefix", "cam_")
    frm_prefix = cfg.get("frames", {}).get("frame_prefix", "frame_")
    return {
        "root_link": root,
        "components": comps,
        "frozen_joints": sorted(movable - articulated),
        "cameras": {ln.name[len(cam_prefix):]: in_robot(ln.name) for ln in fx.links if ln.name.startswith(cam_prefix)},
        "frames": {ln.name[len(frm_prefix):]: in_robot(ln.name) for ln in fx.links if ln.name.startswith(frm_prefix)},
        "note": "4x4 matrices, row-major, meters. ROBOT frame = origin_frame (+X front, +Y left, +Z up, floor plane).",
    }


# ---------------------------------------------------------------- fixtures

BASE_CFG = """\
robot:
  name: "{name}"
  folder: Robot_{name}
  origin_frame: ascope_origin
"""


def base(fx: Fixture, origin_xyz=(0.05, -0.02, -0.1), origin_rpy=(0, 0, math.pi / 2)) -> None:
    """Drivetrain box plus an origin frame that is deliberately not identity,
    so tests catch a converter that ignores origin_frame."""
    fx.link("drivetrain", box=(0.7, 0.7, 0.1), box_xyz=(0, 0, 0.05), color=(97, 73, 148, 255))
    fx.frame("ascope_origin", "drivetrain", origin_xyz, origin_rpy)


def single_revolute() -> Fixture:
    fx = Fixture("single_revolute", "One arm on a revolute joint about the robot's left-right axis.")
    base(fx)
    fx.link("arm", box=(0.5, 0.05, 0.05), box_xyz=(0.25, 0, 0), color=(220, 120, 0, 255))
    fx.joint("j_arm", "revolute", "drivetrain", "arm", (0.2, 0.1, 0.5), (0, 0, 0), (0, 1, 0), (-1.0, 2.0))
    fx.config = BASE_CFG.format(name=fx.name) + """\
signals:
  arm: {units: rad}
joints:
  j_arm: {signal: arm}
"""
    return fx


def prismatic() -> Fixture:
    fx = Fixture("prismatic", "One carriage on a vertical slider.")
    base(fx)
    fx.link("carriage", box=(0.2, 0.3, 0.1), color=(0, 140, 200, 255))
    fx.joint("j_lift", "prismatic", "drivetrain", "carriage", (-0.1, 0, 0.2), (0, 0, 0), (0, 0, 1), (0.0, 1.2))
    fx.config = BASE_CFG.format(name=fx.name) + """\
signals:
  lift: {units: m}
joints:
  j_lift: {signal: lift}
"""
    return fx


def nested_chain() -> Fixture:
    fx = Fixture("nested_chain", "Turret on the drivetrain, hood on the turret, one camera on each, and a measured frame. Mirrors the 2026 robot.")
    base(fx)
    fx.link("turret", box=(0.25, 0.25, 0.08), color=(60, 60, 60, 255))
    fx.joint("j_turret", "revolute", "drivetrain", "turret", (-0.076, 0.14, 0.286), (0, 0, 0.3), (0, 0, 1), (-3.0, 3.0))
    fx.link("hood", box=(0.15, 0.2, 0.04), box_xyz=(0.075, 0, 0), color=(200, 30, 30, 255))
    fx.joint("j_hood", "revolute", "turret", "hood", (0.1, 0, 0.1), (0, -0.2, 0), (0, 1, 0), (0.0, 0.8))
    fx.frame("cam_FRONT_LEFT", "drivetrain", (0.236, 0.328, 0.233), (0, 0.349066, 0.872665))
    fx.frame("cam_TURRET", "turret", (0.05, 0, 0.12), (0, -0.2, 0))
    fx.frame("frame_turret_pivot", "drivetrain", (-0.076, 0.14, 0.286))
    fx.config = BASE_CFG.format(name=fx.name) + """\
signals:
  turret: {units: rad}
  hood: {units: rad}
joints:
  j_turret: {signal: turret}
  j_hood: {signal: hood, direction: -1}
cameras:
  frame_prefix: cam_
  fallback: {resolution: [1280, 800], fov_deg: 70}
frames:
  frame_prefix: frame_
"""
    return fx


def coupled() -> Fixture:
    fx = Fixture("coupled", "Two-stage cascade elevator (carriage mated to stage 1, mimic relation) with a wrist on the carriage. Mirrors the 2025 robot.")
    base(fx)
    fx.link("stage1", box=(0.05, 0.4, 0.9), box_xyz=(0, 0, 0.45), color=(150, 150, 150, 255))
    fx.joint("j_elevator_stage1", "prismatic", "drivetrain", "stage1", (0.05, 0.127, 0.1), (0, 0, 0), (0, 0, 1), (0.0, 0.7))
    fx.link("carriage", box=(0.1, 0.3, 0.15), color=(0, 140, 200, 255))
    fx.joint("j_elevator_carriage", "prismatic", "stage1", "carriage", (0.06, 0, 0.1), (0, 0, 0), (0, 0, 1), (0.0, 0.7),
             mimic=("j_elevator_stage1", 1.0, 0.0))
    fx.link("wrist", box=(0.3, 0.1, 0.05), box_xyz=(0.15, 0, 0), color=(220, 120, 0, 255))
    fx.joint("j_wrist", "revolute", "carriage", "wrist", (0.05, 0, 0.05), (0, 0, 0), (0, 1, 0), (-1.5, 1.5))
    fx.config = BASE_CFG.format(name=fx.name) + """\
signals:
  elevator: {units: m}
  wrist: {units: rad}
joints:
  j_elevator_stage1:   {signal: elevator, ratio: 0.5}
  j_elevator_carriage: {signal: elevator, ratio: 0.5}
  j_wrist:             {signal: wrist, zero_offset_deg: 10}
"""
    return fx


def frozen() -> Fixture:
    fx = Fixture("frozen", "Two movable joints; only one is listed, so the other must be frozen and merged into the base.")
    base(fx)
    fx.link("intake", box=(0.3, 0.6, 0.05), color=(0, 160, 80, 255))
    fx.joint("j_intake", "revolute", "drivetrain", "intake", (0.35, 0, 0.15), (0, 0, 0), (0, 1, 0), (0.0, 1.6))
    fx.link("flap", box=(0.1, 0.2, 0.02), color=(200, 200, 0, 255))
    fx.joint("Revolute 7", "revolute", "drivetrain", "flap", (-0.3, 0, 0.2), (0, 0, 0), (1, 0, 0), (0.0, 1.0))
    fx.config = BASE_CFG.format(name=fx.name) + """\
signals:
  intake: {units: rad}
joints:
  j_intake: {signal: intake}
"""
    return fx


def invalid_two_parents() -> Fixture:
    fx = Fixture("invalid_two_parents", "A link with two parent joints, as from a closed linkage. Must fail and name the link.",
                 expect_error="bar")
    base(fx)
    fx.link("left_arm", box=(0.4, 0.05, 0.05))
    fx.link("right_arm", box=(0.4, 0.05, 0.05))
    fx.link("bar", box=(0.05, 0.5, 0.05))
    fx.joint("j_left", "revolute", "drivetrain", "left_arm", (0, 0.25, 0.3), axis=(0, 1, 0))
    fx.joint("j_right", "revolute", "drivetrain", "right_arm", (0, -0.25, 0.3), axis=(0, 1, 0))
    fx.joint("j_bar_left", "revolute", "left_arm", "bar", (0.4, -0.25, 0), axis=(0, 1, 0))
    fx.joint("j_bar_right", "revolute", "right_arm", "bar", (0.4, 0.25, 0), axis=(0, 1, 0))
    fx.config = BASE_CFG.format(name=fx.name) + """\
signals:
  arm: {units: rad}
joints:
  j_left: {signal: arm}
"""
    return fx


def missing_origin() -> Fixture:
    fx = Fixture("missing_origin", "No ascope_origin frame. Must fail with a message telling the student to add it on the drivetrain.",
                 expect_error="ascope_origin")
    fx.link("drivetrain", box=(0.7, 0.7, 0.1), box_xyz=(0, 0, 0.05))
    fx.link("arm", box=(0.5, 0.05, 0.05))
    fx.joint("j_arm", "revolute", "drivetrain", "arm", (0.2, 0, 0.5), axis=(0, 1, 0))
    fx.config = BASE_CFG.format(name=fx.name) + """\
signals:
  arm: {units: rad}
joints:
  j_arm: {signal: arm}
"""
    return fx


ALL = [single_revolute, prismatic, nested_chain, coupled, frozen, invalid_two_parents, missing_origin]


def main() -> None:
    index = []
    for make in ALL:
        fx = make()
        out = HERE / fx.name
        if out.exists():
            shutil.rmtree(out)
        out.mkdir()
        write_urdf(fx, out)
        write_meshes(fx, out)
        (out / "advantagescope.yaml").write_text(fx.config)
        if fx.expect_error is None:
            (out / "expected.json").write_text(json.dumps(expected(fx), indent=2) + "\n")
        else:
            (out / "expected_error.txt").write_text(fx.expect_error + "\n")
        with zipfile.ZipFile(HERE / f"{fx.name}.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(out.rglob("*")):
                if p.name in ("advantagescope.yaml", "expected.json", "expected_error.txt"):
                    continue  # the zip mimics an Onshape export: URDF and meshes only
                z.write(p, p.relative_to(out))
        index.append({"name": fx.name, "description": fx.description,
                      "valid": fx.expect_error is None, "expect_error_mentions": fx.expect_error})
    (HERE / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"wrote {len(index)} fixtures to {HERE}")


if __name__ == "__main__":
    main()
