"""Team config loading, export reading, and the student-facing error messages (PLAN §6.6)."""

from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import pytest
import yaml

from cad2ascope.build import build
from cad2ascope.cameras import ascope_fov, read_calibration
from cad2ascope.config import load_config, load_schema, parse_config
from cad2ascope.errors import CadError
from cad2ascope.export import load_export
from cad2ascope.urdf import parse_urdf
from test_fixtures import FIXTURES

ROOT = Path(__file__).resolve().parents[1]


def cfg(**overrides) -> dict:
    data = yaml.safe_load((FIXTURES / "coupled" / "advantagescope.yaml").read_text())
    for key, value in overrides.items():
        data[key] = value
    return data


def build_with(tmp_path: Path, data: dict, fixture: str = "coupled"):
    path = tmp_path / "advantagescope.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return build(FIXTURES / f"{fixture}.zip", path, tmp_path / "out", repo_root=tmp_path)


# ------------------------------------------------------------------------------------------------- config


def test_packaged_schema_matches_spec():
    assert load_schema() == json.loads((ROOT / "spec" / "advantagescope.schema.json").read_text())


def test_example_config_loads():
    c = load_config(ROOT / "spec" / "advantagescope.example.yaml")
    assert c.joints["j_wrist"].direction == -1
    assert c.cameras.fallback_resolution == (1280, 800)
    assert c.codegen.java_package == "frc.robot.generated"


@pytest.mark.parametrize(
    ("edit", "needle"),
    [
        (lambda d: d["joints"]["j_wrist"].update(direction=2), "Use one of: 1, -1"),
        (lambda d: d["robot"].update(folder="MyRobot"), "must start with Robot_"),
        (lambda d: d["joints"].update(wrist_pivot={"signal": "wrist"}), "must start with j_"),
        (lambda d: d["joints"]["j_wrist"].update(ratio=0), "ratio cannot be 0"),
        (lambda d: d["joints"]["j_wrist"].update(speed=3), "'speed' was unexpected"),
        (lambda d: d["robot"].pop("name"), "robot: 'name' is missing"),
        (lambda d: d["joints"]["j_wrist"].update(signal="wirst"), "signal 'wirst' is not listed under signals"),
    ],
)
def test_config_errors_are_readable(edit, needle):
    data = cfg()
    edit(data)
    with pytest.raises(CadError) as err:
        parse_config(data)
    assert needle in str(err.value)


def test_bad_yaml_points_at_line(tmp_path):
    p = tmp_path / "advantagescope.yaml"
    p.write_text("robot:\n  name: x\n\tfolder: Robot_x\n")
    with pytest.raises(CadError, match="line 3"):
        load_config(p)


def test_missing_config_says_run_init(tmp_path):
    with pytest.raises(CadError, match="cad2ascope init"):
        load_config(tmp_path / "nope.yaml")


# ------------------------------------------------------------------------------------------------- joints vs export


def test_listed_joint_missing_suggests_close_name(tmp_path):
    data = cfg()
    data["joints"]["j_wirst"] = data["joints"].pop("j_wrist")
    with pytest.raises(CadError, match="Did you mean 'j_wrist'"):
        build_with(tmp_path, data)


def test_fastened_mate_listed(tmp_path):
    data = cfg()
    data["joints"]["j_test"] = {"signal": "wrist"}
    urdf = (FIXTURES / "coupled" / "robot.urdf").read_text()
    urdf = urdf.replace('name="j_wrist" type="revolute"', 'name="j_test" type="fixed"')
    folder = tmp_path / "export"
    folder.mkdir()
    (folder / "robot.urdf").write_text(urdf)
    (folder / "meshes").symlink_to(FIXTURES / "coupled" / "meshes")
    data["joints"].pop("j_wrist")
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(CadError, match="j_test is a Fastened mate. Change it to Revolute or Slider"):
        build(folder, path, tmp_path / "out", repo_root=tmp_path)


def test_units_must_match_joint_type(tmp_path):
    data = cfg()
    data["signals"]["wrist"] = {"units": "m"}
    with pytest.raises(CadError, match="j_wrist turns, so its signal must be in rad"):
        build_with(tmp_path, data)


