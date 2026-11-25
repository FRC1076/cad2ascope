"""Phase 3: RobotModel.java generation.

Three independent checks:
1. The numpy reference (codegen.fk) against a separate forward-kinematics walk of each fixture's robot.urdf with the
   joints actually moved (scipy rotations, link by link), including cameras and frames on moving parts.
2. Golden RobotModel.java per fixture (CAD2ASCOPE_UPDATE_GOLDEN=1 rewrites them; review the diff).
3. The generated Java compiled with -Werror against real WPILib jars and its JUnit test run (skipped if no WPILib
   or JDK is found; see tests/java_harness.py).
"""

from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

import java_harness
from cad2ascope.build import analyze
from cad2ascope.codegen import _joints, _signals, fk, generate, java_const, java_method, quaternion
from cad2ascope.config import load_config
from cad2ascope.errors import Warnings
from test_fixtures import FIXTURES, VALID

GOLDEN = Path(__file__).resolve().parent / "golden"


def _model(name):
    cfg = load_config(FIXTURES / name / "advantagescope.yaml")
    return analyze(FIXTURES / f"{name}.zip", cfg, FIXTURES)


def _urdf_fk(name: str, joint_values: dict[str, float]) -> dict[str, np.ndarray]:
    """Link frames in the URDF world with the named joints moved; written without cad2ascope code."""
    robot = ET.parse(FIXTURES / name / "robot.urdf").getroot()

    def origin(j):
        o = j.find("origin")
        xyz = [float(v) for v in o.get("xyz").split()]
        rpy = [float(v) for v in o.get("rpy").split()]
        t = np.eye(4)
        t[:3, :3] = Rotation.from_euler("xyz", rpy).as_matrix()  # lowercase = extrinsic = URDF rpy
        t[:3, 3] = xyz
        return t

    joints = robot.findall("joint")
    children = {j.find("child").get("link") for j in joints}
    root = next(link.get("name") for link in robot.findall("link") if link.get("name") not in children)
    world = {root: np.eye(4)}
    pending = list(joints)
    while pending:
        for j in list(pending):
            parent = j.find("parent").get("link")
            if parent not in world:
                continue
            q = joint_values.get(j.get("name"), 0.0)
            motion = np.eye(4)
            if j.get("type") in ("revolute", "continuous"):
                axis = np.array([float(v) for v in j.find("axis").get("xyz").split()])
                motion[:3, :3] = Rotation.from_rotvec(axis / np.linalg.norm(axis) * q).as_matrix()
            elif j.get("type") == "prismatic":
                axis = np.array([float(v) for v in j.find("axis").get("xyz").split()])
                motion[:3, 3] = axis / np.linalg.norm(axis) * q
            world[j.find("child").get("link")] = world[parent] @ origin(j) @ motion
            pending.remove(j)
    return world


@pytest.mark.parametrize("name", VALID)
def test_reference_fk_matches_urdf_with_joints_moved(name):
    model, cams, frames = _model(name)
    w = Warnings()
    signals = _signals(model, w)
    joints = _joints(model, {s.name: i for i, s in enumerate(signals)})
    rng = np.random.default_rng(1076)
    for trial in range(5):
        values = [s.min + rng.random() * (s.max - s.min) if s.max > s.min else rng.uniform(-1, 1) for s in signals]
        if trial == 0:
            values = [0.0] * len(signals)
        poses = fk(joints, values)
        q_joint = {j.name: j.scale * (values[j.signal] - j.zero_offset) for j in joints}
        world = _urdf_fk(name, q_joint)
        robot_from_world = np.linalg.inv(world[model.config.robot.origin_frame])
        for comp, pose in zip(model.components, poses, strict=True):
            np.testing.assert_allclose(pose, robot_from_world @ world[comp.root_link], atol=1e-9)
        for item in cams + frames:
            if item.component is not None:
                local = np.linalg.inv(model.components[item.component].T0) @ item.T
                np.testing.assert_allclose(
                    poses[item.component] @ local, robot_from_world @ world[item.link], atol=1e-9
                )


