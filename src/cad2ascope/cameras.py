"""Camera and measured-frame connectors (PLAN §4 C7, §6.4 step 7, §7.4).

A ``cam_<NAME>`` connector is the camera's lens center in the WPILib camera frame (+X out of the lens, +Z up).
AdvantageScope's ``cameras`` entries use the same frame (Phase 0, B5), so the transform goes in unchanged.

Field of view: AdvantageScope uses ``fov / (width / height)`` as the vertical FOV (Phase 0, B5), so cad2ascope
writes ``fov = aspect × true vertical FOV``. Then the rendered view matches the real camera.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from cad2ascope.errors import CadError, Warnings
from cad2ascope.export import frame_links
from cad2ascope.grouping import Model

DEFAULT_RESOLUTION = (1280, 800)
DEFAULT_HFOV_DEG = 70.0


@dataclass
class Camera:
    name: str  # NAME from cam_<NAME>, matches the PhotonVision camera name
    link: str
    T: np.ndarray  # camera frame in robot frame at the export pose
    component: int | None  # moving mechanism it rides on, None = fixed to the robot
    resolution: tuple[int, int]
    fov_deg: float  # value written to config.json
    hfov_deg: float  # true horizontal field of view, for reports
    source: str  # "calibration: <file>", "fallback", or "default"


@dataclass
class Frame:
    name: str
    link: str
    T: np.ndarray
    component: int | None


def ascope_fov(width: float, height: float, fy: float) -> float:
    """The ``fov`` value that makes AdvantageScope render the camera's true view."""
    vfov = 2.0 * math.atan(height / (2.0 * fy))
    return math.degrees(vfov) * (width / height)


def fy_from_hfov(width: float, hfov_deg: float) -> float:
    """Focal length in pixels for a horizontal FOV, assuming square pixels."""
    return (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)


def read_calibration(path: Path) -> tuple[int, int, float, float]:
    """(width, height, fx, fy) from a PhotonVision calibration export ("<NAME> Calibration.json")."""
    try:
        data = json.loads(path.read_text())
        width = float(data["resolution"]["width"])
        height = float(data["resolution"]["height"])
        k = data["cameraIntrinsics"]["data"]
        fx, fy = float(k[0]), float(k[4])
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise CadError(
            f"{path} is not a PhotonVision calibration file cad2ascope can read. "
            "Export the calibration again from the PhotonVision web page."
        ) from None
    if width <= 0 or height <= 0 or fx <= 0 or fy <= 0 or width != int(width) or height != int(height):
        raise CadError(
            f"{path} has an impossible resolution or focal length. Export the calibration again from PhotonVision."
        )
    return int(width), int(height), fx, fy


def _calibration_file(folder: Path, name: str) -> Path | None:
    exact = folder / f"{name} Calibration.json"
    if exact.is_file():
        return exact
    want = f"{name} calibration.json".lower()
    for p in sorted(folder.glob("*.json")):
        if p.name.lower() == want:
            return p
    return None


def find_cameras(model: Model, repo_root: Path, warnings: Warnings | None = None) -> list[Camera]:
    cfg = model.config.cameras
    warnings = warnings if warnings is not None else model.warnings
    folder = (repo_root / cfg.photonvision_calibrations) if cfg.photonvision_calibrations else None
    if folder is not None and not folder.is_dir():
        warnings.add(
            f"The PhotonVision calibration folder {cfg.photonvision_calibrations!r} does not exist, so every camera "
            "uses the fallback resolution and field of view. Fix cameras.photonvision_calibrations in the config."
        )
        folder = None
    cams: list[Camera] = []
    for link in frame_links(model.robot, cfg.frame_prefix):
        name = link[len(cfg.frame_prefix) :]
        if not name:
            continue
        cal = _calibration_file(folder, name) if folder else None
        if cal is not None:
            w, h, _fx, fy = read_calibration(cal)
            source = f"calibration: {cal.name}"
        elif cfg.fallback_resolution is not None or cfg.fallback_fov_deg is not None:
            w, h = cfg.fallback_resolution or DEFAULT_RESOLUTION
            fy = fy_from_hfov(w, cfg.fallback_fov_deg or DEFAULT_HFOV_DEG)
            source = "fallback"
            if folder is not None:
                warnings.add(
                    f"No calibration file for camera {name} in {cfg.photonvision_calibrations}; using the fallback."
                )
        else:
            w, h = DEFAULT_RESOLUTION
            fy = fy_from_hfov(w, DEFAULT_HFOV_DEG)
            source = "default"
            warnings.add(
                f"Camera {name} has no calibration file and the config has no cameras.fallback, so it uses "
                f"{w}x{h} and {DEFAULT_HFOV_DEG:g}°. Add cameras.photonvision_calibrations or cameras.fallback."
            )
        component = model.group_of.get(link)
        if component is not None:
            joint = model.components[component].joint.name
            warnings.add(
                f"Camera {name} rides on {joint}. AdvantageScope's camera view is fixed to the robot, so it shows the "
                "view at the exported position only. The generated code still moves it with the mechanism."
            )
        hfov = math.degrees(2.0 * math.atan(w / (2.0 * fy)))
        cams.append(Camera(name, link, model.link_pose(link), component, (w, h), ascope_fov(w, h, fy), hfov, source))
    return cams


def find_frames(model: Model) -> list[Frame]:
    prefix = model.config.frame_prefix
    return [
        Frame(link[len(prefix) :], link, model.link_pose(link), model.group_of.get(link))
        for link in frame_links(model.robot, prefix)
        if link[len(prefix) :]
    ]