def test_zero_offset_kind_must_match(tmp_path):
    data = cfg()
    data["joints"]["j_elevator_stage1"]["zero_offset_deg"] = 5
    with pytest.raises(CadError, match="j_elevator_stage1 is a Slider, so use zero_offset_m"):
        build_with(tmp_path, data)


def test_origin_on_moving_part_is_rejected(tmp_path):
    data = cfg()
    data["robot"]["origin_frame"] = "carriage"
    with pytest.raises(CadError, match="on a moving mechanism"):
        build_with(tmp_path, data)


def test_mimic_ratio_mismatch_warns(tmp_path):
    data = cfg()
    data["joints"]["j_elevator_carriage"]["ratio"] = 0.25
    result = build_with(tmp_path, data)
    assert any("relation says it moves 1 times j_elevator_stage1" in w for w in result.warnings)


def test_consistent_mimic_does_not_warn(tmp_path):
    result = build_with(tmp_path, cfg())
    assert result.warnings == []


# ------------------------------------------------------------------------------------------------- URDF and export

MINI = """<robot name="r">
  <link name="a"/><link name="b"/><link name="c"/>
  <joint name="j1" type="revolute"><parent link="a"/><child link="b"/><axis xyz="0 0 2"/></joint>
  {extra}
</robot>"""


def test_axis_is_read_and_normalized():
    robot = parse_urdf(MINI.format(extra='<joint name="f" type="fixed"><parent link="a"/><child link="c"/></joint>'))
    assert list(robot.joints["j1"].axis) == [0.0, 0.0, 1.0]


def test_two_separate_pieces_are_named():
    with pytest.raises(CadError, match="2 separate pieces that are not mated to each other: 'a', 'c'"):
        parse_urdf(MINI.format(extra=""))


def test_unknown_link_in_joint():
    with pytest.raises(CadError, match="connects to a part named 'zz'"):
        parse_urdf(MINI.format(extra='<joint name="f" type="fixed"><parent link="a"/><child link="zz"/></joint>'))


def test_duplicate_mate_names():
    extra = '<joint name="j1" type="fixed"><parent link="a"/><child link="c"/></joint>'
    with pytest.raises(CadError, match="Two mates are both named 'j1'"):
        parse_urdf(MINI.format(extra=extra))


def test_walk_is_depth_first_by_joint_name():
    text = """<robot name="r">
      <link name="root"/><link name="a"/><link name="a1"/><link name="b"/>
      <joint name="z_b" type="fixed"><parent link="root"/><child link="b"/></joint>
      <joint name="m_a" type="fixed"><parent link="root"/><child link="a"/></joint>
      <joint name="n_a1" type="fixed"><parent link="a"/><child link="a1"/></joint>
    </robot>"""
    assert [j.name for j in parse_urdf(text).walk()] == ["m_a", "n_a1", "z_b"]


def _zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


def test_zip_with_subfolder_and_package_paths(tmp_path):
    urdf = (
        (FIXTURES / "single_revolute" / "robot.urdf")
        .read_text()
        .replace('filename="meshes/', 'filename="package://bot/meshes/')
    )
    files = {"bot/robot.urdf": urdf.encode()}
    for p in (FIXTURES / "single_revolute" / "meshes").iterdir():
        files[f"bot/meshes/{p.name}"] = p.read_bytes()
    z = _zip(tmp_path / "export.zip", files)
    with load_export(z) as export:
        assert export.resolve_mesh("package://bot/meshes/arm.glb").name == "arm.glb"
    result = build(z, FIXTURES / "single_revolute" / "advantagescope.yaml", tmp_path / "out", repo_root=tmp_path)
    assert (result.folder / "model_0.glb").stat().st_size > 0


def test_zip_slip_is_refused(tmp_path):
    z = _zip(tmp_path / "evil.zip", {"../outside.urdf": b"<robot/>"})
    with pytest.raises(CadError, match="unsafe path"):
        load_export(z)
    assert not (tmp_path / "outside.urdf").exists()


def test_zip_without_urdf(tmp_path):
    with pytest.raises(CadError, match="export the assembly as URDF"):
        load_export(_zip(tmp_path / "x.zip", {"a.step": b"x"}))


def test_missing_mesh_file(tmp_path):
    urdf = (FIXTURES / "single_revolute" / "robot.urdf").read_text()
    z = _zip(tmp_path / "x.zip", {"robot.urdf": urdf.encode()})
    with pytest.raises(CadError, match="missing the mesh file 'meshes/"):
        build(z, FIXTURES / "single_revolute" / "advantagescope.yaml", tmp_path / "out", repo_root=tmp_path)


