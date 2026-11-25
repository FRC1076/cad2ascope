"""`cad2ascope render`: preview PNGs of a built robot (PLAN §6.2, §8.1 step 5, §10.3 item 2).

Reads only the built folder (config.json, manifest.json, model*.glb), so the previews show exactly what was
written. Components are placed the way AdvantageScope places them (Phase 0, B3):

    world = component pose · Translate(zeroedPosition) · Rotate(zeroedRotations)

with the component pose computed from the signals the same way the generated RobotModel.java does.

The renderer is a small z-buffer rasterizer in numpy (orthographic camera, flat Lambert shading, one layer of
transparency, 2× supersampling). It needs no GPU, display or extra packages, so it runs in GitHub Actions.
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from cad2ascope.errors import CadError
from cad2ascope.transforms import from_config, make_transform

BACKGROUND = np.array([233, 231, 238], dtype=float)
LIGHT = np.array([0.45, 0.35, 0.82])
VIEW_DIR = np.array([-1.0, -0.8, -0.65])  # camera looks from front-left-above toward the robot
OPAQUE_ALPHA = 0.75  # AdvantageScope's transparent cutoff (Phase 0, B6)


@dataclass
class Mesh:
    vertices: np.ndarray  # (n, 3) in the file's frame
    faces: np.ndarray
    color: np.ndarray  # rgba 0..1


def load_glb(path: Path) -> list[Mesh]:
    try:
        scene = trimesh.load(path, force="scene")
    except Exception:
        if path.stat().st_size < 1024:  # an empty component file (no meshes) is fine
            return []
        raise CadError(f"{path.name} could not be read. Run 'cad2ascope build' again.") from None
    out = []
    for geom in scene.dump(concatenate=False):
        if not isinstance(geom, trimesh.Trimesh) or not len(geom.faces):
            continue
        mat = getattr(geom.visual, "material", None)
        base = getattr(mat, "baseColorFactor", None)
        color = np.array(base if base is not None else [180, 180, 180, 255], dtype=float)
        if color.max() > 1.0:
            color = color / 255.0
        out.append(Mesh(np.asarray(geom.vertices, dtype=float), np.asarray(geom.faces), color))
    return out


# ----------------------------------------------------------------------------------------------- kinematics


def component_poses(manifest: dict, signals: list[float]) -> list[np.ndarray]:
    """Same chain as RobotModel.componentPoses, from the manifest's T0, axis, ratio, direction and zero offset."""
    poses: list[np.ndarray] = []
    names = manifest.get("signals") or []
    for c in manifest["components"]:
        t0 = np.array(c["T0"], dtype=float)
        parent_t0 = (
            np.eye(4)
            if c["parent_component"] is None
            else np.array(manifest["components"][c["parent_component"]]["T0"])
        )
        parent = np.eye(4) if c["parent_component"] is None else poses[c["parent_component"]]
        origin = np.linalg.inv(parent_t0) @ t0
        value = signals[names.index(c["signal"])] if c["signal"] in names else 0.0
        q = float(c["direction"]) * float(c["ratio"]) * (value - float(c.get("zero_offset", 0.0)))
        a = np.array(c["axis"], dtype=float)
        a = a / (np.linalg.norm(a) or 1.0)
        if c["type"] == "prismatic":
            motion = make_transform(np.eye(3), a * q)
        else:
            k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
            motion = make_transform(np.eye(3) + math.sin(q) * k + (1 - math.cos(q)) * (k @ k))
        poses.append(parent @ origin @ motion)
    return poses


def signal_ranges(manifest: dict) -> dict[str, tuple[float, float]]:
    """Signal limits in robot-code units, intersected over the joints each signal drives."""
    out: dict[str, tuple[float, float]] = {}
    for name in manifest.get("signals") or []:
        lo, hi = -math.inf, math.inf
        for c in manifest["components"]:
            if c["signal"] != name or not c.get("limits") or None in c["limits"]:
                continue
            scale = float(c["direction"]) * float(c["ratio"])
            a = c["limits"][0] / scale + c.get("zero_offset", 0.0)
            b = c["limits"][1] / scale + c.get("zero_offset", 0.0)
            lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
        if math.isfinite(lo) and math.isfinite(hi) and lo <= hi:
            out[name] = (lo, hi)
    return out


# ----------------------------------------------------------------------------------------------- rasterizer


def _camera(points: np.ndarray, width: int, height: int):
    d = VIEW_DIR / np.linalg.norm(VIEW_DIR)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(d, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, d)
    basis = np.stack([right, true_up, d])  # rows: screen x, screen y, depth
    p = points @ basis.T
    lo, hi = p[:, :2].min(axis=0), p[:, :2].max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    scale = 0.9 * min(width / span[0], height / span[1])
    center = (lo + hi) / 2
    return basis, scale, center


