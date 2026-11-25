"""Mesh reduction (PLAN §6.4 step 5, Phase 2): filter parts, cap heavy parts, merge by color.

1. Filter whole parts (one URDF visual = one part):
   - drop parts whose link name or mesh file name matches ``mesh.exclude_names`` (case-insensitive wildcards);
   - drop parts whose largest dimension is under ``mesh.min_part_size_mm``, unless they match ``keep_detail``.
2. Clean each mesh file once: weld vertices closer than 0.1 mm and drop degenerate and repeated triangles
   (Onshape's glTF repeats many: the 2026 turntable gear goes from 1.17 million to 0.37 million triangles).
3. Cap triangles per part. One cap is found so the whole robot fits ``mesh.triangle_budget``; parts under the cap
   are untouched, so plates, tubes and lettering keep their exact shape, and only heavy parts (gears, motors,
   terminals) are reduced. A heavy part is decimated with quadric edge collapse; where that stops short of the cap
   (it does on many real Onshape meshes), vertex clustering sized to that part finishes the job. Identical parts
   share one mesh file, so each file is reduced once. ``keep_detail`` parts are never capped.
4. Merge each group's parts into one mesh per color, so a file holds tens of meshes instead of tens of thousands.
   ``keep_detail`` parts get their own meshes named ``..._NOSIMPLIFY``, which AdvantageScope never drops
   (Phase 0, B6).
5. Re-shade with a 30° crease angle, so CAD edges stay sharp and flat faces stay smooth.
"""

from __future__ import annotations

import fnmatch
import math
from collections import Counter
from dataclasses import dataclass, field

import fast_simplification
import numpy as np
import trimesh

from cad2ascope.config import MeshConfig
from cad2ascope.errors import Warnings
from cad2ascope.meshes import GroupMesh, Part

CREASE_ANGLE = math.radians(30.0)
WELD_DIGITS = 4  # weld vertices closer than 0.1 mm
MIN_CAP = 12  # never cap a part below a box's worth of triangles
OVERSHOOT = 1.05  # quadric result may exceed its target by this much before clustering takes over


@dataclass
class OutMesh:
    name: str
    mesh: trimesh.Trimesh
    color: tuple[int, int, int, int]
    keep_detail: bool = False


@dataclass
class ReducedGroup:
    file: str
    links: list[str]
    meshes: list[OutMesh]
    source_triangles: int

    @property
    def triangles(self) -> int:
        return int(sum(len(m.mesh.faces) for m in self.meshes))


@dataclass
class MeshStats:
    budget: int
    source_triangles: int = 0
    kept_triangles: int = 0
    cleaned_triangles: int = 0
    output_triangles: int = 0
    cap: int | None = None  # triangles allowed per part, None = no cap needed
    capped_parts: int = 0
    excluded_parts: dict[str, int] = field(default_factory=dict)  # pattern -> parts removed
    excluded_triangles: int = 0
    small_parts: int = 0
    small_triangles: int = 0
    keep_detail_parts: int = 0
    clustered_files: list[str] = field(default_factory=list)  # mesh files the quadric decimator could not finish
    largest_parts: list[tuple[str, int]] = field(default_factory=list)  # (part name, source triangles), kept parts

    def as_dict(self) -> dict:
        return {
            "triangle_budget": self.budget,
            "source_triangles": self.source_triangles,
            "after_filters": self.kept_triangles,
            "after_cleanup": self.cleaned_triangles,
            "output_triangles": self.output_triangles,
            "per_part_cap": self.cap,
            "capped_parts": self.capped_parts,
            "excluded_by_pattern": self.excluded_parts,
            "excluded_triangles": self.excluded_triangles,
            "too_small_parts": self.small_parts,
            "too_small_triangles": self.small_triangles,
            "keep_detail_parts": self.keep_detail_parts,
            "clustered_mesh_files": self.clustered_files,
            "largest_kept_parts": [{"name": n, "triangles": t} for n, t in self.largest_parts],
        }


# ----------------------------------------------------------------------------------------------- filters


def _match(part: Part, patterns: tuple[str, ...]) -> str | None:
    names = (part.name.lower(), part.label.lower())
    for pat in patterns:
        p = pat.lower()
        if any(fnmatch.fnmatchcase(n, p) for n in names):
            return pat
    return None