# ------------------------------------------------------------------------------------------------- cameras


def test_fov_for_2026_front_left_values():
    # From FRC1076/2026-Competition assets/photonvision/FRONT_LEFT Calibration.json: 1280 x 800, fy = 922.96.
    fov = ascope_fov(1280, 800, 922.9612905749468)
    assert fov == pytest.approx(1.6 * math.degrees(2 * math.atan(400 / 922.9612905749468)))
    assert fov == pytest.approx(74.99, abs=0.02)


def test_calibration_file_is_used(tmp_path):
    cal_dir = tmp_path / "assets" / "photonvision"
    cal_dir.mkdir(parents=True)
    calibration = {
        "resolution": {"width": 1280.0, "height": 800.0},
        "cameraIntrinsics": {"rows": 3, "cols": 3, "type": 6, "data": [922.66, 0, 637.0, 0, 922.96, 406.0, 0, 0, 1]},
        "distCoeffs": {"rows": 1, "cols": 8, "type": 6, "data": [0] * 8},
    }
    (cal_dir / "FRONT_LEFT Calibration.json").write_text(json.dumps(calibration))
    assert read_calibration(cal_dir / "FRONT_LEFT Calibration.json") == (1280, 800, 922.66, 922.96)
    data = yaml.safe_load((FIXTURES / "nested_chain" / "advantagescope.yaml").read_text())
    data["cameras"]["photonvision_calibrations"] = "assets/photonvision"
    result = build_with(tmp_path, data, fixture="nested_chain")
    cams = {c.name: c for c in result.cameras}
    assert cams["FRONT_LEFT"].source == "calibration: FRONT_LEFT Calibration.json"
    assert cams["FRONT_LEFT"].fov_deg == pytest.approx(ascope_fov(1280, 800, 922.96))
    assert cams["TURRET"].source == "fallback"
    assert any("No calibration file for camera TURRET" in w for w in result.warnings)


def test_fallback_fov_means_true_horizontal(tmp_path):
    result = build_with(
        tmp_path, yaml.safe_load((FIXTURES / "nested_chain" / "advantagescope.yaml").read_text()), "nested_chain"
    )
    cam = result.cameras[0]
    assert cam.hfov_deg == pytest.approx(70.0)
    assert cam.fov_deg > 70.0  # written wider, because AdvantageScope divides it by the aspect ratio


# ------------------------------------------------------------------------------------------------- Onshape export shape
# Mirrors what the real 2025 and 2026 manual exports contain (docs/phase0-findings.md, section A).

ONSHAPE_LIKE = """<robot name="pkg_bot">
  <link name="root"><visual><geometry><mesh filename="package://pkg_bot/meshes/a.gltf"/></geometry></visual></link>
  <link name="drivetrain"><visual><geometry><mesh filename="package://pkg_bot/meshes/a.gltf"/></geometry></visual></link>
  <link name="ascope_origin"/>
  <link name="turret_plate"><visual><geometry><mesh filename="package://pkg_bot/meshes/a.gltf"/></geometry></visual></link>
  <link name="hood"><visual><geometry><mesh filename="package://pkg_bot/meshes/a.gltf"/></geometry></visual></link>
  <link name="loose_roller"><visual><geometry><mesh filename="package://pkg_bot/meshes/a.gltf"/></geometry></visual></link>
  <link name="j_turret_1"/><link name="j_turret"/>
  <link name="turret"><visual><geometry><mesh filename="package://pkg_bot/meshes/a.gltf"/></geometry></visual></link>
  <link name="bar_loop_closure"/>
  <joint name="fastened_1" type="fixed"><parent link="root"/><child link="drivetrain"/></joint>
  <joint name="ascope_origin" type="fixed"><parent link="drivetrain"/><child link="ascope_origin"/></joint>
  <joint name="fixed_node_to_root_joint" type="fixed"><parent link="root"/><child link="turret_plate"/></joint>
  <joint name="j_hood" type="revolute"><parent link="turret_plate"/><child link="hood"/><axis xyz="0 1 0"/>
    <limit lower="-0.3" upper="0.1" effort="1" velocity="1"/></joint>
  <joint name="hanging_node_to_root_joint" type="fixed"><parent link="root"/><child link="loose_roller"/></joint>
  <joint name="j_turret" type="prismatic"><parent link="drivetrain"/><child link="j_turret_1"/><axis xyz="1 0 0"/>
    <limit lower="-10000" upper="10000" effort="1" velocity="1"/></joint>
  <joint name="j_turret_1" type="prismatic"><parent link="j_turret_1"/><child link="j_turret"/><axis xyz="0 1 0"/>
    <limit lower="-10000" upper="10000" effort="1" velocity="1"/></joint>
  <joint name="j_turret_2" type="continuous"><parent link="j_turret"/><child link="turret"/><axis xyz="0 0 1"/></joint>
  <joint name="bar_loop_closure" type="continuous"><parent link="turret"/><child link="bar_loop_closure"/></joint>
</robot>"""


