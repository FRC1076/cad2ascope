"""Load and validate the team config file, cad/advantagescope.yaml (PLAN §6.3).

The schema is spec/advantagescope.schema.json. A copy ships inside the package (data/) so an installed tool can
validate without the repo; tests/test_config.py checks the two copies are identical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from cad2ascope.errors import CadError

CONFIG_NAME = "cad/advantagescope.yaml"


def load_schema() -> dict:
    return json.loads(resources.files("cad2ascope").joinpath("data/advantagescope.schema.json").read_text())


@dataclass(frozen=True)
class RobotConfig:
    name: str
    folder: str
    origin_frame: str = "ascope_origin"
    onshape_url: str | None = None
    configuration: str | None = None
    version: str = "latest"


@dataclass(frozen=True)
class JointConfig:
    signal: str
    ratio: float = 1.0
    direction: int = 1
    zero_offset_deg: float | None = None
    zero_offset_m: float | None = None


@dataclass(frozen=True)
class MeshConfig:
    triangle_budget: int = 300_000
    exclude_names: tuple[str, ...] = ()
    min_part_size_mm: float = 6.0
    keep_detail: tuple[str, ...] = ()


@dataclass(frozen=True)
class CamerasConfig:
    frame_prefix: str = "cam_"
    photonvision_calibrations: str | None = None
    fallback_resolution: tuple[int, int] | None = None
    fallback_fov_deg: float | None = None
    baseline: str | None = None


@dataclass(frozen=True)
class CodegenConfig:
    java_package: str = "frc.robot.generated"
    output: str = "src/main/java/frc/robot/generated/RobotModel.java"
    test_output: str = "src/test/java/frc/robot/generated/RobotModelTest.java"


@dataclass(frozen=True)
class Config:
    robot: RobotConfig
    signals: dict[str, str]  # signal name -> units ("m" or "rad")
    joints: dict[str, JointConfig]  # in file order
    mesh: MeshConfig = field(default_factory=MeshConfig)
    cameras: CamerasConfig = field(default_factory=CamerasConfig)
    frame_prefix: str = "frame_"
    codegen: CodegenConfig = field(default_factory=CodegenConfig)
    source: str = CONFIG_NAME


def _where(path: Any) -> str:
    parts = [str(p) for p in path]
    return ".".join(parts) if parts else "the top level"


def _describe(error: jsonschema.ValidationError) -> str:
    where = _where(error.absolute_path)
    v = error.validator
    if v == "required":
        return f"{where}: {error.message.replace(' is a required property', '')} is missing. Add it."
    if v == "additionalProperties":
        return f"{where}: {error.message}. Check the spelling, or remove it."
    if v == "enum":
        allowed = ", ".join(json.dumps(x) for x in error.validator_value)
        return f"{where}: {json.dumps(error.instance)} is not allowed. Use one of: {allowed}."
    if v == "pattern" and error.absolute_path and error.absolute_path[-1] == "folder":
        return f"{where}: {json.dumps(error.instance)} must start with Robot_ and use only letters, digits, _ and -."
    if v == "pattern" and len(error.absolute_path) == 2 and error.absolute_path[0] == "robot":
        return f"{where}: {json.dumps(error.instance)} does not look right. Copy the full assembly URL from Onshape."
    if v == "propertyNames" or "propertyNames" in error.schema_path:
        # A bad key: jsonschema reports it as a pattern error on the key itself, at the section's path.
        section = where
        hint = (
            "Joint names must start with j_ (rename the mate in Onshape)."
            if section == "joints"
            else "Signal names use lowercase letters, digits and _ and start with a letter."
        )
        return f"{section}: {json.dumps(error.instance)} is not a valid name. {hint}"
    if v == "not" and error.absolute_path and error.absolute_path[-1] == "ratio":
        return f"{where}: ratio cannot be 0. Use 1 if the joint moves exactly as the signal says."
    return f"{where}: {error.message}"


def parse_config(data: Any, source: str = CONFIG_NAME) -> Config:
    """Validate parsed YAML against the schema and return a typed Config. Raises CadError."""
    if data is None:
        raise CadError(f"{source} is empty. Run 'cad2ascope init' to make a starter file.")
    errors = sorted(jsonschema.Draft202012Validator(load_schema()).iter_errors(data), key=lambda e: list(e.path))
    # propertyNames errors report the bad key as the instance; collapse duplicates from nested validators.
    if errors:
        lines = []
        for e in errors:
            line = _describe(e)
            if line not in lines:
                lines.append(line)
        raise CadError(f"{source} has {len(lines)} problem(s):\n" + "\n".join(f"  - {x}" for x in lines))

    r = data["robot"]
    robot = RobotConfig(
        name=r["name"],
        folder=r["folder"],
        origin_frame=r.get("origin_frame", "ascope_origin"),
        onshape_url=r.get("onshape_url"),
        configuration=r.get("configuration"),
        version=str(r.get("version", "latest")),
    )
    signals = {name: s["units"] for name, s in (data.get("signals") or {}).items()}
    joints = {
        name: JointConfig(
            signal=j["signal"],
            ratio=float(j.get("ratio", 1.0)),
            direction=int(j.get("direction", 1)),
            zero_offset_deg=j.get("zero_offset_deg"),
            zero_offset_m=j.get("zero_offset_m"),
        )
        for name, j in (data.get("joints") or {}).items()
    }
    problems = [
        f"joints.{name}: signal {j.signal!r} is not listed under signals. Add it there, or fix the spelling."
        for name, j in joints.items()
        if j.signal not in signals
    ]
    if problems:
        raise CadError(f"{source} has {len(problems)} problem(s):\n" + "\n".join(f"  - {x}" for x in problems))

    m = data.get("mesh") or {}
    mesh = MeshConfig(
        triangle_budget=int(m.get("triangle_budget", 300_000)),
        exclude_names=tuple(m.get("exclude_names", ())),
        min_part_size_mm=float(m.get("min_part_size_mm", 6.0)),
        keep_detail=tuple(m.get("keep_detail", ())),
    )
    c = data.get("cameras") or {}
    fb = c.get("fallback") or {}
    cameras = CamerasConfig(
        frame_prefix=c.get("frame_prefix", "cam_"),
        photonvision_calibrations=c.get("photonvision_calibrations"),
        fallback_resolution=tuple(fb["resolution"]) if "resolution" in fb else None,
        fallback_fov_deg=fb.get("fov_deg"),
        baseline=c.get("baseline"),
    )
    g = data.get("codegen") or {}
    defaults = CodegenConfig()
    codegen = CodegenConfig(
        java_package=g.get("java_package", defaults.java_package),
        output=g.get("output", defaults.output),
        test_output=g.get("test_output", defaults.test_output),
    )
    return Config(
        robot=robot,
        signals=signals,
        joints=joints,
        mesh=mesh,
        cameras=cameras,
        frame_prefix=(data.get("frames") or {}).get("frame_prefix", "frame_"),
        codegen=codegen,
        source=source,
    )


def load_config(path: str | Path) -> Config:
    """Read and validate a team config file. Raises CadError with a student-readable message."""
    path = Path(path)
    if not path.is_file():
        raise CadError(f"Cannot find {path}. Run 'cad2ascope init' to make a starter config, or pass --config.")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" near line {mark.line + 1}" if mark is not None else ""
        raise CadError(
            f"{path} is not valid YAML{where}. Check indentation (spaces, not tabs) and that every ':' has a space after it."
        ) from None
    return parse_config(data, source=str(path))
