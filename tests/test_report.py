"""report.md: breaking-change line, camera movement since the last build, and the hand-typed baseline comparison."""

from __future__ import annotations

import math
import shutil

import pytest
import yaml

from cad2ascope.build import build
from cad2ascope.errors import CadError
from cad2ascope.report import load_baseline
from test_fixtures import FIXTURES


def _export_copy(tmp_path, name="nested_chain"):
    d = tmp_path / "export"
    shutil.copytree(FIXTURES / name, d, ignore=shutil.ignore_patterns("advantagescope.yaml", "expected*"))
    return d


def _config(tmp_path, name="nested_chain", **changes):
    data = yaml.safe_load((FIXTURES / name / "advantagescope.yaml").read_text())
    for key, value in changes.items():
        section, field = key.split("__")
        data.setdefault(section, {})[field] = value
    p = tmp_path / "advantagescope.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return p, data


def test_first_build_has_no_comparison(tmp_path):
    cfg, _ = _config(tmp_path)
    result = build(_export_copy(tmp_path), cfg, tmp_path / "out", repo_root=tmp_path)
    report = (result.folder / "report.md").read_text()
    assert report.startswith("# Robot model update: nested_chain")
    assert "First build, so there is nothing to compare cameras against yet." in report
    assert "| model_1.glb | `j_hood` | revolute | hood | model_0 |" in report


def test_camera_moved_since_last_build_is_reported(tmp_path):
    export = _export_copy(tmp_path)
    cfg, _ = _config(tmp_path)
    build(export, cfg, tmp_path / "out", repo_root=tmp_path)
    urdf = export / "robot.urdf"
    text = urdf.read_text()
    # cam_FRONT_LEFT sits at x = 0.236 on the drivetrain; move it 5 mm forward.
    assert 'xyz="0.236 0.328 0.233"' in text
    urdf.write_text(text.replace('xyz="0.236 0.328 0.233"', 'xyz="0.241 0.328 0.233"'))
    result = build(export, cfg, tmp_path / "out", repo_root=tmp_path)
    report = (result.folder / "report.md").read_text()
    assert "| FRONT_LEFT | 5.0 mm | 0.00° | check with the vision lead before merging |" in report
    assert "| TURRET | 0.0 mm | 0.00° |  |" in report
    assert "| TURRET_PIVOT | 0.0 mm | 0.00° |  |" in report


def test_added_signal_is_the_first_line(tmp_path):
    export = _export_copy(tmp_path, "coupled")
    cfg, data = _config(tmp_path, "coupled")
    del data["joints"]["j_wrist"], data["signals"]["wrist"]
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    build(export, cfg, tmp_path / "out", repo_root=tmp_path)
    cfg, _ = _config(tmp_path, "coupled")
    result = build(export, cfg, tmp_path / "out", repo_root=tmp_path)
    first = (result.folder / "report.md").read_text().splitlines()[0]
    assert first.startswith("> **Robot code changes needed:** signals added `wrist`.")


def test_baseline_comparison(tmp_path):
    export = _export_copy(tmp_path)
    # FRONT_LEFT in the fixture: robot-frame transform from expected.json, typed back in inches and degrees.
    import json

    import numpy as np
    from scipy.spatial.transform import Rotation

    t = np.array(json.loads((FIXTURES / "nested_chain" / "expected.json").read_text())["cameras"]["FRONT_LEFT"])
    roll, pitch, yaw = (float(v) for v in Rotation.from_matrix(t[:3, :3]).as_euler("xyz", degrees=True))
    x, y, z = (float(v) for v in t[:3, 3] / 0.0254)
    baseline = {
        "front_left": {
            "x": x + 0.1,
            "y": y,
            "z": z,
            "roll": roll,
            "pitch": pitch + 0.5,
            "yaw": yaw,
        },  # within tolerance
        "TURRET": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},  # far off
        "REAR_LEFT": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},  # no connector in CAD
    }
    (tmp_path / "baseline.yaml").write_text(yaml.safe_dump(baseline))
    cfg, _ = _config(tmp_path, cameras__baseline="baseline.yaml")
    report = (build(export, cfg, tmp_path / "out", repo_root=tmp_path).folder / "report.md").read_text()
    assert "| FRONT_LEFT | 2.5 mm | 0.50° | pass |" in report
    assert "| TURRET |" in report and "**check** |" in report
    assert "| REAR_LEFT | | | no `cam_` connector in CAD |" in report


def test_baseline_matches_wpilib_rotation_order(tmp_path):
    p = tmp_path / "b.yaml"
    p.write_text("CAM: {x: 10, y: 0, z: 0, roll: 0, pitch: 20, yaw: 50}\n")
    t = load_baseline(p)["CAM"]
    assert t[0, 3] == pytest.approx(0.254)
    # Rotation3d(0, 20°, 50°) looks along yaw 50° and pitches down 20° (WPILib: +pitch tilts +X toward -Z)
    view = t[:3, :3] @ [1, 0, 0]
    assert view[2] == pytest.approx(-math.sin(math.radians(20)))
    assert math.degrees(math.atan2(view[1], view[0])) == pytest.approx(50)


def test_bad_baseline_explains_the_format(tmp_path):
    p = tmp_path / "b.yaml"
    p.write_text("CAM: {x: 1}\n")
    with pytest.raises(CadError, match="needs x, y, z in inches"):
        load_baseline(p)


def test_missing_baseline_file_is_an_error(tmp_path):
    cfg, _ = _config(tmp_path, cameras__baseline="nope.yaml")
    with pytest.raises(CadError, match="cameras.baseline points at"):
        build(_export_copy(tmp_path), cfg, tmp_path / "out", repo_root=tmp_path)
