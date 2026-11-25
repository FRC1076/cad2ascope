"""`cad2ascope ci`: everything the robot repo's "Update robot model" workflow does, in one tested command (PLAN §8.1).

1. Source: exactly one zip in cad/drops/ (manual export, no key needed), else the Onshape API (latest Version,
   a named Version, or the workspace as a preview).
2. Build the AdvantageScope folder, generate RobotModel.java and its test, render preview PNGs.
3. Write the pull request body (report.md plus previews) and delete the processed zip, so drops do not pile up.
4. Tell the workflow what happened through $GITHUB_OUTPUT: mode, title, report path, and whether robot code
   will need changes before it compiles.

The workflow then runs ./gradlew test and commits or opens a pull request. Nothing merges automatically.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cad2ascope.build import build
from cad2ascope.codegen import generate, source_description, write
from cad2ascope.config import load_config
from cad2ascope.errors import CadError
from cad2ascope.onshape import fetch
from cad2ascope.render import preview_markdown, render_folder

BREAKING_MARK = "> **Robot code changes needed:**"


@dataclass
class CiResult:
    mode: str  # "drop", "version" or "workspace"
    title: str
    report: Path
    breaking: bool
    zip_removed: Path | None
    warnings: list[str]


def find_drop(drops: Path) -> Path | None:
    zips = sorted(p for p in drops.glob("*.zip") if p.is_file()) if drops.is_dir() else []
    if len(zips) > 1:
        names = ", ".join(p.name for p in zips)
        raise CadError(
            f"There are {len(zips)} zips in {drops} ({names}). Drop one Onshape export at a time: delete the extra ones "
            "on your branch and push again."
        )
    return zips[0] if zips else None


def run_ci(
    config_path: str | Path,
    repo_root: str | Path = ".",
    drops: str = "cad/drops",
    out: str = "assets/advantagescope",
    previews: str = "cad/previews",
    report: str = "build/cad2ascope/report.md",
    version: str | None = None,
    workspace: bool = False,
    link_base: str = "",
    render: bool = True,
    cache_dir: Path | None = None,
    log=lambda msg: None,
) -> CiResult:
    root = Path(repo_root).resolve()
    cfg = load_config(root / config_path)
    drop = find_drop(root / drops)
    onshape = None
    if drop is not None:
        mode, export = "drop", drop
        title = f"Update robot model from dropped export {drop.name}"
        log(f"Using the dropped export {drop.relative_to(root)} (no Onshape API calls).")
    else:
        if not cfg.robot.onshape_url:
            raise CadError(
                f"{config_path} has no robot.onshape_url and there is no zip in {drops}. Either paste the assembly URL "
                f"into the config, or drop a URDF zip exported from Onshape into {drops}/ on a branch."
            )
        wanted = version or cfg.robot.version
        got = fetch(
            cfg.robot.onshape_url, wanted, cfg.robot.configuration, workspace=workspace, cache_dir=cache_dir, log=log
        )
        export, onshape = got.zip_path, got.source
        if workspace:
            mode, title = "workspace", "Preview robot model from the Onshape workspace"
        else:
            mode, title = "version", f'Update robot model from Onshape version "{got.source.get("version_name")}"'

    result = build(export, root / config_path, root / out, root, onshape_source=onshape)
    java, test = generate(
        result.model,
        result.cameras,
        result.frames,
        source_description(onshape, result.source_name, result.source_sha256),
    )
    write(java, test, result.model.config, root)

    body = (result.folder / "report.md").read_text()
    if render:
        rendered = render_folder(result.folder, root / previews)
        body = body.rstrip() + "\n\n" + preview_markdown(rendered, link_base)
        if rendered.zero_check_pixels:
            result.model.warnings.add(
                f"Zero-pose check: {rendered.zero_check_pixels} pixels differ between zero poses and no poses."
            )
    report_path = root / report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(body)

    removed = None
    if drop is not None:
        drop.unlink()
        removed = drop
    return CiResult(mode, title, report_path, body.startswith(BREAKING_MARK), removed, list(result.model.warnings))


def write_github_output(result: CiResult, repo_root: Path, path: str | None = None) -> None:
    repo_root = Path(repo_root).resolve()
    """Append step outputs for GitHub Actions ($GITHUB_OUTPUT). Values are single lines."""
    target = path or os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    values = {
        "mode": result.mode,
        "title": result.title.replace("\n", " "),
        "report": str(
            result.report.relative_to(repo_root) if result.report.is_relative_to(repo_root) else result.report
        ),
        "breaking": "true" if result.breaking else "false",
        "zip_removed": str(result.zip_removed.relative_to(repo_root)) if result.zip_removed else "",
    }
    with open(target, "a") as f:
        for k, v in values.items():
            f.write(f"{k}={v}\n")
