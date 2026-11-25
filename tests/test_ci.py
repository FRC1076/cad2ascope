"""Phase 5: `cad2ascope ci`, `cad2ascope render`, and the robot-repo workflow template."""

from __future__ import annotations

import json
import re
import shutil
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
import yaml

from cad2ascope.cli import build_parser, main
from cad2ascope.codegen import _joints, _signals, fk
from cad2ascope.errors import Warnings
from cad2ascope.render import Mesh, component_poses, png_bytes, render, render_folder
from test_fixtures import FIXTURES
from test_onshape import ACCESS, SECRET, URL, VID, FakeOnshape, _zip_of, client

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "templates" / "robot-repo" / ".github" / "workflows" / "update-robot-model.yml"


def robot_repo(tmp_path: Path, fixture: str = "nested_chain", url: str | None = None) -> Path:
    repo = tmp_path / "robot"
    (repo / "cad" / "drops").mkdir(parents=True)
    text = (FIXTURES / fixture / "advantagescope.yaml").read_text()
    if url:
        text = text.replace("  origin_frame: ascope_origin\n", f"  origin_frame: ascope_origin\n  onshape_url: {url}\n")
    (repo / "cad" / "advantagescope.yaml").write_text(text)
    return repo


def outputs(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


# ----------------------------------------------------------------------------------------------- ci


def test_drop_route(tmp_path, monkeypatch):
    repo = robot_repo(tmp_path)
    shutil.copy(FIXTURES / "nested_chain.zip", repo / "cad" / "drops" / "week4.zip")
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    rc = main(["ci", "--repo-root", str(repo), "--link-base", "https://github.com/team/robot/blob/b/cad/previews"])
    assert rc == 0
    out = outputs(gh_out)
    assert out["mode"] == "drop" and out["breaking"] == "false"
    assert out["title"] == "Update robot model from dropped export week4.zip"
    assert out["zip_removed"] == "cad/drops/week4.zip" and not (repo / "cad/drops/week4.zip").exists()
    assert (repo / "assets/advantagescope/Robot_nested_chain/model_1.glb").is_file()
    assert (repo / "src/main/java/frc/robot/generated/RobotModel.java").is_file()
    assert (repo / "cad/previews/preview_zero.png").is_file()
    report = (repo / out["report"]).read_text()
    assert "![All mechanisms at zero](https://github.com/team/robot/blob/b/cad/previews/preview_zero.png)" in report
    assert "Zero-pose check (PLAN §10.3 item 2): the model with zero poses published looks identical" in report


def test_two_drops_are_refused(tmp_path, capsys):
    repo = robot_repo(tmp_path)
    for name in ("a.zip", "b.zip"):
        shutil.copy(FIXTURES / "nested_chain.zip", repo / "cad" / "drops" / name)
    assert main(["ci", "--repo-root", str(repo), "--no-render"]) == 1
    assert "Drop one Onshape export at a time" in capsys.readouterr().err
    assert (repo / "cad/drops/a.zip").exists() and (repo / "cad/drops/b.zip").exists()


def test_no_url_and_no_drop_explains_both_routes(tmp_path, capsys):
    repo = robot_repo(tmp_path)
    assert main(["ci", "--repo-root", str(repo), "--no-render"]) == 1
    assert "drop a URDF zip exported from Onshape into cad/drops/" in capsys.readouterr().err


def test_api_route_and_breaking_change(tmp_path, monkeypatch):
    import cad2ascope.onshape as onshape_module

    server = FakeOnshape(zip_bytes=_zip_of(FIXTURES / "coupled"))
    monkeypatch.setattr(onshape_module, "Client", lambda *a, **k: client(server))
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", ACCESS)
    monkeypatch.setenv("ONSHAPE_SECRET_KEY", SECRET)
    repo = robot_repo(tmp_path, "coupled", URL)
    cfg = repo / "cad" / "advantagescope.yaml"
    full = cfg.read_text()
    data = yaml.safe_load(full)
    del data["joints"]["j_wrist"], data["signals"]["wrist"]
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    cache = tmp_path / "cache"
    gh_out = tmp_path / "gh1"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    assert main(["ci", "--repo-root", str(repo), "--no-render", "--cache-dir", str(cache)]) == 0
    first = outputs(gh_out)
    assert first["mode"] == "version" and first["title"] == 'Update robot model from Onshape version "Week 4"'
    assert first["breaking"] == "false"
    manifest = json.loads((repo / "assets/advantagescope/Robot_coupled/manifest.json").read_text())
    assert manifest["source"]["onshape"]["version_id"] == VID

    cfg.write_text(full)  # the wrist joint comes back: a new signal, so robot code must change
    gh_out2 = tmp_path / "gh2"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out2))
    assert main(["ci", "--repo-root", str(repo), "--no-render", "--cache-dir", str(cache)]) == 0
    second = outputs(gh_out2)
    assert second["breaking"] == "true"
    assert (repo / second["report"]).read_text().startswith("> **Robot code changes needed:** signals added `wrist`")


