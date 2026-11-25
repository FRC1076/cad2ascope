"""4x4 transform math and AdvantageScope rotation sequences.

AdvantageScope rule, confirmed in Phase 0 against the AdvantageScope source (docs/phase0-findings.md, B1 to B3):

- A ``rotations`` list is applied about the FIXED (extrinsic) axes, in list order. In
  ``src/shared/geometry.ts`` ``rotationSequenceToQuaternion`` premultiplies each step, so
  ``[r1, r2, ..., rn]`` gives ``R = Rn @ ... @ R2 @ R1``.
- ``position`` is set on the same three.js object as that rotation, so the local transform is
  ``Translate(position) @ Rotate(rotations)``: rotate first, then shift in the parent frame.
- A component is drawn at ``robot_pose @ component_pose @ zeroed``, where ``zeroed`` is built from
  ``zeroedRotations`` and ``zeroedPosition`` the same way.

The writer below always emits three steps, x then y then z, so ``R = Rz(c) @ Ry(b) @ Rx(a)``. That is
the same matrix as URDF ``rpy="a b c"`` and WPILib's ``Rotation3d(roll, pitch, yaw)``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TypedDict

import numpy as np

AXES = {"x": 0, "y": 1, "z": 2}


class Rotation(TypedDict):
    axis: str
    degrees: float


def axis_rotation(axis: str, radians: float) -> np.ndarray:
    """3x3 right-handed rotation about one coordinate axis."""
    c, s = math.cos(radians), math.sin(radians)
    if axis == "x":
        return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])
    if axis == "y":
        return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    if axis == "z":
        return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    raise ValueError(f"axis must be 'x', 'y', or 'z', not {axis!r}")


def sequence_to_matrix(rotations: Sequence[Rotation]) -> np.ndarray:
    """3x3 matrix for an AdvantageScope rotation sequence (fixed axes, applied in list order)."""
    r = np.eye(3)
    for step in rotations:
        r = axis_rotation(step["axis"], math.radians(step["degrees"])) @ r
    return r


def matrix_to_sequence(r: np.ndarray) -> list[Rotation]:
    """Inverse of :func:`sequence_to_matrix` for a proper rotation matrix.

    Returns ``[x, y, z]`` steps with ``R = Rz(yaw) @ Ry(pitch) @ Rx(roll)``. Near pitch = ±90° (gimbal
    lock) roll is set to 0 and yaw absorbs the rest, which still reproduces the same matrix.
    """
    r = np.asarray(r, dtype=float)
    if r.shape != (3, 3):
        raise ValueError(f"expected a 3x3 rotation matrix, got shape {r.shape}")
    # R = Rz(y) Ry(p) Rx(r):  R[2,0] = -sin(p),  R[2,1] = cos(p) sin(r),  R[2,2] = cos(p) cos(r),
    #                         R[1,0] = sin(y) cos(p),  R[0,0] = cos(y) cos(p)
    cos_p = math.hypot(r[0, 0], r[1, 0])
    pitch = math.atan2(-r[2, 0], cos_p)
    if cos_p > 1e-9:
        roll = math.atan2(r[2, 1], r[2, 2])
        yaw = math.atan2(r[1, 0], r[0, 0])
    else:
        # Gimbal lock: only roll - yaw (pitch = +90°) or roll + yaw (pitch = -90°) is defined.
        roll = 0.0
        yaw = math.atan2(-r[0, 1], r[1, 1])
    return [
        {"axis": "x", "degrees": math.degrees(roll)},
        {"axis": "y", "degrees": math.degrees(pitch)},
        {"axis": "z", "degrees": math.degrees(yaw)},
    ]


def make_transform(rotation: np.ndarray | None = None, translation: Sequence[float] = (0.0, 0.0, 0.0)) -> np.ndarray:
    """4x4 homogeneous transform from a 3x3 rotation and a translation in meters."""
    t = np.eye(4)
    if rotation is not None:
        t[:3, :3] = rotation
    t[:3, 3] = translation
    return t


def invert(t: np.ndarray) -> np.ndarray:
    """Inverse of a rigid 4x4 transform (exact transpose, no general matrix inverse)."""
    r = t[:3, :3]
    return make_transform(r.T, -r.T @ t[:3, 3])


def to_config(t: np.ndarray) -> tuple[list[Rotation], list[float]]:
    """``(rotations, position)`` for config.json such that AdvantageScope rebuilds ``t`` exactly."""
    return matrix_to_sequence(t[:3, :3]), [float(v) for v in t[:3, 3]]


def from_config(rotations: Sequence[Rotation], position: Sequence[float]) -> np.ndarray:
    """4x4 transform AdvantageScope builds from a ``rotations`` list and a ``position``."""
    return make_transform(sequence_to_matrix(rotations), position)


def zeroed_config(t0: np.ndarray) -> tuple[list[Rotation], list[float]]:
    """``zeroedRotations`` and ``zeroedPosition`` for a component whose root link sits at ``t0`` (robot frame).

    The component mesh is written in robot frame at the export pose, so the zeroed transform is ``t0^-1``.
    Publishing ``t0`` as the component pose then draws the mesh exactly where it was exported (PLAN §6.4).
    """
    return to_config(invert(t0))
