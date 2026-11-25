# Phase 2 results: mesh reduction

Measured 2026-11-25 on manual URDF + glTF exports of the 2025 and 2026 pilot robots (medium resolution, "rigid subassemblies as a single link" off). The robots' CAD has not yet had the PLAN §4 edits, so these builds use the URDF root as the origin and list at most one joint; the mesh numbers do not depend on that.

## What the reduction does

See `src/cad2ascope/reduce.py` for details.

1. **Filter whole parts:** drop names matching `mesh.exclude_names`, and parts whose largest dimension is under `mesh.min_part_size_mm`, unless they match `mesh.keep_detail`.
2. **Clean each mesh file once:** weld vertices closer than 0.1 mm and drop degenerate and repeated triangles. Onshape's glTF repeats many triangles; the 2026 robot's largest part (a 200-tooth turntable gear) drops from 1.17 million to 0.37 million triangles here, and the whole 2026 robot from 5.0 to 3.3 million.
3. **Cap triangles per part:** find one cap so the whole robot fits `mesh.triangle_budget`. Parts under the cap are untouched, so plates, tubes, panels and lettering keep their exact shape. Heavy parts are decimated with quadric edge collapse (fast-simplification). On these meshes that algorithm often stops at 10 to 30% of the input whatever target it is given, so vertex clustering, with a grid sized to that part, finishes the job. A part that cannot keep any triangles at its cap becomes a box of its size. Identical parts share one mesh file and are reduced once.
4. **Merge each group by color**, weld again, and re-shade with a 30° crease angle. `keep_detail` parts get separate meshes named `..._NOSIMPLIFY`.

The first version decimated whole merged color meshes with one ratio. It met the budget but visibly wrecked simple parts (bumper numbers, polycarbonate panels, rods), because one coarse clustering grid was applied across the robot. Capping per part fixed that.

## Numbers

Budget 300,000 triangles. Fasteners excluded with `["*screw*", "*bolt*", "*nut*", "*washer*", "*rivet*", "*bhcs*", "*shcs*", "*fhcs*"]` (most Onshape fasteners are named BHCS, SHCS or FHCS, not "screw"). `min_part_size_mm: 6`.

| | 2026 | 2025 |
| --- | --- | --- |
| Source triangles | 6,343,326 | 22,160,828 |
| After name and size filters | 4,995,914 | 13,545,528 |
| After weld and de-duplication | 3,257,148 | 7,618,909 |
| Output triangles | 295,682 | 292,846 |
| Per-part cap | 426 | 223 |
| Parts capped | 632 | 1,334 |
| Total `.glb` size | 13.0 MB | 14.6 MB |
| Build time (whole `cad2ascope build`, this Mac) | 9 s | 13 s |
| Unreduced build for comparison | 182 MB, 6.3 M triangles | not built |

With `keep_detail: ["*bumper*", "front_side*", "left_side*", "right_side*", "back_side*"]` on 2026, the bumper numbers stay crisp for about 700 more triangles (296,379 in total, still 13.0 MB).

Checked by eye in a three.js viewer (the renderer AdvantageScope uses), reduced against unreduced 2026: frame, panels, rails, rollers, belts and bumpers match. Heavy mechanical parts (gears, motors, planetary gearboxes) are visibly simplified but recognizable.

## Not yet checked

- **Load time in AdvantageScope on a team laptop** (PLAN §1 success criterion 4, decision #5). Needs a person on a team laptop.
- **How the model looks in AdvantageScope itself.** The check above used three.js directly, with AdvantageScope's per-mesh simplification not applied. Merged meshes are large, so AdvantageScope's radius-based culling (Phase 0, B6) should not remove anything.
- **Git LFS (decision #6):** about 13 to 15 MB per model update. At 20 to 30 updates a season that adds roughly 0.3 to 0.45 GB to a robot repo's history, unless an unchanged robot produces identical files (builds are byte-for-byte repeatable, and Git stores identical files once).
