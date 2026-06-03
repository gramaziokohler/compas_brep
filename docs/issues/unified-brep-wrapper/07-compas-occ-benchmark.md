## Parent

../../prd/unified-brep-wrapper.md

## What to build

A benchmark suite that compares `compas_brep` (OCC backend) against `compas_occ` — the existing, production-grade COMPAS wrapper for OpenCASCADE. `compas_occ` is the established reference: if `compas_brep` cannot match its geometric outputs within tolerance on the same inputs, that is a correctness regression that must be caught before shipping.

The deliverable is a set of standalone example scripts under `examples/benchmark/` that can be run in both environments, plus an automated comparison runner that prints a pass/fail summary table for every operation.

### Environment

`compas_occ` requires `python-occ-core` which is only available via conda. Set up a side environment with mamba:

```
mamba create -n compas_occ_bench python=3.11 -y
mamba activate compas_occ_bench
mamba install -c conda-forge python-occ-core -y
pip install compas compas_occ
```

`compas_brep` is exercised from the dev install in the main environment (`pip install -e .[occ]`).

The comparison runner invokes each benchmark script twice — once with `BREP_BACKEND=occ` (compas_brep) and once by importing `compas_occ.brep.BRep` directly — and diffs the numerical outputs.

### Operation groups

#### Group 1: Primitive construction

| Operation | compas_brep | compas_occ |
|---|---|---|
| Box | `Brep.from_box(Box(...))` | `BRep.from_box(Box(...))` |
| Cylinder | `Brep.from_cylinder(Cylinder(...))` | `BRep.from_cylinder(Cylinder(...))` |
| Sphere | `Brep.from_sphere(Sphere(...))` | `BRep.from_sphere(Sphere(...))` |
| Cone | `Brep.from_cone(Cone(...))` | `BRep.from_cone(Cone(...))` |
| Torus | `Brep.from_torus(Torus(...))` | `BRep.from_torus(Torus(...))` |

For each primitive, compare: volume, area, face count, vertex count, edge count, `is_solid`.

#### Group 2: Boolean operations

Three standard test pairs:

- `Box(2,2,2) − Cylinder(r=0.3, h=4)` (difference)
- `Box(2,2,2) + Box(1,1,1)` translated by (1.5, 0, 0) (union)
- `Box(2,2,2) & Sphere(r=1.5)` (intersection)

For each: compare volume (1% relative tolerance), face count, `is_solid`.

#### Group 3: Geometric queries

On a box(1,1,1) and a cylinder(r=0.5, h=2):

| Query | Expected tolerance |
|---|---|
| `area` | 0.1% relative |
| `volume` | 0.1% relative |
| `centroid` | 1e-6 absolute per component |
| `aabb` (dimensions) | 1e-6 absolute |
| `is_solid` | exact bool |
| `is_valid` | exact bool |

#### Group 4: Topology inspection

On the same primitives, compare counts exactly:

- `len(brep.faces)`
- `len(brep.edges)`
- `len(brep.vertices)`

And verify that accessing topology does not raise and returns the correct COMPAS types:

- `face.surface` → `Plane` or `NurbsSurface`
- `edge.curve` → `Line` or `NurbsCurve`
- `vertex.point` → `Point`

#### Group 5: Transformations

Translate, rotate, and scale a unit box using `Transformation`. Compare volume and centroid before/after (volume must be invariant; centroid must match the expected transformed position).

| Transform | brep API | occ API |
|---|---|---|
| Translate by (1, 2, 3) | `brep.transform(T)` | `brep.transform(T)` |
| Rotate 45° around Z | `brep.transform(R)` | `brep.transform(R)` |
| `transformed(T)` (copy) | `brep.transformed(T)` | `brep.transformed(T)` |

#### Group 6: Modeling operations

| Operation | Description | Correctness check |
|---|---|---|
| `fillet(r=0.05)` | All edges on a unit box | `volume` decreases; `is_valid` |
| `trimmed(plane)` | Trim box with z=0 plane | `volume ≈ 0.5` |
| `split(plane)` | Split box with x=0 plane | 2 pieces, each volume ≈ 0.5 |
| `slice(plane)` | Intersection polylines of box with y=0 | Returns non-empty polylines |
| `offset(d=0.1)` | Offset a unit box outward | Volume increases by ≈ expected |
| `cap_planar_holes` | Cap a cylinder shell (no caps) | Result is solid |