@pytest.mark.parametrize("name", VALID)
def test_generated_java_matches_golden(name):
    model, cams, frames = _model(name)
    java, test = generate(model, cams, frames, f"{name}.zip (fixture)")
    golden_dir = GOLDEN / name
    if os.environ.get("CAD2ASCOPE_UPDATE_GOLDEN"):
        golden_dir.mkdir(parents=True, exist_ok=True)
        (golden_dir / "RobotModel.java").write_text(java)
        (golden_dir / "RobotModelTest.java").write_text(test)
    assert (golden_dir / "RobotModel.java").is_file(), "run with CAD2ASCOPE_UPDATE_GOLDEN=1 and review the files"
    assert java == (golden_dir / "RobotModel.java").read_text()
    assert test == (golden_dir / "RobotModelTest.java").read_text()


@pytest.mark.skipif(
    not java_harness.available() and not os.environ.get("CAD2ASCOPE_REQUIRE_JAVA"),
    reason="no WPILib Maven folder or JDK found",
)
@pytest.mark.parametrize("name", VALID)
def test_generated_java_compiles_and_its_tests_pass(name, tmp_path):
    model, cams, frames = _model(name)
    java, test = generate(model, cams, frames, f"{name}.zip (fixture)")
    result = java_harness.compile_and_test(java, test, model.config.codegen.java_package, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_signal_ranges_follow_ratio_direction_and_offset():
    model, _, _ = _model("coupled")
    signals = {s.name: s for s in _signals(model, Warnings())}
    # stage1 and carriage both 0..0.7 m in CAD with ratio 0.5, so the elevator signal may go 0..1.4 m
    assert (signals["elevator"].min, signals["elevator"].max) == pytest.approx((0.0, 1.4))
    # wrist -1.5..1.5 rad in CAD, zero_offset 10 degrees
    off = math.radians(10)
    assert (signals["wrist"].min, signals["wrist"].max) == pytest.approx((-1.5 + off, 1.5 + off))
    model, _, _ = _model("nested_chain")
    hood = {s.name: s for s in _signals(model, Warnings())}["hood"]
    assert (hood.min, hood.max) == pytest.approx((-0.8, 0.0))  # direction -1 flips 0..0.8


def test_names():
    assert java_const("front_left") == "FRONT_LEFT"
    assert java_const("FRONT-LEFT cam") == "FRONT_LEFT_CAM"
    assert java_const("2nd") == "N_2ND"
    assert java_method("FRONT_LEFT") == "frontLeft"
    assert java_method("turret") == "turret"


def test_quaternion_is_normalized_with_positive_w():
    for r in Rotation.random(50, random_state=7):
        w, x, y, z = quaternion(r.as_matrix())
        assert w >= 0 and math.isclose(w * w + x * x + y * y + z * z, 1.0, abs_tol=1e-12)
        np.testing.assert_allclose(Rotation.from_quat([x, y, z, w]).as_matrix(), r.as_matrix(), atol=1e-12)


@pytest.mark.skipif(
    not java_harness.available() and not os.environ.get("CAD2ASCOPE_REQUIRE_JAVA"),
    reason="no WPILib Maven folder or JDK found",
)
def test_visualizer_and_sweep_templates_compile(tmp_path):
    from cad2ascope.codegen import robot_code_templates, visualizer_package

    model, cams, frames = _model("coupled")
    java, _ = generate(model, cams, frames, "coupled.zip (fixture)")
    pkg = model.config.codegen.java_package
    result = java_harness.compile_robot_code(java, robot_code_templates(pkg), pkg, visualizer_package(pkg), tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_run_writes_code_and_keeps_hand_owned_files(tmp_path, capsys):
    from cad2ascope.cli import main

    args = [
        "run",
        "-c",
        str(FIXTURES / "coupled" / "advantagescope.yaml"),
        "--zip",
        str(FIXTURES / "coupled.zip"),
        "-o",
        str(tmp_path / "assets"),
        "--repo-root",
        str(tmp_path),
    ]
    assert main(args) == 0
    gen = tmp_path / "src/main/java/frc/robot/generated/RobotModel.java"
    vis = tmp_path / "src/main/java/frc/robot/visualization/RobotVisualizer.java"
    assert gen.is_file() and (tmp_path / "src/test/java/frc/robot/generated/RobotModelTest.java").is_file()
    assert "j_elevator_carriage" in gen.read_text() and "coupled.zip (sha256 " in gen.read_text()
    assert "(yours to edit from now on)" in capsys.readouterr().out
    vis.write_text("// edited by the software team")
    assert main(args) == 0
    assert vis.read_text() == "// edited by the software team"
