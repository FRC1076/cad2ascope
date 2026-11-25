"""The command line: inspect, init, build, and exit codes (errors 1, warnings 0)."""

from __future__ import annotations

import yaml

from cad2ascope.cli import main
from cad2ascope.config import load_config
from test_fixtures import FIXTURES


def test_inspect_prints_tree(capsys):
    assert main(["inspect", str(FIXTURES / "coupled.zip")]) == 0
    out = capsys.readouterr().out
    assert "j_elevator_carriage" in out
    assert "relation: 1 x j_elevator_stage1" in out
    assert "[robot origin]" in out


def test_inspect_url_explains_phase_4(capsys):
    assert main(["inspect", "https://aaps.onshape.com/documents/x"]) == 1
    assert "pass the downloaded zip" in capsys.readouterr().err


def test_init_then_build(tmp_path, capsys):
    cfg = tmp_path / "cad" / "advantagescope.yaml"
    assert main(["init", str(FIXTURES / "coupled.zip"), "-o", str(cfg), "--name", "1076 Test"]) == 0
    c = load_config(cfg)
    assert c.robot.folder == "Robot_1076_Test"
    assert list(c.joints) == ["j_elevator_stage1", "j_elevator_carriage", "j_wrist"]
    # the carriage follows stage 1 through the Onshape relation, so it shares its signal
    assert c.joints["j_elevator_carriage"].signal == c.joints["j_elevator_stage1"].signal == "elevator_stage1"
    assert c.signals == {"elevator_stage1": "m", "wrist": "rad"}
    assert main(["build", str(FIXTURES / "coupled.zip"), "-c", str(cfg), "-o", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "Robot_1076_Test" / "model_2.glb").is_file()


def test_init_lists_frozen_mates_as_comments(tmp_path):
    cfg = tmp_path / "a.yaml"
    assert main(["init", str(FIXTURES / "frozen.zip"), "-o", str(cfg)]) == 0
    text = cfg.read_text()
    assert "#   Revolute 7 (Revolute)" in text
    assert list(yaml.safe_load(text)["joints"]) == ["j_intake"]


def test_init_refuses_to_overwrite(tmp_path, capsys):
    cfg = tmp_path / "a.yaml"
    cfg.write_text("keep me")
    assert main(["init", str(FIXTURES / "coupled.zip"), "-o", str(cfg)]) == 1
    assert cfg.read_text() == "keep me"
    assert "--force" in capsys.readouterr().err


def test_build_warnings_exit_zero(tmp_path, capsys):
    rc = main(
        [
            "build",
            str(FIXTURES / "frozen.zip"),
            "-c",
            str(FIXTURES / "frozen" / "advantagescope.yaml"),
            "-o",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert "Warning: Mate 'Revolute 7'" in capsys.readouterr().err


def test_build_error_exits_one(tmp_path, capsys):
    rc = main(
        [
            "build",
            str(FIXTURES / "missing_origin.zip"),
            "-c",
            str(FIXTURES / "missing_origin" / "advantagescope.yaml"),
            "-o",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert capsys.readouterr().err.startswith("Error: The robot origin frame 'ascope_origin'")
