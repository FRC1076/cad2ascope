"""A line-by-line port of the AdvantageScope math that places robot components, used as a test oracle.

Ported from AdvantageScope commit ea60b46 (2026-11-25), https://github.com/Mechanical-Advantage/AdvantageScope:

- ``rotation_sequence_to_quaternion``: src/shared/geometry.ts, ``rotationSequenceToQuaternion``
  (starts at identity and ``premultiply``s each axis-angle step).
- ``component_world``: src/shared/renderers/field3d/objectManagers/RobotManager.ts, the "Update components"
  block. ``dummyConfigPose`` is a child of ``dummyUserPose``, which is a child of ``dummyRobotPose``.
- ``CAMERA_ROTATION``: src/shared/renderers/Field3dRendererImpl.ts.

Quaternions follow three.js: ``(x, y, z, w)``, Hamilton product, ``a.premultiply(b)`` sets ``a = b * a``.
Nothing here imports cad2ascope, so the tests compare two independent implementations.
"""

from __future__ import annotations

import math

import numpy as np

Quat = tuple[float, float, float, float]  # x, y, z, w


def quat_from_axis_angle(axis: tuple[float, float, float], angle: float) -> Quat:
    h = angle / 2
    s = math.sin(h)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(h))


def quat_multiply(a: Quat, b: Quat) -> Quat:
    """three.js multiplyQuaternions(a, b)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        ax * bw + aw * bx + ay * bz - az * by,
        ay * bw + aw * by + az * bx - ax * bz,
        az * bw + aw * bz + ax * by - ay * bx,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def rotation_sequence_to_quaternion(rotations: list[dict]) -> Quat:
    q: Quat = (0.0, 0.0, 0.0, 1.0)
    for step in rotations:
        axis = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}[step["axis"]]
        q = quat_multiply(quat_from_axis_angle(axis, math.radians(step["degrees"])), q)  # premultiply
    return q


def quat_to_matrix(q: Quat) -> np.ndarray:
    """Rotation part of three.js Matrix4.compose / makeRotationFromQuaternion."""
    x, y, z, w = q
    x2, y2, z2 = x + x, y + y, z + z
    xx, xy, xz = x * x2, x * y2, x * z2
    yy, yz, zz = y * y2, y * z2, z * z2
    wx, wy, wz = w * x2, w * y2, w * z2
    return np.array(
        [
            [1 - (yy + zz), xy - wz, xz + wy],
            [xy + wz, 1 - (xx + zz), yz - wx],
            [xz - wy, yz + wx, 1 - (xx + yy)],
        ]
    )


def compose(position, q: Quat) -> np.ndarray:
    """three.js Object3D local matrix: Matrix4.compose(position, quaternion, scale = 1)."""
    m = np.eye(4)
    m[:3, :3] = quat_to_matrix(q)
    m[:3, 3] = position
    return m


def config_object(rotations: list[dict], position) -> np.ndarray:
    """Local matrix of dummyConfigPose after rotation.setFromQuaternion(...) and position.set(...)."""
    return compose(position, rotation_sequence_to_quaternion(rotations))


def component_world(robot_pose: np.ndarray, user_pose: np.ndarray | None, config: dict, index: int) -> np.ndarray:
    """World matrix AdvantageScope uses for component ``index`` (0-based, i.e. model_<index>.glb).

    ``robot_pose`` and ``user_pose`` are 4x4 matrices. ``user_pose`` is None when no component poses are published,
    in which case AdvantageScope falls back to the robot-level ``rotations`` and ``position``.
    """
    if user_pose is None:
        local = config_object(config.get("rotations", []), config.get("position", [0, 0, 0]))
        user = np.eye(4)
    else:
        comp = config["components"][index]
        local = config_object(comp["zeroedRotations"], comp["zeroedPosition"])
        user = user_pose
    return robot_pose @ user @ local


# Field3dRendererImpl.ts: applied after a camera entry's rotations, to turn a three.js camera (looks down -Z, +Y up)
CAMERA_ROTATION: Quat = rotation_sequence_to_quaternion([{"axis": "z", "degrees": -90}, {"axis": "y", "degrees": -90}])


def camera_world_rotation(rotations: list[dict]) -> np.ndarray:
    """rotationSequenceToQuaternion(cameraConfig.rotations).multiply(CAMERA_ROTATION), as a matrix."""
    return quat_to_matrix(quat_multiply(rotation_sequence_to_quaternion(rotations), CAMERA_ROTATION))
