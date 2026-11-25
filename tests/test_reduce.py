"""Phase 2 mesh reduction: filters, per-part cap, merge by color, NOSIMPLIFY, and the triangle budget."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from cad2ascope.config import MeshConfig
from cad2ascope.errors import Warnings
from cad2ascope.meshes import GroupMesh, Part, glb_bytes
from cad2ascope.reduce import _cluster, _find_cap, reduce_groups

RED = (200, 30, 30, 255)
GREY = (128, 128, 128, 255)


def part(name, mesh, color=GREY, label=None, at=(0.0, 0.0, 0.0), visual=0):
    matrix = np.eye(4)
    matrix[:3, 3] = at
    placed = mesh.copy()
    placed.apply_transform(matrix)
    return Part(name, placed, color, label or name, (name, visual), mesh, matrix)


def heavy(subdivisions=5, radius=0.05):
    """A sphere with 20 * 4**subdivisions triangles (20,480 at 5)."""
    return trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)


def plate():
    return trimesh.creation.box(extents=(0.3, 0.2, 0.006))


def run(groups, **cfg):
    w = Warnings()
    out, stats = reduce_groups(groups, MeshConfig(**cfg), w)
    return out, stats, w


def test_under_budget_keeps_every_triangle():
    groups = [GroupMesh("model.glb", ["a", "b"], [part("a", plate()), part("b", plate(), RED, at=(1, 0, 0))])]
    out, stats, w = run(groups, triangle_budget=1000)
    assert stats.cap is None and stats.output_triangles == 24 and not list(w)
    assert len(out[0].meshes) == 2  # one per color


def test_budget_is_met_and_light_parts_are_untouched():
    parts = [part(f"gear{i}", heavy(), at=(i * 0.2, 0, 0)) for i in range(4)]
    parts += [part(f"plate{i}", plate(), RED, at=(0, i * 0.3, 0)) for i in range(10)]
    groups = [GroupMesh("model.glb", [p.name for p in parts], parts)]
    out, stats, w = run(groups, triangle_budget=5000, min_part_size_mm=0)
    assert stats.output_triangles <= 5000 * 1.05, stats.output_triangles
    assert not list(w)
    red = next(m for m in out[0].meshes if m.color == RED)
    assert len(red.mesh.faces) == 10 * 12  # plates are under the cap, so exactly as they were
    assert stats.capped_parts == 4


def test_identical_parts_are_reduced_once(monkeypatch):
    import cad2ascope.reduce as reduce_module

    calls = []
    original = reduce_module._reduce_to
    monkeypatch.setattr(
        reduce_module, "_reduce_to", lambda mesh, target: calls.append(target) or original(mesh, target)
    )
    shared = heavy()
    parts = [part(f"gear{i}", shared, at=(i * 0.2, 0, 0)) for i in range(5)]
    groups = [GroupMesh("model.glb", [p.name for p in parts], parts)]
    out, stats, _ = run(groups, triangle_budget=2000, min_part_size_mm=0)
    assert len(calls) == 1  # five instances of one mesh file, reduced once
    assert stats.output_triangles <= 2000 * 1.05


def test_excluded_and_small_parts_are_dropped():
    screw = part("bhcs_10_32", trimesh.creation.cylinder(radius=0.003, height=0.02), label="_10_32_BHCS_Steel")
    washer = part("tiny_washer", trimesh.creation.cylinder(radius=0.002, height=0.001))
    keep_small = part("bumper_letter", trimesh.creation.box(extents=(0.004, 0.004, 0.001)))
    groups = [GroupMesh("model.glb", ["a"], [part("a", plate()), screw, washer, keep_small])]
    out, stats, _ = run(groups, exclude_names=("*BHCS*",), min_part_size_mm=6, keep_detail=("*bumper*",))
    assert stats.excluded_parts == {"*BHCS*": 1}
    assert stats.small_parts == 1  # the washer; the bumper letter is kept despite being small
    names = [m.name for m in out[0].meshes]
    assert names == ["model_808080ff", "model_808080ff_NOSIMPLIFY"]


def test_keep_detail_is_never_capped():
    detail = part("bumper", heavy(4))
    parts = [detail] + [part(f"gear{i}", heavy(), at=(i * 0.2, 0, 0)) for i in range(3)]
    groups = [GroupMesh("model.glb", [p.name for p in parts], parts)]
    out, stats, _ = run(groups, triangle_budget=8000, min_part_size_mm=0, keep_detail=("bumper",))
    kept = next(m for m in out[0].meshes if m.keep_detail)
    assert len(kept.mesh.faces) == len(heavy(4).faces)


def test_keep_detail_over_budget_warns():
    groups = [GroupMesh("model.glb", ["b"], [part("bumper", heavy())])]
    _, _, w = run(groups, triangle_budget=1000, keep_detail=("bumper",))
    assert any("keep_detail parts alone" in m for m in w)


def test_nosimplify_name_reaches_the_glb():
    groups = [GroupMesh("model_0.glb", ["b"], [part("bumper", plate())])]
    out, _, _ = run(groups, keep_detail=("bumper",))
    scene = trimesh.load(trimesh.util.wrap_as_stream(glb_bytes(out[0].meshes)), file_type="glb")
    assert any("NOSIMPLIFY" in name for name in scene.geometry)
    assert any("NOSIMPLIFY" in name for name in scene.graph.nodes)


def test_find_cap():
    assert _find_cap([10, 20, 30], 100) is None
    cap = _find_cap([1000, 1000, 10], 500)
    assert sum(min(t, cap) for t in [1000, 1000, 10]) <= 500
    assert sum(min(t, cap + 1) for t in [1000, 1000, 10]) > 500


def test_cluster_meets_target_or_falls_back_to_a_box():
    mesh = heavy()
    reduced = _cluster(mesh, 2000)
    assert 0 < len(reduced.faces) <= 2000
    np.testing.assert_allclose(reduced.bounds, mesh.bounds, atol=0.01)
    tiny = _cluster(mesh, 3)  # no grid gives 1 to 3 triangles of a sphere
    assert len(tiny.faces) == 12
    np.testing.assert_allclose(tiny.bounds, mesh.bounds)


def test_reduction_is_deterministic():
    def build():
        parts = [part(f"gear{i}", heavy(), at=(i * 0.2, 0, 0)) for i in range(3)]
        out, _, _ = run([GroupMesh("model.glb", [p.name for p in parts], parts)], triangle_budget=3000)
        return glb_bytes(out[0].meshes)

    assert build() == build()


@pytest.mark.parametrize("budget", [1000, 20000])
def test_groups_share_the_budget(budget):
    base = [part(f"b{i}", heavy(), at=(i * 0.2, 0, 0)) for i in range(3)]
    comp = [part("arm", heavy(), RED)]
    groups = [GroupMesh("model.glb", ["b"], base), GroupMesh("model_0.glb", ["arm"], comp)]
    out, stats, _ = run(groups, triangle_budget=budget, min_part_size_mm=0)
    assert stats.output_triangles <= budget * 1.05
    assert out[1].triangles > 0 and out[0].triangles > out[1].triangles