def _filter(groups: list[GroupMesh], cfg: MeshConfig, stats: MeshStats) -> list[list[tuple[Part, bool]]]:
    """Per group, the pieces that survive the filters, each flagged keep_detail or not."""
    excluded: Counter[str] = Counter()
    largest: Counter[str] = Counter()
    kept_all: list[list[tuple[Part, bool]]] = []
    for group in groups:
        by_source: dict[tuple[str, int], list[Part]] = {}
        for part in group.parts:
            by_source.setdefault(part.source, []).append(part)
        kept: list[tuple[Part, bool]] = []
        for pieces in by_source.values():
            tris = sum(len(p.mesh.faces) for p in pieces)
            stats.source_triangles += tris
            hit = _match(pieces[0], cfg.exclude_names)
            if hit is not None:
                excluded[hit] += 1
                stats.excluded_triangles += tris
                continue
            keep = _match(pieces[0], cfg.keep_detail) is not None
            if not keep and cfg.min_part_size_mm > 0:
                lo = np.min([p.mesh.bounds[0] for p in pieces], axis=0)
                hi = np.max([p.mesh.bounds[1] for p in pieces], axis=0)
                if float(np.max(hi - lo)) * 1000.0 < cfg.min_part_size_mm:
                    stats.small_parts += 1
                    stats.small_triangles += tris
                    continue
            stats.keep_detail_parts += keep
            stats.kept_triangles += tris
            largest[pieces[0].label] = max(largest[pieces[0].label], tris)
            kept += [(p, keep) for p in pieces]
        kept_all.append(kept)
    stats.excluded_parts = dict(sorted(excluded.items()))
    stats.largest_parts = largest.most_common(10)
    return kept_all


# ----------------------------------------------------------------------------------------------- mesh operations


