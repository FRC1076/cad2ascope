"""Parse a URDF and check that it describes one tree (PLAN §6.4 step 1).

This module knows only standard URDF. Anything specific to how Onshape writes its export (file layout, mesh paths,
how mate connectors appear) lives in export.py.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import numpy as np

from cad2ascope.errors import CadError
from cad2ascope.transforms import axis_rotation, make_transform

MOVABLE = {"revolute", "continuous", "prismatic"}
KNOWN_TYPES = MOVABLE | {"fixed", "floating", "planar"}
ONSHAPE_KIND = {
    "fixed": "Fastened",
    "revolute": "Revolute",
    "continuous": "Revolute (no limits)",
    "prismatic": "Slider",
    "floating": "free (floating)",
    "planar": "Planar",
}


@dataclass
class Visual:
    mesh: str  # filename exactly as written in the URDF
    origin: np.ndarray  # 4x4, visual frame in link frame
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    name: str | None = None


@dataclass
class Link:
    name: str
    visuals: list[Visual] = field(default_factory=list)


@dataclass
class Mimic:
    joint: str
    multiplier: float = 1.0
    offset: float = 0.0


@dataclass
class Joint:
    name: str
    type: str
    parent: str
    child: str
    origin: np.ndarray  # 4x4, child frame in parent frame at q = 0
    axis: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    lower: float | None = None
    upper: float | None = None
    mimic: Mimic | None = None

    @property
    def movable(self) -> bool:
        return self.type in MOVABLE

    @property
    def onshape_kind(self) -> str:
        return ONSHAPE_KIND.get(self.type, self.type)


@dataclass
class Robot:
    name: str
    links: dict[str, Link]  # in file order
    joints: dict[str, Joint]  # in file order
    root: str
    parent_joint: dict[str, Joint]  # child link -> joint
    child_joints: dict[str, list[Joint]]  # parent link -> joints, sorted by joint name

    def walk(self):
        """Joints depth-first (pre-order) from the root, children visited in joint-name order.

        This order defines component indices (CLAUDE.md, "Conventions that matter"), so it must never change.
        """
        return self._walk(self.root)

    def _walk(self, link: str):
        # Iterative pre-order so very deep exports cannot hit Python's recursion limit.
        stack = list(reversed(self.child_joints.get(link, [])))
        while stack:
            j = stack.pop()
            yield j
            stack.extend(reversed(self.child_joints.get(j.child, [])))

    def world_poses(self) -> dict[str, np.ndarray]:
        """Frame of every link in the URDF's world (root link) frame, with every joint at q = 0."""
        poses = {self.root: np.eye(4)}
        for j in self._walk(self.root):
            poses[j.child] = poses[j.parent] @ j.origin
        return poses

    def subtree_links(self, link: str) -> list[str]:
        out = [link]
        for j in self._walk(link):
            out.append(j.child)
        return out


def _floats(text: str | None, n: int, default: tuple[float, ...], what: str) -> tuple[float, ...]:
    if text is None:
        return default
    try:
        values = tuple(float(v) for v in text.split())
    except ValueError:
        raise CadError(f"The robot file has a bad number in {what}: {text!r}. Re-export from Onshape.") from None
    if len(values) != n or not all(math.isfinite(v) for v in values):
        raise CadError(f"The robot file has a bad value in {what}: {text!r}. Re-export from Onshape.")
    return values


def _origin(element: ET.Element | None, what: str) -> np.ndarray:
    if element is None:
        return np.eye(4)
    x, y, z = _floats(element.get("xyz"), 3, (0.0, 0.0, 0.0), f"the origin of {what}")
    r, p, yaw = _floats(element.get("rpy"), 3, (0.0, 0.0, 0.0), f"the origin of {what}")
    # URDF rpy: fixed-axis roll about X, then pitch about Y, then yaw about Z.
    rot = axis_rotation("z", yaw) @ axis_rotation("y", p) @ axis_rotation("x", r)
    return make_transform(rot, (x, y, z))


