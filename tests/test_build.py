"""`cad2ascope build` on every fixture, checked against the independent oracle (expected.json) and golden files.

Set CAD2ASCOPE_UPDATE_GOLDEN=1 to rewrite tests/golden/<fixture>/config.json after an intended change, then review
the diff before committing.
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import numpy as np
import pytest
import trimesh

from ascope_reference import component_world, config_object
from cad2ascope.build import build
from cad2ascope.errors import CadError
from test_fixtures import FIXTURES, INDEX, VALID, _link_frames

GOLDEN = Path(__file__).resolve().parent / "golden"
INVALID = [f for f in INDEX if not f["valid"]]


def run_build(name: str, out: Path, config: Path | None = None):
    return build(FIXTURES / f"{name}.zip", config or FIXTURES / name / "advantagescope.yaml", out, repo_root=out)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("assets")
    return {name: run_build(name, out) for name in VALID}


def glb_json(path: Path) -> dict:
    data = path.read_bytes()
    assert data[:4] == b"glTF"
    n = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + n])


@pytest.mark.parametrize("name", VALID)
def test_config_json_matches_golden(name, built):
    actual = json.loads((built[name].folder / "config.json").read_text())
    golden = GOLDEN / name / "config.json"
    if os.environ.get("CAD2ASCOPE_UPDATE_GOLDEN"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(json.dumps(actual, indent=2) + "\n")
    assert golden.is_file(), f"no golden file yet; run with CAD2ASCOPE_UPDATE_GOLDEN=1 and review {golden}"
    assert actual == json.loads(golden.read_text())


@pytest.mark.parametrize("name", VALID)
def test_components_match_oracle(name, built):
    exp = json.loads((FIXTURES / name / "expected.json").read_text())
    result = built[name]
    assert [c.joint.name for c in result.model.components] == [c["joint"] for c in exp["components"]]
    assert sorted(j.name for j in result.model.frozen) == exp["frozen_joints"]
    cfg = json.loads((result.folder / "config.json").read_text())
    assert cfg["rotations"] == [] and cfg["position"] == [0.0, 0.0, 0.0]
    for comp, e in zip(cfg["components"], exp["components"], strict=True):
        # What AdvantageScope rebuilds from the written numbers must equal the oracle's inverse(T0).
        np.testing.assert_allclose(
            config_object(comp["zeroedRotations"], comp["zeroedPosition"]), e["zeroed"], atol=1e-8
        )
    for comp, e in zip(result.model.components, exp["components"], strict=True):
        np.testing.assert_allclose(comp.T0, e["T0"], atol=1e-9)


@pytest.mark.parametrize("name", VALID)
def test_cameras_and_frames_match_oracle(name, built):
    exp = json.loads((FIXTURES / name / "expected.json").read_text())
    result = built[name]
    cfg = json.loads((result.folder / "config.json").read_text())
    assert [c["name"] for c in cfg["cameras"]] == [c.name for c in result.cameras]
    assert {c["name"] for c in cfg["cameras"]} == set(exp["cameras"])
    for cam in cfg["cameras"]:
        np.testing.assert_allclose(
            config_object(cam["rotations"], cam["position"]), exp["cameras"][cam["name"]], atol=1e-8
        )
    assert {f.name: f.T for f in result.frames}.keys() == exp["frames"].keys()
    for f in result.frames:
        np.testing.assert_allclose(f.T, exp["frames"][f.name], atol=1e-9)


@pytest.mark.parametrize("name", VALID)
def test_every_mesh_is_where_the_urdf_puts_it(name, built):
    """Each link's box, in the .glb of the group it belongs to, is centered where FK of robot.urdf says."""
    result = built[name]
    model = result.model
    world = _link_frames(FIXTURES / name / "robot.urdf")
    robot_from_world = np.linalg.inv(world[model.config.robot.origin_frame])
    files = {"model.glb": model.base_links} | {c.file: c.links for c in model.components}
    for file, links in files.items():
        scene = trimesh.load(result.folder / file, force="scene")
        for link in links:
            visuals = model.robot.links[link].visuals
            if not visuals:
                continue
            center_local = visuals[0].origin[:3, 3]
            expected = (robot_from_world @ world[link] @ np.append(center_local, 1.0))[:3]
            geom = scene.geometry[link]
            np.testing.assert_allclose(geom.bounds.mean(axis=0), expected, atol=1e-6)