def _onshape_config(joints: dict) -> object:
    return parse_config(
        {
            "robot": {"name": "t", "folder": "Robot_t", "origin_frame": "ascope_origin"},
            "signals": {"hood": {"units": "rad"}, "turret": {"units": "rad"}},
            "joints": joints,
        }
    )


def test_onshape_root_attachments_and_loop_cuts_are_reported():
    from cad2ascope.grouping import build_model

    model = build_model(parse_urdf(ONSHAPE_LIKE), _onshape_config({"j_hood": {"signal": "hood"}}))
    text = "\n".join(model.warnings)
    assert "'turret_plate' is grounded (Fixed) in Onshape" in text
    assert "1 part(s) are not mated to anything ('loose_roller')" in text
    assert "Onshape cut 1 closed loop(s)" in text
    assert model.components[0].parent is None  # the hood hangs off the grounded plate, i.e. the base


def test_grounded_drivetrain_is_not_reported():
    from cad2ascope.grouping import build_model

    # Swap roles: the drivetrain is the grounded instance and the turret plate is fastened to the root.
    urdf = ONSHAPE_LIKE.replace('"fastened_1"', '"TMP"').replace('"fixed_node_to_root_joint"', '"fastened_1"')
    urdf = urdf.replace('"TMP"', '"fixed_node_to_root_joint"')
    model = build_model(parse_urdf(urdf), _onshape_config({"j_hood": {"signal": "hood"}}))
    assert not any("grounded" in w for w in model.warnings)


def test_planar_mate_chain_cannot_be_listed():
    from cad2ascope.grouping import build_model

    for name in ("j_turret", "j_turret_2"):
        with pytest.raises(CadError, match=f"{name} comes from a mate that Onshape exports as several joints"):
            build_model(parse_urdf(ONSHAPE_LIKE), _onshape_config({name: {"signal": "turret"}}))


def test_many_frozen_joints_are_summarized():
    from cad2ascope.grouping import build_model

    extra = "".join(
        f'<link name="w{i}"/><joint name="revolute_{i}" type="continuous"><parent link="drivetrain"/><child link="w{i}"/></joint>'
        for i in range(8)
    )
    model = build_model(parse_urdf(ONSHAPE_LIKE.replace("</robot>", extra + "</robot>")), _onshape_config({}))
    summary = [w for w in model.warnings if "joints can move in Onshape but are frozen" in w]
    assert len(summary) == 1 and summary[0].startswith("9 joints can move")  # 8 rollers + the loop cut
    # unlisted j_ joints are still named one by one, because they are probably a forgotten config entry
    assert any(w.startswith("Mate j_hood can move in Onshape but is not listed") for w in model.warnings)


def test_ros_package_layout_resolves(tmp_path):
    pkg = tmp_path / "export" / "pkg_bot"
    (pkg / "urdf").mkdir(parents=True)
    (pkg / "meshes").mkdir()
    (pkg / "urdf" / "pkg_bot.urdf").write_text(ONSHAPE_LIKE)
    (pkg / "meshes" / "a.gltf").write_text("{}")
    (tmp_path / "export" / "decoy").mkdir()
    (tmp_path / "export" / "decoy" / "a.gltf").write_text("{}")  # same name elsewhere: must not be picked
    with load_export(tmp_path / "export") as export:
        assert export.resolve_mesh("package://pkg_bot/meshes/a.gltf") == (pkg / "meshes" / "a.gltf").resolve()