def parse_urdf(text: str, source: str = "robot.urdf") -> Robot:
    """Parse URDF text and check the tree. Raises CadError naming the link or joint that is wrong."""
    try:
        root_el = ET.fromstring(text)
    except ET.ParseError as e:
        raise CadError(f"{source} is not a readable robot file ({e}). Re-export the assembly from Onshape.") from None
    if root_el.tag != "robot":
        raise CadError(f"{source} is not a URDF robot file. Export the assembly from Onshape as URDF.")

    links: dict[str, Link] = {}
    for el in root_el.findall("link"):
        name = el.get("name")
        if not name:
            raise CadError(f"{source} has a part (link) with no name. Re-export from Onshape.")
        if name in links:
            raise CadError(f"Two parts are both named {name!r}. Rename one of them in Onshape so every name is unique.")
        link = Link(name)
        for i, v in enumerate(el.findall("visual")):
            mesh = v.find("geometry/mesh")
            if mesh is None or not mesh.get("filename"):
                continue  # boxes, cylinders and spheres are not produced by Onshape; nothing to draw
            scale = _floats(mesh.get("scale"), 3, (1.0, 1.0, 1.0), f"the mesh scale of {name}")
            link.visuals.append(
                Visual(mesh.get("filename"), _origin(v.find("origin"), f"{name} visual {i}"), scale, v.get("name"))
            )
        links[name] = link

    joints: dict[str, Joint] = {}
    for el in root_el.findall("joint"):
        name = el.get("name")
        kind = el.get("type")
        if not name:
            raise CadError(f"{source} has a joint with no name. Re-export from Onshape.")
        if name in joints:
            raise CadError(f"Two mates are both named {name!r}. Rename one of them in Onshape so every name is unique.")
        if kind not in KNOWN_TYPES:
            raise CadError(
                f"Mate {name!r} has a type ({kind}) cad2ascope does not know. Use Revolute, Slider, or Fastened."
            )
        parent_el, child_el = el.find("parent"), el.find("child")
        parent = parent_el.get("link") if parent_el is not None else None
        child = child_el.get("link") if child_el is not None else None
        for link_name in (parent, child):
            if link_name not in links:
                raise CadError(
                    f"Mate {name!r} connects to a part named {link_name!r} that is not in the export. "
                    "Re-export from Onshape; if it repeats, check that the part is not suppressed."
                )
        axis_el = el.find("axis")  # not `or`: an Element with no children is falsy
        axis_text = axis_el.get("xyz") if axis_el is not None else None
        axis = np.array(_floats(axis_text, 3, (1.0, 0.0, 0.0), f"the axis of {name}"))
        if kind in MOVABLE:
            norm = float(np.linalg.norm(axis))
            if norm < 1e-12:
                raise CadError(f"Mate {name!r} has no direction of motion (zero axis). Re-create the mate in Onshape.")
            axis = axis / norm
        lim = el.find("limit")
        lower = upper = None
        if lim is not None and kind != "continuous":
            if lim.get("lower") is not None:
                lower = _floats(lim.get("lower"), 1, (0.0,), f"the lower limit of {name}")[0]
            if lim.get("upper") is not None:
                upper = _floats(lim.get("upper"), 1, (0.0,), f"the upper limit of {name}")[0]
        mim = el.find("mimic")
        mimic = None
        if mim is not None and mim.get("joint"):
            mimic = Mimic(
                mim.get("joint"),
                _floats(mim.get("multiplier"), 1, (1.0,), f"the relation on {name}")[0],
                _floats(mim.get("offset"), 1, (0.0,), f"the relation on {name}")[0],
            )
        joints[name] = Joint(
            name, kind, parent, child, _origin(el.find("origin"), f"mate {name}"), axis, lower, upper, mimic
        )

    if not links:
        raise CadError(
            f"{source} has no parts in it. Check that the export configuration does not suppress everything."
        )

    parent_joint: dict[str, Joint] = {}
    for j in joints.values():
        if j.child in parent_joint:
            other = parent_joint[j.child]
            raise CadError(
                f"Part {j.child!r} is attached to two moving paths (mates {other.name!r} and {j.name!r}). "
                "That is a closed loop, like a four-bar linkage, which URDF cannot describe. "
                "In the AdvantageScope export configuration, fasten all but one joint of the loop (PLAN §4 C4)."
            )
        parent_joint[j.child] = j

    roots = [name for name in links if name not in parent_joint]
    if not roots:
        raise CadError(
            "Every part has a parent, so the mates form a loop. Fasten one joint of the loop in the export configuration (PLAN §4 C4)."
        )
    if len(roots) > 1:
        shown = ", ".join(repr(r) for r in roots[:6]) + (" ..." if len(roots) > 6 else "")
        raise CadError(
            f"The export has {len(roots)} separate pieces that are not mated to each other: {shown}. "
            "Mate every part to the robot (Fastened is fine) in the export configuration, or suppress the loose ones."
        )

    child_joints: dict[str, list[Joint]] = {}
    for j in joints.values():
        child_joints.setdefault(j.parent, []).append(j)
    for kids in child_joints.values():
        kids.sort(key=lambda jj: jj.name)

    robot = Robot(root_el.get("name") or "robot", links, joints, roots[0], parent_joint, child_joints)
    reached = set(robot.subtree_links(robot.root))
    stranded = [n for n in links if n not in reached]
    if stranded:  # only possible with a cycle that does not include the root
        raise CadError(
            f"Parts {', '.join(repr(s) for s in stranded[:6])} are in a closed loop of mates. "
            "Fasten one joint of the loop in the export configuration (PLAN §4 C4)."
        )
    return robot