@pytest.mark.parametrize("name", VALID)
def test_components_line_up_with_base_when_t0_is_published(name, built):
    """PLAN §6.4: publishing T0 for every component draws each mesh exactly where it was exported (B3)."""
    result = built[name]
    cfg = json.loads((result.folder / "config.json").read_text())
    robot_pose = np.eye(4)
    robot_pose[:3, 3] = [3.0, -1.0, 0.0]  # anywhere on the field
    for comp in result.model.components:
        world = component_world(robot_pose, comp.T0, cfg, comp.index)
        np.testing.assert_allclose(world, robot_pose, atol=1e-8)


@pytest.mark.parametrize("name", VALID)
def test_glb_files_render_in_advantagescope(name, built):
    """B6: every primitive has normals and a material with a base color, or AdvantageScope drops or greys it."""
    result = built[name]
    files = ["model.glb"] + [c.file for c in result.model.components]
    assert sorted(p.name for p in result.folder.glob("*.glb")) == sorted(files)
    for file in files:
        g = glb_json(result.folder / file)
        for mesh in g.get("meshes", []):
            for prim in mesh["primitives"]:
                assert "NORMAL" in prim["attributes"], (file, mesh.get("name"))
                assert "COLOR_0" not in prim["attributes"]
                mat = g["materials"][prim["material"]]
                assert len(mat["pbrMetallicRoughness"]["baseColorFactor"]) == 4


def test_fixture_colors_survive(built):
    g = glb_json(built["single_revolute"].folder / "model_0.glb")
    color = g["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"]
    np.testing.assert_allclose(color, np.array([220, 120, 0, 255]) / 255, atol=1e-6)


@pytest.mark.parametrize("name", VALID)
def test_manifest_records_the_build(name, built):
    result = built[name]
    m = json.loads((result.folder / "manifest.json").read_text())
    assert m["source"]["input"] == f"{name}.zip"
    assert len(m["source"]["sha256"]) == 64
    assert [c["joint"] for c in m["components"]] == [c.joint.name for c in result.model.components]
    assert m["frozen_joints"] == [j.name for j in result.model.frozen]
    assert m["warnings"] == result.warnings
    for c in m["components"]:
        assert (result.folder / c["file"]).stat().st_size == c["bytes"]


def test_build_is_deterministic(tmp_path):
    a = run_build("nested_chain", tmp_path / "a").folder
    b = run_build("nested_chain", tmp_path / "b").folder
    for f in sorted(a.iterdir()):
        assert f.read_bytes() == (b / f.name).read_bytes(), f.name


def test_rebuild_removes_stale_component_files(tmp_path):
    folder = run_build("coupled", tmp_path).folder
    assert (folder / "model_2.glb").exists()
    cfg = (FIXTURES / "coupled" / "advantagescope.yaml").read_text()
    cfg = cfg.replace("  j_wrist:             {signal: wrist, zero_offset_deg: 10}\n", "")
    path = tmp_path / "fewer.yaml"
    path.write_text(cfg)
    run_build("coupled", tmp_path, config=path)
    assert sorted(p.name for p in folder.glob("*.glb")) == ["model.glb", "model_0.glb", "model_1.glb"]


@pytest.mark.parametrize("entry", INVALID, ids=[f["name"] for f in INVALID])
def test_invalid_fixtures_fail_and_name_the_problem(entry, tmp_path):
    with pytest.raises(CadError) as err:
        run_build(entry["name"], tmp_path)
    assert entry["expect_error_mentions"] in str(err.value)
    assert not any(tmp_path.rglob("*.glb")), "a failed build must not write files"


def test_frozen_joint_is_merged_into_base(built):
    result = built["frozen"]
    assert "flap" in result.model.base_links
    assert any("Revolute 7" in w for w in result.warnings)


def test_coupled_chain_parents(built):
    comps = built["coupled"].model.components
    assert [(c.joint.name, c.parent) for c in comps] == [
        ("j_elevator_stage1", None),
        ("j_elevator_carriage", 0),
        ("j_wrist", 1),
    ]
