"""Place each group's meshes in robot frame and write one .glb per group (PLAN §6.4 step 5).

Phase 1 scope: placement and a correct file. Filtering, merging by color, decimation, and NOSIMPLIFY tagging are
Phase 2. What Phase 1 already guarantees, because AdvantageScope needs it (Phase 0, B6):

- every mesh has normals (AdvantageScope discards meshes without them), and
- every mesh has one material with a base color (AdvantageScope ignores vertex colors and textures).

Source meshes with per-face or per-vertex colors are split into one mesh per color. Each mesh is named
``<link>`` or ``<link>_<n>`` so Phase 2 can match ``exclude_names`` and ``keep_detail`` patterns against it.
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from trimesh.visual import ColorVisuals, TextureVisuals
from trimesh.visual.material import PBRMaterial

from cad2ascope.errors import CadError, Warnings
from cad2ascope.export import Export
from cad2ascope.grouping import Model
from cad2ascope.transforms import make_transform

DEFAULT_COLOR = (180, 180, 180, 255)
MESH_TYPES = {".glb", ".gltf", ".stl", ".obj", ".ply", ".off", ".dae"}


@dataclass
class Part:
    name: str
    mesh: trimesh.Trimesh  # vertices in robot frame
    color: tuple[int, int, int, int]


@dataclass
class GroupMesh:
    file: str
    links: list[str]
    parts: list[Part]

    @property
    def triangles(self) -> int:
        return int(sum(len(p.mesh.faces) for p in self.parts))


def _rgba(c) -> tuple[int, int, int, int]:
    """RGBA 0..255 from a 0..255 color with 3 or 4 channels (trimesh's ColorVisuals convention)."""
    a = np.asarray(c, dtype=float).ravel()
    if a.size == 3:
        a = np.append(a, 255.0)
    r, g, b, alpha = (int(round(max(0.0, min(255.0, float(x))))) for x in a[:4])
    return r, g, b, alpha


def _material_color(material) -> tuple[int, int, int, int]:
    base = getattr(material, "baseColorFactor", None)
    if base is not None:
        b = np.asarray(base, dtype=float)
        if b.max(initial=0) <= 1.0:
            b = b * 255.0
        return _rgba(b)
    main = getattr(material, "main_color", None)
    return _rgba(main) if main is not None else DEFAULT_COLOR


def _split_by_color(mesh: trimesh.Trimesh) -> list[tuple[trimesh.Trimesh, tuple[int, int, int, int]]]:
    visual = mesh.visual
    if isinstance(visual, TextureVisuals):
        color = _material_color(visual.material) if visual.material is not None else DEFAULT_COLOR
        return [(mesh, color)]
    if isinstance(visual, ColorVisuals) and visual.kind in ("face", "vertex"):
        face_colors = np.asarray(visual.face_colors, dtype=np.uint8)
        unique, inverse = np.unique(face_colors, axis=0, return_inverse=True)
        if len(unique) == 1:
            return [(mesh, _rgba(unique[0]))]
        out = []
        for i, c in enumerate(unique):
            sub = mesh.submesh([np.flatnonzero(inverse.ravel() == i)], append=True)
            out.append((sub, _rgba(c)))
        return out
    return [(mesh, DEFAULT_COLOR)]


def load_mesh_file(path: Path) -> list[tuple[trimesh.Trimesh, tuple[int, int, int, int]]]:
    """Meshes in one file, with node transforms applied, split by color."""
    if path.suffix.lower() not in MESH_TYPES:
        raise CadError(f"Mesh file {path.name} has a format cad2ascope cannot read. Export URDF with glTF meshes.")
    try:
        scene = trimesh.load(path, force="scene")
    except Exception as e:  # trimesh raises many types for bad files
        raise CadError(
            f"Mesh file {path.name} could not be read ({type(e).__name__}). Re-export from Onshape."
        ) from None
    out = []
    for geom in scene.dump(concatenate=False):  # applies each node's transform
        if isinstance(geom, trimesh.Trimesh) and len(geom.faces):
            out += _split_by_color(geom)
    return out


def place_groups(model: Model, export: Export, warnings: Warnings | None = None) -> list[GroupMesh]:
    """One GroupMesh for the base model, then one per component, all in robot frame at the export pose."""
    warnings = warnings if warnings is not None else model.warnings
    groups = [GroupMesh("model.glb", model.base_links, [])] + [GroupMesh(c.file, c.links, []) for c in model.components]
    cache: dict[Path, list[tuple[trimesh.Trimesh, tuple[int, int, int, int]]]] = {}
    for gi, group in enumerate(groups):
        for link_name in group.links:
            link = model.robot.links[link_name]
            pose = model.link_pose(link_name)
            n = 0
            for visual in link.visuals:
                path = export.resolve_mesh(visual.mesh)
                if path not in cache:
                    cache[path] = load_mesh_file(path)
                scale = make_transform()
                scale[:3, :3] = np.diag(visual.scale)
                placement = pose @ visual.origin @ scale
                for mesh, color in cache[path]:
                    m = mesh.copy()
                    m.apply_transform(placement)
                    name = link_name if n == 0 else f"{link_name}_{n}"
                    n += 1
                    group.parts.append(Part(name, m, color))
        if gi > 0 and not group.parts:
            comp = model.components[gi - 1]
            warnings.add(
                f"{comp.joint.name} moves part {comp.root_link!r}, but nothing visible is attached to it, so "
                f"{group.file} is empty. Check that its parts are not suppressed in the export configuration."
            )
    return groups


_EMPTY_GLB_JSON = json.dumps(
    {"asset": {"version": "2.0", "generator": "cad2ascope"}, "scenes": [{"nodes": []}], "scene": 0}
)


def _empty_glb() -> bytes:
    body = _EMPTY_GLB_JSON.encode()
    body += b" " * (-len(body) % 4)
    header = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(body))
    return header + struct.pack("<I4s", len(body), b"JSON") + body


def glb_bytes(group: GroupMesh) -> bytes:
    """Binary glTF with normals and one base-color material per color."""
    if not group.parts:
        return _empty_glb()
    scene = trimesh.Scene()
    materials: dict[tuple[int, int, int, int], PBRMaterial] = {}
    for part in group.parts:
        mat = materials.get(part.color)
        if mat is None:
            r, g, b, a = part.color
            mat = PBRMaterial(
                name=f"color_{r:02x}{g:02x}{b:02x}{a:02x}",
                baseColorFactor=[r, g, b, a],
                metallicFactor=0.0,
                roughnessFactor=1.0,
                alphaMode="BLEND" if a < 255 else "OPAQUE",
            )
            materials[part.color] = mat
        mesh = trimesh.Trimesh(vertices=part.mesh.vertices, faces=part.mesh.faces, process=False)
        mesh.visual = TextureVisuals(material=mat)
        scene.add_geometry(mesh, geom_name=part.name, node_name=part.name)
    buf = io.BytesIO(scene.export(file_type="glb", include_normals=True))
    return buf.getvalue()
