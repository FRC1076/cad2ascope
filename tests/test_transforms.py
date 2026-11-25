"""cad2ascope.transforms against a port of AdvantageScope's own math (tests/ascope_reference.py).

PHASE0-CHECKLIST section B: round-trip 1,000 random transforms within 1e-9, and reproduce the composition
robot pose @ component pose @ zeroed transform.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from ascope_reference import camera_world_rotation, component_world, config_object
from cad2ascope import transforms as tf

FIXTURES = Path(__file__).resolve().parent / "fixtures"
INDEX = json.loads((FIXTURES / "index.json").read_text())
VALID = [f["name"] for f in INDEX if f["valid"]]
RNG_SEED = 1076


def random_rotation(rng: np.random.Generator) -> np.ndarray:
    """Uniform random rotation (QR of a Gaussian matrix, sign-fixed to det = +1)."""
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q = q @ np.diag(np.sign(np.diag(r)))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def random_transform(rng: np.random.Generator) -> np.ndarray:
    return tf.make_transform(random_rotation(rng), rng.uniform(-2.0, 2.0, size=3))


def test_sequence_uses_fixed_axes_in_list_order():
    # Fixed axes: x 90° takes +Y to +Z, then z 90° about the fixed Z leaves +Z alone, so +Y ends at +Z.
    # Moving axes would be Rx(90) @ Rz(90), which takes +Y to -X. The two rules disagree on this case.
    seq = [{"axis": "x", "degrees": 90}, {"axis": "z", "degrees": 90}]
    np.testing.assert_allclose(tf.sequence_to_matrix(seq) @ [0, 1, 0], [0, 0, 1], atol=1e-12)
    np.testing.assert_allclose(config_object(seq, [0, 0, 0])[:3, :3] @ [0, 1, 0], [0, 0, 1], atol=1e-12)
    moving_axes = tf.axis_rotation("x", math.pi / 2) @ tf.axis_rotation("z", math.pi / 2)
    np.testing.assert_allclose(moving_axes @ [0, 1, 0], [-1, 0, 0], atol=1e-12)


def test_position_applies_after_rotation():
    seq = [{"axis": "z", "degrees": 90}]
    m = config_object(seq, [1.0, 2.0, 3.0])
    # The point (1, 0, 0) rotates to (0, 1, 0), then shifts by the position.
    np.testing.assert_allclose(m @ [1, 0, 0, 1], [1.0, 3.0, 3.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(tf.from_config(seq, [1.0, 2.0, 3.0]), m, atol=1e-12)


def test_random_sequences_match_advantagescope():
    rng = np.random.default_rng(RNG_SEED)
    for _ in range(1000):
        n = int(rng.integers(0, 6))
        seq = [{"axis": str(rng.choice(["x", "y", "z"])), "degrees": float(rng.uniform(-360, 360))} for _ in range(n)]
        np.testing.assert_allclose(tf.sequence_to_matrix(seq), config_object(seq, [0, 0, 0])[:3, :3], atol=1e-12)


def test_round_trip_1000_random_transforms():
    rng = np.random.default_rng(RNG_SEED)
    worst = 0.0
    for _ in range(1000):
        t = random_transform(rng)
        rotations, position = tf.to_config(t)
        rebuilt = config_object(rotations, position)  # what AdvantageScope will build from config.json
        worst = max(worst, float(np.max(np.abs(rebuilt - t))))
    assert worst < 1e-9, worst


@pytest.mark.parametrize("pitch_deg", [90.0, -90.0])
def test_round_trip_at_gimbal_lock(pitch_deg):
    for roll, yaw in [(0.0, 0.0), (30.0, -45.0), (170.0, 120.0)]:
        r = tf.sequence_to_matrix(
            [{"axis": "x", "degrees": roll}, {"axis": "y", "degrees": pitch_deg}, {"axis": "z", "degrees": yaw}]
        )
        rotations, _ = tf.to_config(tf.make_transform(r))
        np.testing.assert_allclose(config_object(rotations, [0, 0, 0])[:3, :3], r, atol=1e-9)


def test_writer_matches_urdf_rpy_and_wpilib_order():
    roll, pitch, yaw = 0.1, -0.7, 2.3
    r = tf.axis_rotation("z", yaw) @ tf.axis_rotation("y", pitch) @ tf.axis_rotation("x", roll)
    seq = tf.matrix_to_sequence(r)
    assert [s["axis"] for s in seq] == ["x", "y", "z"]
    np.testing.assert_allclose([s["degrees"] for s in seq], np.degrees([roll, pitch, yaw]), atol=1e-12)


def test_published_t0_draws_component_where_it_was_exported():
    """PLAN §6.4: with P_i(0) = T0_i, every vertex of the component mesh lands where the base model would put it."""
    rng = np.random.default_rng(RNG_SEED)
    for _ in range(200):
        robot_pose = random_transform(rng)
        t0 = random_transform(rng)
        zr, zp = tf.zeroed_config(t0)
        config = {"rotations": [], "position": [0, 0, 0], "components": [{"zeroedRotations": zr, "zeroedPosition": zp}]}
        np.testing.assert_allclose(component_world(robot_pose, t0, config, 0), robot_pose, atol=1e-9)


def test_moving_a_joint_moves_the_component_about_its_own_frame():
    """Publishing T0 @ M draws the mesh at robot @ T0 @ M @ T0^-1: motion M expressed in the component root frame."""
    rng = np.random.default_rng(RNG_SEED + 1)
    robot_pose, t0, motion = (random_transform(rng) for _ in range(3))
    zr, zp = tf.zeroed_config(t0)
    config = {"components": [{"zeroedRotations": zr, "zeroedPosition": zp}]}
    expected = robot_pose @ t0 @ motion @ tf.invert(t0)
    np.testing.assert_allclose(component_world(robot_pose, t0 @ motion, config, 0), expected, atol=1e-9)


def test_no_published_poses_uses_robot_level_config():
    """B4: without component poses, components get the robot-level transform, which cad2ascope leaves at identity."""
    rng = np.random.default_rng(RNG_SEED + 2)
    robot_pose = random_transform(rng)
    config = {
        "rotations": [],
        "position": [0, 0, 0],
        "components": [{"zeroedRotations": [], "zeroedPosition": [1, 2, 3]}],
    }
    np.testing.assert_allclose(component_world(robot_pose, None, config, 0), robot_pose, atol=1e-12)


@pytest.mark.parametrize("name", VALID)
def test_fixture_zeroed_values_rebuild_the_oracle(name):
    exp = json.loads((FIXTURES / name / "expected.json").read_text())
    for comp in exp["components"]:
        zr, zp = tf.zeroed_config(np.array(comp["T0"]))
        np.testing.assert_allclose(config_object(zr, zp), np.array(comp["zeroed"]), atol=1e-8)


def test_camera_entry_looks_along_plus_x_with_plus_z_up():
    """B5: a cameras entry with no rotations looks along robot +X, image up = +Z (WPILib camera frame)."""
    r = camera_world_rotation([])
    np.testing.assert_allclose(r @ [0, 0, -1], [1, 0, 0], atol=1e-12)  # three.js camera looks down its -Z
    np.testing.assert_allclose(r @ [0, 1, 0], [0, 0, 1], atol=1e-12)  # three.js camera up is its +Y


def test_camera_rotations_use_same_rule_as_components():
    # 20° pitch about +Y (WPILib: tilted down) then 50° yaw: view direction must point down and to the left.
    seq = [{"axis": "y", "degrees": 20}, {"axis": "z", "degrees": 50}]
    view = camera_world_rotation(seq) @ [0, 0, -1]
    expected = tf.sequence_to_matrix(seq) @ [1, 0, 0]
    np.testing.assert_allclose(view, expected, atol=1e-12)
    assert view[2] == pytest.approx(-math.sin(math.radians(20)))
    assert view[1] > 0