def _fill(t, d, c, px, py, width, height, zbuf, cbuf) -> None:
    """Test candidate pixels (px, py: one row per triangle) against triangles t (n, 3, 2); keep the nearest."""
    cx, cy = px + 0.5, py + 0.5
    (x0, y0), (x1, y1), (x2, y2) = (t[:, i, :].T for i in range(3))
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    ok_den = np.abs(den) > 1e-12
    den = np.where(ok_den, den, 1.0)
    w0 = ((y1 - y2)[:, None] * (cx - x2[:, None]) + (x2 - x1)[:, None] * (cy - y2[:, None])) / den[:, None]
    w1 = ((y2 - y0)[:, None] * (cx - x2[:, None]) + (x0 - x2)[:, None] * (cy - y2[:, None])) / den[:, None]
    w2 = 1 - w0 - w1
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0) & ok_den[:, None]
    inside &= (px >= 0) & (py >= 0) & (px < width) & (py < height)
    ti, fi = np.nonzero(inside)
    if not len(ti):
        return
    pix = (py[ti, fi] * width + px[ti, fi]).astype(np.int64)
    z = w0[ti, fi] * d[ti, 0] + w1[ti, fi] * d[ti, 1] + w2[ti, fi] * d[ti, 2]
    order = np.lexsort((z, pix))
    pix, z, ti = pix[order], z[order], ti[order]
    first = np.ones(len(pix), dtype=bool)
    first[1:] = pix[1:] != pix[:-1]
    pix, z, ti = pix[first], z[first], ti[first]
    closer = z < zbuf[pix]
    zbuf[pix[closer]] = z[closer]
    cbuf[pix[closer]] = c[ti[closer]]


BATCH_MAX_PX = 256  # triangles up to this size on screen are drawn in vectorized batches


