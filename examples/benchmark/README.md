# compas_brep vs compas_occ Benchmark Suite

Compares `compas_brep` (OCC backend) against `compas_occ` — the existing COMPAS wrapper for
OpenCASCADE — across eight operation groups. `compas_occ` is the established reference;
divergence beyond stated tolerances is a correctness regression.

## Environment setup

### compas_brep (dev environment)

```bash
pip install -e ".[occ]"
```

### compas_occ (conda environment — required for comparison)

`compas_occ` depends on `python-occ-core`, which is only available via conda:

```bash
mamba create -n compas_occ_bench python=3.11 -y
mamba activate compas_occ_bench
mamba install -c conda-forge python-occ-core -y
pip install compas compas_occ
```

Pin to the latest stable release of `compas_occ` available on PyPI at install time.

## Running the benchmark

Run a single group script against one backend:

```bash
# compas_brep backend (from your dev environment)
python examples/benchmark/01_primitives.py --backend compas_brep

# compas_occ backend (activate the conda env first)
mamba activate compas_occ_bench
python examples/benchmark/01_primitives.py --backend compas_occ
```

### Full comparison across two environments

Use `--occ-conda-env` to name the conda/mamba environment. The runner finds the mamba/conda
binary automatically (including when it is only available as a shell function, not on PATH):

```bash
python examples/benchmark/run_comparison.py \
    --occ-conda-env compas_occ_bench \
    --brep-python .venv/bin/python
```

`--brep-python` is needed when your `compas_brep` interpreter is not the `python` on your
PATH (e.g. when using a uv `.venv`).

`--occ-python` is also accepted as an alternative to `--occ-conda-env`, but calling a
conda env's Python binary directly (without activation) often fails to find conda-installed
shared libraries — prefer `--occ-conda-env`.

The runner exits with code 0 when all non-skipped operations pass. Three result codes are
used:

- `PASS` — values agree within the stated tolerance.
- `NOTE` — values differ due to a known API design difference (not a correctness bug). Rows
  marked `NOTE` do not affect the exit code. Currently applies to edge/vertex counts
  (compas_occ counts oriented per-face entities; compas_brep counts unique geometric
  entities) and `from_loft is_solid` (compas_brep caps automatically; compas_occ does not).
- `SKIP` — operation not available in one or both backends.

## Operation groups

| Script | Group | Operations |
|--------|-------|------------|
| `01_primitives.py` | 1 | Box, Cylinder, Sphere, Cone, Torus |
| `02_booleans.py` | 2 | Difference, Union, Intersection |
| `03_queries.py` | 3 | area, volume, centroid, aabb, is_solid, is_valid |
| `04_topology.py` | 4 | face/edge/vertex counts, sub-object COMPAS types |
| `05_transforms.py` | 5 | translate, rotate, transformed copy |
| `06_modeling_ops.py` | 6 | fillet, trimmed, split, slice, offset, cap_planar_holes |
| `07_io.py` | 7 | from_mesh, STEP round-trip, to_viewmesh |
| `08_generators.py` | 8 | from_extrusion, from_loft, from_sweep, from_pipe |

## Tolerances

| Metric | Tolerance |
|--------|-----------|
| volume, area (primitives) | 0.1% relative |
| volume (booleans, STEP) | 1% relative |
| face/edge/vertex counts | exact |
| is_solid, is_valid | exact bool |
| centroid components | 1e-6 absolute |
| aabb dimensions | 1e-6 absolute |

## API mapping

`compas_occ.brep.BRep` is imported as `OccBRep` in the runner to avoid name collision with
`compas_brep.Brep`. The two APIs are structurally equivalent; differences in constructor
names or missing operations are documented inline in each script.

## Notes

- Rhino backend tests are not included (rhinoinside not available in the conda environment).
- Performance (wall time) is not a criterion; correctness and completeness are.
- Scripts that raise `NotImplementedError` or `AttributeError` for an operation mark that
  operation as `SKIP`, which does not fail the suite.
