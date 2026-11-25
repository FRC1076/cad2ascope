"""Checks that the fixture oracle (tests/fixtures/*/expected.json) is in place and self-consistent.

These tests do not exercise the converter yet. They pin down the oracle so that Phase 1 code is
tested against something independent of itself:

- every fixture in index.json exists, with a zip holding only the URDF and meshes
- every team config validates against spec/advantagescope.schema.json
- expected.json agrees with a forward-kinematics walk of robot.urdf done here, separately from
  make_fixtures.py (which builds the URDF and the oracle from the same Python objects)
- zeroed == inverse(T0), and every rotation block is a proper rotation
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import jsonschema
import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCHEMA = json.loads((ROOT / "spec" / "advantagescope.schema.json").read_text())
INDEX = json.loads((FIXTURES / "index.json").read_text())
VALID = [f["name"] for f in INDEX if f["valid"]]
ALL = [f["name"] for f in INDEX]


def _rpy(r: float, p: float, y: float) -> np.ndarray:
    # URDF: R = Rz(yaw) @ Ry(pitch) @ Rx(roll). Written out from scratch, not imported from the generator.
    def rx(a):
        return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])

    def ry(a):
        return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])

    def rz(a):
        return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])

    return rz(y) @ ry(p) @ rx(r)


def _origin(joint: ET.Element) -> np.ndarray:
    o = joint.find("origin")
    xyz = [float(v) for v in (o.get("xyz", "0 0 0") if o is not None else "0 0 0").split()]
    rpy = [float(v) for v in (o.get("rpy", "0 0 0") if o is not None else "0 0 0").split()]
    t = np.eye(4)
    t[:3, :3] = _rpy(*rpy)
    t[:3, 3] = xyz
    return t


def _link_frames(urdf: Path) -> dict[str, np.ndarray]:
    """World frame of every link at q = 0, from the URDF text alone."""
    robot = ET.parse(urdf).getroot()
    joints = robot.findall("joint")
    child_of = {j.find("parent").get("link"): [] for j in joints}
    for j in joints:
        child_of[j.find("parent").get("link")].append(j)
    children = {j.find("child").get("link") for j in joints}
    roots = [ln.get("name") for ln in robot.findall("link") if ln.get("name") not in children]
    assert len(roots) == 1
    world = {roots[0]: np.eye(4)}
    stack = [roots[0]]
    while stack:
        link = stack.pop()
        for j in child_of.get(link, []):
            c = j.find("child").get("link")
            world[c] = world[link] @ _origin(j)
            stack.append(c)
    return world


def _load(name: str) -> tuple[dict, dict]:
    cfg = yaml.safe_load((FIXTURES / name / "advantagescope.yaml").read_text())
    exp = json.loads((FIXTURES / name / "expected.json").read_text())
    return cfg, exp


def test_index_lists_seven_fixtures():
    assert len(ALL) == 7
    assert sum(not f["valid"] for f in INDEX) == 2


@pytest.mark.parametrize("name", ALL)
def test_fixture_files_present(name):
    folder = FIXTURES / name
    assert (folder / "robot.urdf").is_file()
    assert (folder / "advantagescope.yaml").is_file()
    entry = next(f for f in INDEX if f["name"] == name)
    if entry["valid"]:
        assert (folder / "expected.json").is_file()
    else:
        assert (folder / "expected_error.txt").read_text().strip() == entry["expect_error_mentions"]


@pytest.mark.parametrize("name", ALL)
def test_zip_matches_folder_and_hides_answers(name):
    folder = FIXTURES / name
    with zipfile.ZipFile(FIXTURES / f"{name}.zip") as z:
        files = {n for n in z.namelist() if not n.endswith("/")}
        assert "robot.urdf" in files
        assert not files & {"advantagescope.yaml", "expected.json", "expected_error.txt"}
        for n in files:
            assert z.read(n) == (folder / n).read_bytes(), n


@pytest.mark.parametrize("name", ALL)
def test_config_matches_schema(name):
    cfg = yaml.safe_load((FIXTURES / name / "advantagescope.yaml").read_text())
    jsonschema.validate(cfg, SCHEMA)


def test_example_config_matches_schema():
    jsonschema.validate(yaml.safe_load((ROOT / "spec" / "advantagescope.example.yaml").read_text()), SCHEMA)


@pytest.mark.parametrize("name", VALID)
def test_oracle_agrees_with_urdf(name):
    cfg, exp = _load(name)
    world = _link_frames(FIXTURES / name / "robot.urdf")
    robot_from_world = np.linalg.inv(world[cfg["robot"]["origin_frame"]])
    for comp in exp["components"]:
        t0 = np.array(comp["T0"])
        np.testing.assert_allclose(t0, robot_from_world @ world[comp["child_link"]], atol=1e-8)
    for prefix_key, default, section in (("cameras", "cam_", "cameras"), ("frames", "frame_", "frames")):
        prefix = cfg.get(prefix_key, {}).get("frame_prefix", default)
        for short, mat in exp[section].items():
            np.testing.assert_allclose(np.array(mat), robot_from_world @ world[prefix + short], atol=1e-8)


@pytest.mark.parametrize("name", VALID)
def test_oracle_components_are_the_listed_joints_in_dfs_order(name):
    cfg, exp = _load(name)
    joints = [c["joint"] for c in exp["components"]]
    assert sorted(joints) == sorted(cfg["joints"])
    assert [c["index"] for c in exp["components"]] == list(range(len(joints)))


@pytest.mark.parametrize("name", VALID)
def test_oracle_transforms_are_rigid_and_inverse(name):
    _, exp = _load(name)
    mats = [np.array(c["T0"]) for c in exp["components"]]
    mats += [np.array(m) for m in exp["cameras"].values()] + [np.array(m) for m in exp["frames"].values()]
    for m in mats:
        r = m[:3, :3]
        np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-8)
        assert np.linalg.det(r) == pytest.approx(1.0, abs=1e-8)
        np.testing.assert_allclose(m[3], [0, 0, 0, 1])
    for c in exp["components"]:
        np.testing.assert_allclose(np.array(c["zeroed"]) @ np.array(c["T0"]), np.eye(4), atol=1e-8)