def _clean(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Weld at 0.1 mm and drop degenerate and repeated triangles. 0.1 mm is invisible at robot scale."""
    out = trimesh.Trimesh(np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces), process=False)
    out.merge_vertices(digits_vertex=WELD_DIGITS)
    out.update_faces(out.nondegenerate_faces())
    out.update_faces(out.unique_faces())
    out.remove_unreferenced_vertices()
    return out


def _cluster_once(vertices: np.ndarray, faces: np.ndarray, cell: float) -> tuple[np.ndarray, np.ndarray]:
    keys = np.floor((vertices - vertices.min(axis=0)) / cell).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    n = int(inverse.max()) + 1
    sums = np.zeros((n, 3))
    np.add.at(sums, inverse, vertices)
    points = sums / np.bincount(inverse, minlength=n)[:, None]
    f = inverse[faces]
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    if len(f):
        _, first = np.unique(np.sort(f, axis=1), axis=0, return_index=True)
        f = f[np.sort(first)]
    return points, f


def _cluster(mesh: trimesh.Trimesh, target: int) -> trimesh.Trimesh:
    """Vertex clustering: the finest grid (found by bisection) that brings the mesh to ``target`` triangles."""
    v = np.asarray(mesh.vertices, dtype=np.float64)
    f = np.asarray(mesh.faces, dtype=np.int64)
    lo, hi = 1e-5, float(np.max(np.ptp(v, axis=0))) or 1e-3  # meters
    best = None
    for _ in range(24):
        cell = math.sqrt(lo * hi)
        points, faces = _cluster_once(v, f, cell)
        if len(faces) <= target:
            best, hi = (points, faces), cell
        else:
            lo = cell
        if hi / lo < 1.02:
            break
    if best is None or len(best[1]) == 0:
        # No grid keeps any triangles within the target: stand in a box of the part's size, in the part's own frame.
        box = trimesh.creation.box(bounds=mesh.bounds)
        return trimesh.Trimesh(box.vertices, box.faces, process=False)
    out = trimesh.Trimesh(best[0], best[1], process=False)
    out.remove_unreferenced_vertices()
    return out


def _reduce_to(mesh: trimesh.Trimesh, target: int) -> tuple[trimesh.Trimesh, bool]:
    """At most about ``target`` triangles. Returns the mesh and whether vertex clustering was needed."""
    if len(mesh.faces) <= target:
        return mesh, False
    points, faces = fast_simplification.simplify(
        np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int64), target_count=target
    )
    out = trimesh.Trimesh(points, faces, process=False) if len(faces) else mesh
    if len(out.faces) > target * OVERSHOOT:
        return _cluster(out, target), True
    return out, False


def _find_cap(counts: list[int], available: int) -> int | None:
    """Smallest per-part cap c with sum(min(t, c)) <= available, or None if no cap is needed."""
    if sum(counts) <= available:
        return None
    lo, hi = MIN_CAP, max(counts)
    if sum(min(t, lo) for t in counts) > available:
        return lo
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if sum(min(t, mid) for t in counts) <= available:
            lo = mid
        else:
            hi = mid
    return lo


# ----------------------------------------------------------------------------------------------- main entry


def reduce_groups(groups: list[GroupMesh], cfg: MeshConfig, warnings: Warnings) -> tuple[list[ReducedGroup], MeshStats]:
    stats = MeshStats(budget=cfg.triangle_budget)
    kept = _filter(groups, cfg, stats)

    # Clean each distinct source piece once; instances of the same mesh file share it.
    cleaned: dict[int, trimesh.Trimesh] = {}
    names: dict[int, str] = {}

    def local_of(part: Part) -> trimesh.Trimesh:
        return part.local if part.local is not None else part.mesh

    for row in kept:
        for part, _ in row:
            key = id(local_of(part))
            if key not in cleaned:
                cleaned[key] = _clean(local_of(part))
                names[key] = part.label or part.name

    # One cap per part (a part = all pieces of one visual), applied to each of its pieces in proportion.
    part_tris: dict[tuple[int, tuple[str, int]], int] = {}
    keep_tris = 0
    for gi, row in enumerate(kept):
        for part, keep in row:
            n = len(cleaned[id(local_of(part))].faces)
            if keep:
                keep_tris += n
            else:
                part_tris[(gi, part.source)] = part_tris.get((gi, part.source), 0) + n
    stats.cleaned_triangles = keep_tris + sum(part_tris.values())
    available = cfg.triangle_budget - keep_tris
    if available <= 0:
        warnings.add(
            f"The keep_detail parts alone have {keep_tris} triangles, more than mesh.triangle_budget "
            f"({cfg.triangle_budget}). Raise the budget or shorten mesh.keep_detail."
        )
        available = MIN_CAP * max(1, len(part_tris))
    cap = _find_cap(list(part_tris.values()), available)
    stats.cap = cap
    stats.capped_parts = 0 if cap is None else sum(1 for t in part_tris.values() if t > cap)

    reduced_cache: dict[tuple[int, int], trimesh.Trimesh] = {}
    clustered: set[str] = set()
    out = []
    for gi, (group, row) in enumerate(zip(groups, kept, strict=True)):
        buckets: dict[tuple[tuple[int, int, int, int], bool], list[trimesh.Trimesh]] = {}
        for part, keep in row:
            key = id(local_of(part))
            base = cleaned[key]
            mesh = base
            if not keep and cap is not None:
                total = part_tris[(gi, part.source)]
                if total > cap:
                    target = max(MIN_CAP, int(len(base.faces) * cap / total))
                    ck = (key, target)
                    if ck not in reduced_cache:
                        reduced_cache[ck], was_clustered = _reduce_to(base, target)
                        if was_clustered:
                            clustered.add(names[key])
                    mesh = reduced_cache[ck]
            placed = mesh.copy()
            if part.local is not None and part.matrix is not None:
                placed.apply_transform(part.matrix)
            buckets.setdefault((part.color, keep), []).append(placed)

        stem = group.file.removesuffix(".glb")
        meshes = []
        for (color, keep), parts in sorted(buckets.items()):
            merged = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
            merged = trimesh.Trimesh(merged.vertices, merged.faces, process=False)
            merged.merge_vertices(digits_vertex=WELD_DIGITS)
            if len(merged.faces):
                merged = trimesh.graph.smooth_shade(merged, angle=CREASE_ANGLE)
            r, g, b, a = color
            name = f"{stem}_{r:02x}{g:02x}{b:02x}{a:02x}" + ("_NOSIMPLIFY" if keep else "")
            meshes.append(OutMesh(name, merged, color, keep))
        out.append(ReducedGroup(group.file, group.links, meshes, sum(len(p.mesh.faces) for p in group.parts)))

    stats.clustered_files = sorted(clustered)
    stats.output_triangles = sum(r.triangles for r in out)
    if stats.output_triangles > cfg.triangle_budget * OVERSHOOT:
        warnings.add(
            f"The model has {stats.output_triangles} triangles, over mesh.triangle_budget ({cfg.triangle_budget}). "
            "Add patterns to mesh.exclude_names (manifest.json lists the largest parts) or raise the budget."
        )
    return out, stats
