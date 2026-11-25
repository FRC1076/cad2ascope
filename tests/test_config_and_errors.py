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