def test_version_override_from_the_workflow(tmp_path, monkeypatch):
    import cad2ascope.onshape as onshape_module

    server = FakeOnshape(zip_bytes=_zip_of(FIXTURES / "single_revolute"))
    monkeypatch.setattr(onshape_module, "Client", lambda *a, **k: client(server))
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", ACCESS)
    monkeypatch.setenv("ONSHAPE_SECRET_KEY", SECRET)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh"))
    repo = robot_repo(tmp_path, "single_revolute", URL)
    args = ["ci", "--repo-root", str(repo), "--no-render", "--version", "Week 3", "--cache-dir", str(tmp_path / "c")]
    assert main(args) == 0
    assert outputs(tmp_path / "gh")["title"] == 'Update robot model from Onshape version "Week 3"'


# ----------------------------------------------------------------------------------------------- render


def test_render_draws_a_box_in_the_right_color():
    box = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (0, 0.2)], dtype=float)
    faces = np.array(
        [
            [0, 1, 3],
            [0, 3, 2],
            [4, 6, 7],
            [4, 7, 5],
            [0, 4, 5],
            [0, 5, 1],
            [2, 3, 7],
            [2, 7, 6],
            [0, 2, 6],
            [0, 6, 4],
            [1, 5, 7],
            [1, 7, 3],
        ]
    )
    img = render([Mesh(box, faces, np.array([1.0, 0.0, 0.0, 1.0]))], 200, 150)
    center = img[75, 100].astype(int)
    assert center[0] > 80 and center[1] == 0 and center[2] == 0  # red, lit
    assert tuple(img[2, 2]) == (233, 231, 238)  # background corner


def test_png_is_valid():
    img = np.zeros((3, 4, 3), dtype=np.uint8)
    img[1, 2] = (10, 20, 30)
    data = png_bytes(img)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (4, 3)
    idat = data[data.index(b"IDAT") + 4 : data.index(b"IEND") - 8]
    raw = zlib.decompress(idat)
    assert raw[1 * (1 + 12) + 1 + 2 * 3 : 1 * (1 + 12) + 1 + 2 * 3 + 3] == bytes([10, 20, 30])


@pytest.mark.parametrize("name", ["nested_chain", "coupled"])
def test_render_kinematics_matches_codegen(name, tmp_path):
    from cad2ascope.build import build

    result = build(FIXTURES / f"{name}.zip", FIXTURES / name / "advantagescope.yaml", tmp_path, repo_root=FIXTURES)
    manifest = json.loads((result.folder / "manifest.json").read_text())
    signals = _signals(result.model, Warnings())
    joints = _joints(result.model, {s.name: i for i, s in enumerate(signals)})
    rng = np.random.default_rng(3)
    for _ in range(4):
        values = [rng.uniform(s.min, s.max) for s in signals]
        for a, b in zip(component_poses(manifest, values), fk(joints, values), strict=True):
            np.testing.assert_allclose(a, b, atol=1e-6)  # manifest stores T0 rounded to 1e-9


def test_zero_check_catches_a_wrong_zeroed_transform(tmp_path):
    from cad2ascope.build import build

    result = build(
        FIXTURES / "single_revolute.zip",
        FIXTURES / "single_revolute" / "advantagescope.yaml",
        tmp_path,
        repo_root=FIXTURES,
    )
    assert render_folder(result.folder, tmp_path / "ok", 160, 120).zero_check_pixels == 0
    cfg_path = result.folder / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["components"][0]["zeroedPosition"][2] += 0.05  # 5 cm off, as if the export pose were wrong
    cfg_path.write_text(json.dumps(cfg))
    assert render_folder(result.folder, tmp_path / "bad", 160, 120).zero_check_pixels > 0


# ----------------------------------------------------------------------------------------------- workflow template


def test_workflow_actions_are_pinned_to_commits():
    wf = yaml.safe_load(WORKFLOW.read_text())
    uses = [s["uses"] for s in wf["jobs"]["update"]["steps"] if "uses" in s]
    assert uses and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses), uses


def test_workflow_never_pastes_inputs_into_scripts():
    wf = yaml.safe_load(WORKFLOW.read_text())
    for step in wf["jobs"]["update"]["steps"]:
        assert "${{" not in step.get("run", ""), step.get("name")


def test_workflow_cad2ascope_arguments_parse():
    text = WORKFLOW.read_text()
    assert "args=(ci --link-base" in text and "--version" in text and "--workspace" in text
    args = build_parser().parse_args(["ci", "--link-base", "x", "--version", "Week 4", "--workspace"])
    assert args.onshape_version == "Week 4" and args.workspace and args.link_base == "x"
    wf = yaml.safe_load(WORKFLOW.read_text())
    triggers = wf[True] if True in wf else wf["on"]  # PyYAML reads the key `on` as True
    assert triggers["push"]["paths"] == ["cad/drops/*.zip"]
