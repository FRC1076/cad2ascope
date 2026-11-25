"""Classify joints, group links into components, and place everything in robot frame (PLAN §6.4 steps 2 to 4, 6).

- A joint listed under ``joints`` in the config is articulated and starts a component.
- Any other movable joint is frozen at its export position and merged into its parent's group (with a warning).
- Fixed joints always merge.
- Components are numbered in depth-first order from the URDF root, children visited in joint-name order.
- T0 for a component is its root link frame (the articulated joint's child frame) in robot frame at q = 0.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field

import numpy as np

from cad2ascope.config import Config, JointConfig
from cad2ascope.errors import CadError, Warnings
from cad2ascope.transforms import invert
from cad2ascope.urdf import Joint, Robot

UNITS_FOR = {"revolute": "rad", "continuous": "rad", "prismatic": "m"}
DEFAULT_PART_NAME = re.compile(r"^(part|part studio|mate connector|revolute|slider|fastened)[ _]*\d+", re.IGNORECASE)


@dataclass
class Component:
    index: int
    joint: Joint
    config: JointConfig
    links: list[str]  # root link first, then the rest of the group in tree order
    parent: int | None  # component index of the parent link's group, None = base model
    T0: np.ndarray  # root link frame in robot frame at q = 0

    @property
    def root_link(self) -> str:
        return self.joint.child

    @property
    def file(self) -> str:
        return f"model_{self.index}.glb"


@dataclass
class Model:
    """Everything the writers and code generator need, in robot frame."""

    robot: Robot
    config: Config
    robot_from_world: np.ndarray
    base_links: list[str]
    components: list[Component]
    frozen: list[Joint]
    group_of: dict[str, int | None]  # link -> component index, None = base
    warnings: Warnings = field(default_factory=Warnings)
    _world: dict[str, np.ndarray] = field(default_factory=dict)

    def link_pose(self, link: str) -> np.ndarray:
        """Link frame in robot frame at the export pose (every joint at q = 0)."""
        return self.robot_from_world @ self._world[link]


def _suggest(name: str, options: list[str]) -> str:
    close = difflib.get_close_matches(name, options, n=1, cutoff=0.6)
    return f" Did you mean {close[0]!r}?" if close else ""


def _check_listed_joint(name: str, jc: JointConfig, joint: Joint | None, robot: Robot, cfg: Config) -> list[str]:
    src = cfg.source
    if joint is None:
        movable = [j.name for j in robot.joints.values() if j.movable]
        return [
            f"{name} is listed in {src} but there is no mate with that name in the export.{_suggest(name, movable)} "
            "Check the mate name in Onshape, or remove it from the config."
        ]
    problems = []
    if joint.type in ("fixed", "floating", "planar"):
        problems.append(
            f"{name} is a {joint.onshape_kind} mate. Change it to Revolute or Slider in Onshape, or remove it from {src}."
        )
        return problems
    units = cfg.signals[jc.signal]
    want = UNITS_FOR[joint.type]
    if units != want:
        kind = "turns, so its signal must be in rad" if want == "rad" else "slides, so its signal must be in m"
        problems.append(
            f"{name} {kind}, but signal {jc.signal!r} is in {units}. Use a different signal, or fix its units."
        )
    if jc.zero_offset_deg is not None and joint.type == "prismatic":
        problems.append(f"{name} is a Slider, so use zero_offset_m instead of zero_offset_deg.")
    if jc.zero_offset_m is not None and joint.type != "prismatic":
        problems.append(f"{name} is a Revolute, so use zero_offset_deg instead of zero_offset_m.")
    return problems


def build_model(robot: Robot, cfg: Config) -> Model:
    """Group the robot into a base model and components. Raises CadError for anything the student must fix."""
    warnings = Warnings()

    problems: list[str] = []
    for name, jc in cfg.joints.items():
        problems += _check_listed_joint(name, jc, robot.joints.get(name), robot, cfg)
    if problems:
        raise CadError(
            f"{len(problems)} problem(s) with the joints in {cfg.source}:\n" + "\n".join(f"  - {p}" for p in problems)
        )

    origin = cfg.robot.origin_frame
    if origin not in robot.links:
        raise CadError(
            f"The robot origin frame {origin!r} is not in the export. Add a mate connector named {origin} on the "
            "drivetrain, at the center of the frame on the floor plane, +X toward the front and +Z up (PLAN §4 C2). "
            "If it is there, check that it is not on a suppressed part in the export configuration."
        )

    world = robot.world_poses()
    robot_from_world = invert(world[origin])

    articulated = set(cfg.joints)
    group_of: dict[str, int | None] = {robot.root: None}
    components: list[Component] = []
    frozen: list[Joint] = []
    for j in robot.walk():
        if j.name in articulated:
            idx = len(components)
            components.append(
                Component(idx, j, cfg.joints[j.name], [j.child], group_of[j.parent], robot_from_world @ world[j.child])
            )
            group_of[j.child] = idx
        else:
            group_of[j.child] = group_of[j.parent]
            g = group_of[j.child]
            if g is not None:
                components[g].links.append(j.child)
            if j.movable:
                frozen.append(j)
    base_links = [name for name, g in group_of.items() if g is None]
    # group_of was filled in walk order, and base_links preserves it.

    if group_of.get(origin) is not None:
        comp = components[group_of[origin]]
        raise CadError(
            f"The origin frame {origin!r} is on a moving mechanism ({comp.joint.name}). "
            "Move the mate connector to the drivetrain, which never moves relative to the robot (PLAN §4 C2)."
        )

    for j in frozen:
        if j.name.startswith("j_"):
            warnings.add(
                f"Mate {j.name} can move in Onshape but is not listed under joints in {cfg.source}, so it is frozen "
                "where it was exported. Add it under joints to make it move."
            )
        else:
            warnings.add(
                f"Mate {j.name!r} ({j.onshape_kind}) can move in Onshape but is not a j_ mate, so it is frozen where it "
                "was exported. To make it move, rename it with a j_ prefix and add it under joints."
            )

    for comp in components:
        j = comp.joint
        if j.mimic is None:
            continue
        leader = cfg.joints.get(j.mimic.joint)
        if leader is None:
            warnings.add(
                f"{j.name} is linked by a relation to {j.mimic.joint}, which is not listed under joints. "
                f"Check that {j.name}'s signal and ratio still describe how it moves."
            )
            continue
        if leader.signal != comp.config.signal:
            warnings.add(
                f"{j.name} is linked by a relation to {j.mimic.joint} but uses a different signal "
                f"({comp.config.signal!r} vs {leader.signal!r}). Use the same signal if one motor drives both."
            )
            continue
        expected = j.mimic.multiplier * leader.ratio * leader.direction
        actual = comp.config.ratio * comp.config.direction
        if not math.isclose(expected, actual, rel_tol=1e-6, abs_tol=1e-9):
            warnings.add(
                f"{j.name}: the Onshape relation says it moves {j.mimic.multiplier:g} times {j.mimic.joint}, "
                f"but the config gives ratio {actual:g} against {j.mimic.joint}'s {leader.ratio * leader.direction:g}. "
                "Check the ratios (PLAN §6.5: each ratio is relative to the joint's parent part)."
            )
        if j.mimic.offset != 0:
            warnings.add(
                f"{j.name}: the Onshape relation has an offset of {j.mimic.offset:g}, which cad2ascope ignores."
            )

    for comp in components:
        j = comp.joint
        if j.type == "continuous" or j.lower is None or j.upper is None:
            if j.type != "continuous":
                warnings.add(
                    f"{j.name} has no mate limits. Set limits on the mate in Onshape (PLAN §4 C3); the sweep test needs them."
                )
        elif j.lower > j.upper:
            warnings.add(f"{j.name} has its lower limit above its upper limit. Fix the mate limits in Onshape.")
        elif not (j.lower - 1e-9 <= 0.0 <= j.upper + 1e-9):
            warnings.add(
                f"{j.name} was exported outside its own mate limits. Put the robot in the ascope_zero position before "
                "creating the Version (PLAN §4 C6)."
            )

    if not components:
        warnings.add(f"No joints are listed in {cfg.source}, so the whole robot is one solid model.")

    for name in robot.links:
        if DEFAULT_PART_NAME.match(name):
            warnings.add(
                f"Part {name!r} still has a default name. Give it a clear name in Onshape so reports are readable."
            )

    return Model(robot, cfg, robot_from_world, base_links, components, frozen, group_of, warnings, world)