def _rasterize(tri: np.ndarray, depth: np.ndarray, shade: np.ndarray, width: int, height: int, zbuf, cbuf) -> None:
    """Draw triangles (n, 3, 2) in pixel coordinates, with per-corner depth (n, 3) interpolated across each
    triangle and one color per triangle, into the z-buffer and color buffer."""
    if not len(tri):
        return
    lo = np.floor(tri.min(axis=1)).astype(int)
    hi = np.ceil(tri.max(axis=1)).astype(int)
    size = np.maximum(hi - lo, 1).max(axis=1)
    keep = (hi[:, 0] >= 0) & (hi[:, 1] >= 0) & (lo[:, 0] < width) & (lo[:, 1] < height)
    # Small and medium triangles: one test grid of k x k pixels per triangle, grouped by size (powers of two).
    k, lower = 2, 0
    while lower < BATCH_MAX_PX:
        sel = np.flatnonzero(keep & (size > lower) & (size <= k))
        if len(sel):
            ox, oy = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="xy")
            for chunk in np.array_split(sel, len(sel) * (k + 1) ** 2 // 4_000_000 + 1):
                px = lo[chunk, 0, None] + ox.ravel()[None, :]
                py = lo[chunk, 1, None] + oy.ravel()[None, :]
                _fill(tri[chunk], depth[chunk], shade[chunk], px, py, width, height, zbuf, cbuf)
        lower, k = k, k * 2
    # Large triangles (few): test only their bounding box, clipped to the image, one at a time.
    for i in np.flatnonzero(keep & (size > BATCH_MAX_PX)):
        x_lo, y_lo = max(lo[i, 0], 0), max(lo[i, 1], 0)
        x_hi, y_hi = min(hi[i, 0], width - 1), min(hi[i, 1], height - 1)
        gx, gy = np.meshgrid(np.arange(x_lo, x_hi + 1), np.arange(y_lo, y_hi + 1), indexing="xy")
        _fill(
            tri[i : i + 1],
            depth[i : i + 1],
            shade[i : i + 1],
            gx.ravel()[None, :],
            gy.ravel()[None, :],
            width,
            height,
            zbuf,
            cbuf,
        )


def render(meshes: list[Mesh], width: int = 960, height: int = 720, supersample: int = 2) -> np.ndarray:
    """RGB image (height, width, 3) uint8 of the meshes, all already in robot frame."""
    if not meshes:
        return np.tile(BACKGROUND.astype(np.uint8), (height, width, 1))
    W, H = width * supersample, height * supersample
    all_pts = np.vstack([m.vertices for m in meshes])
    basis, scale, center = _camera(all_pts, W, H)
    light = LIGHT / np.linalg.norm(LIGHT)
    layers = {}
    for transparent in (False, True):
        zbuf = np.full(W * H, np.inf)
        cbuf = np.zeros((W * H, 3))
        for m in meshes:
            if (m.color[3] < OPAQUE_ALPHA) != transparent:
                continue
            v = m.vertices[m.faces]  # (n, 3, 3)
            n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            lambert = np.abs(n @ light)  # two-sided: CAD normals are not always consistent
            shade = m.color[:3][None, :] * (0.35 + 0.65 * lambert)[:, None] * 255.0
            p = v @ basis.T
            xy = (p[:, :, :2] - center) * scale
            tri = np.stack([xy[:, :, 0] + W / 2, H / 2 - xy[:, :, 1]], axis=-1)
            _rasterize(tri, p[:, :, 2], shade, W, H, zbuf, cbuf)
        layers[transparent] = (zbuf, cbuf)
    zo, co = layers[False]
    zt, ct = layers[True]
    img = np.where(np.isfinite(zo)[:, None], co, BACKGROUND[None, :])
    front = np.isfinite(zt) & (zt < zo)
    img[front] = 0.55 * img[front] + 0.45 * ct[front]
    img = img.reshape(H, W, 3)
    img = img.reshape(height, supersample, width, supersample, 3).mean(axis=(1, 3))
    return np.clip(np.round(img), 0, 255).astype(np.uint8)


def png_bytes(img: np.ndarray) -> bytes:
    """Encode an (h, w, 3) uint8 image as PNG with the standard library."""
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


# ----------------------------------------------------------------------------------------------- previews


@dataclass
class Preview:
    file: str
    caption: str


@dataclass
class RenderResult:
    previews: list[Preview]
    zero_check_pixels: int  # pixels that differ between "zero poses published" and "no poses published"


def _placed(base: list[Mesh], comps: list[list[Mesh]], transforms: list[np.ndarray]) -> list[Mesh]:
    out = list(base)
    for meshes, t in zip(comps, transforms, strict=True):
        for m in meshes:
            v = m.vertices @ t[:3, :3].T + t[:3, 3]
            out.append(Mesh(v, m.faces, m.color))
    return out


def render_folder(folder: Path, out_dir: Path, width: int = 960, height: int = 720) -> RenderResult:
    """Write preview PNGs for a built robot folder and run the zero-pose check (PLAN §10.3 item 2)."""
    try:
        config = json.loads((folder / "config.json").read_text())
        manifest = json.loads((folder / "manifest.json").read_text())
    except (OSError, ValueError):
        raise CadError(
            f"{folder} does not look like a cad2ascope build (config.json or manifest.json missing). Run 'cad2ascope build' first."
        ) from None
    base = load_glb(folder / "model.glb")
    comps = [load_glb(folder / c["file"]) for c in manifest["components"]]
    zeroed = [from_config(c["zeroedRotations"], c["zeroedPosition"]) for c in config["components"]]
    signals = list(manifest.get("signals") or [])

    def at(values: list[float]) -> list[Mesh]:
        poses = component_poses(manifest, values)
        return _placed(base, comps, [p @ z for p, z in zip(poses, zeroed, strict=True)])

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("preview_*.png"):
        old.unlink()
    previews = []
    zero = [0.0] * len(signals)
    img_zero = render(at(zero), width, height)
    (out_dir / "preview_zero.png").write_bytes(png_bytes(img_zero))
    previews.append(Preview("preview_zero.png", "All mechanisms at zero"))

    # §10.3 item 2: with zero poses published the model must look the same as with no poses at all.
    robot = from_config(config.get("rotations", []), config.get("position", [0, 0, 0]))
    img_none = render(_placed(base, comps, [robot] * len(comps)), width, height)
    differing = int(np.count_nonzero(np.any(np.abs(img_zero.astype(int) - img_none.astype(int)) > 2, axis=2)))

    for name, (lo, hi) in signal_ranges(manifest).items():
        for label, value in (("min", lo), ("max", hi)):
            values = list(zero)
            values[signals.index(name)] = value
            file = f"preview_{name}_{label}.png"
            (out_dir / file).write_bytes(png_bytes(render(at(values), width, height)))
            previews.append(
                Preview(file, f"{name} at its {'lowest' if label == 'min' else 'highest'} limit ({value:.3g})")
            )
    return RenderResult(previews, differing)


def preview_markdown(result: RenderResult, link_base: str) -> str:
    lines = ["## Previews", ""]
    if result.zero_check_pixels == 0:
        lines.append(
            "Zero-pose check (PLAN §10.3 item 2): the model with zero poses published looks identical to the model with no poses. Pass."
        )
    else:
        lines.append(
            f"Zero-pose check (PLAN §10.3 item 2): **{result.zero_check_pixels} pixels differ** between zero poses and no "
            "poses. A component will jump when the robot code starts publishing poses. Check the export pose (PLAN §4 C6)."
        )
    lines.append("")
    base = link_base.rstrip("/") + "/" if link_base else ""
    for p in result.previews:
        lines.append(f"**{p.caption}**")
        lines.append("")
        lines.append(f"![{p.caption}]({base}{p.file})")
        lines.append("")
    return "\n".join(lines)