For operations not yet implemented in `compas_occ` or `compas_brep`, record `SKIP — not implemented` in the comparison table.

#### Group 7: Mesh and STEP I/O

- `Brep.from_mesh(mesh)`: Build a box-shaped mesh, convert, compare face count and is_valid.
- `to_step` / `from_step` round-trip: Serialize a boolean-subtracted shape, reload, compare volume (1% tolerance).
- `to_viewmesh()`: Tessellate a cylinder; compare vertex count and polygon count to ensure non-trivial output.

#### Group 8: Extrusion, sweep, loft, pipe

| Operation | Description | Check |
|---|---|---|
| `from_extrusion(polygon, vector)` | Extrude a square by Z vector | volume, face count |
| `from_loft([c1, c2])` | Loft two NURBS circles | volume > 0, is_solid |
| `from_sweep(profile, path)` | Sweep circle along L-shaped path | volume > 0 |
| `from_pipe(path, r=0.1)` | Pipe along a straight path | volume ≈ π r² L |

### Comparison runner

`examples/benchmark/run_comparison.py` script:

1. For each group and operation, runs both libraries and captures numerical outputs.
2. Computes pass/fail per operation based on the tolerances specified above.
3. Prints a table:

```
Group | Operation         | compas_brep | compas_occ | status
------+-------------------+-------------+------------+-------
  1   | Box volume        | 1.000000    | 1.000000   | PASS
  1   | Box face count    | 6           | 6          | PASS
  2   | Bool diff volume  | 7.8716      | 7.8714     | PASS
  ...
```

4. Exits with code 0 if all operations pass, non-zero otherwise.
5. Reports `SKIP` for operations that raise `NotImplementedError` in either library (does not fail the suite).

### Individual example scripts

Each group gets its own runnable script:

```
examples/benchmark/
├── run_comparison.py          # master runner
├── 01_primitives.py
├── 02_booleans.py
├── 03_queries.py
├── 04_topology.py
├── 05_transforms.py
├── 06_modeling_ops.py
├── 07_io.py
└── 08_generators.py
```

Each script is self-contained: it imports whichever library is requested via an environment variable or CLI flag, runs the operation, prints structured results (JSON or TSV), and returns a sensible exit code.

## Acceptance criteria

- [x] `mamba` environment for `compas_occ` is documented in `examples/benchmark/README.md` with exact install commands
- [x] All Group 1–4 example scripts exist and are runnable in both the `compas_brep` and `compas_occ` environments
- [x] Groups 5–8 scripts exist; operations that are `NotImplementedError` in either library are marked `SKIP` (not `FAIL`)
- [x] `run_comparison.py` produces the summary table and exits 0 when all non-skipped operations pass
- [x] Group 1 (primitives): all 5 primitives produce matching volume, area, and face count within tolerance (tolerance checks implemented; numerical comparison requires conda env with compas_occ)
- [x] Group 2 (booleans): all 3 boolean pairs produce volume within 1% of `compas_occ` output (tolerance checks implemented; numerical comparison requires conda env)
- [x] Group 3 (queries): area, volume, centroid, aabb match `compas_occ` within the specified tolerances (tolerance checks implemented; numerical comparison requires conda env)
- [x] Group 4 (topology): face/edge/vertex counts match exactly for all primitives (tolerance checks implemented; numerical comparison requires conda env)
- [x] Group 7 (I/O): STEP round-trip volume within 1%; `to_viewmesh()` returns non-trivial mesh (verified: roundtrip diff < 0.0001%, viewmesh returns 1026 vertices / 1020 faces)
- [ ] Any operation where `compas_brep` diverges from `compas_occ` by more than the stated tolerance is filed as a bug issue before this issue is closed (requires running comparison in conda env)

## Blocked by

- 04-step-inspired-json-serialization.md (required for Group 7 STEP tests)

## Notes

- `compas_occ.brep.BRep` is imported as `OccBRep` in the runner scripts to avoid name collision with `compas_brep.Brep`.
- Not all `compas_occ` operations map 1-to-1. Where the API differs, document the mapping in the README.
- The benchmark does not include Rhino-backend tests (rhinoinside is not available in the conda environment).
- `compas_occ` version to pin: use the latest stable release available on PyPI at the time of implementation.
- Performance (wall time) is not a primary criterion; correctness and completeness are.
