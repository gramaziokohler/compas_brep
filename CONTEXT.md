# compas_brep — Project Context

## Purpose

`compas_brep` is a unified, pip-installable wrapper around Rhino and OpenCASCADE (OCC) Brep implementations, built on top of the [COMPAS](https://github.com/compas-dev/compas) framework.

The project consolidates the compas Brep wrappers (previously split across `compas_rhino` and `compas_occ`) into a single coherent package with a stable public interface, matching the `compas.geometry.Brep` interface without inheriting from it.

---

## Glossary

**Brep**
The single public interface class. A thin wrapper holding a reference to a native backend object. Owns no geometry data itself. All properties and methods delegate to the backend via the COMPAS plugin system. All argument and return types are COMPAS types — never backend types. Inherits `compas.geometry.Geometry` (not `compas.data.Data` directly) for `translate`/`scale`/`rotate`/`transform` and their `-ed` copy-returning counterparts — see [design doc](.agents/prd/inherit-compas-geometry-geometry.md). This is unrelated to the "matching the `compas.geometry.Brep` interface without inheriting from it" decision below: `compas.geometry.Geometry` is the lightweight generic base; `compas.geometry.Brep` is the heavier class (with its own plugin dispatch) that is still avoided.

**Backend**
A geometry kernel that owns and operates on the native Brep object. Selected automatically at runtime based on what is importable. Current backends: OCC, Rhino.

**Native object**
The backend-specific Brep representation (e.g. `TopoDS_Shape` for OCC, `Rhino.Geometry.Brep` for Rhino). The **source of truth** for all geometry and topology. Held by `Brep._native_brep`.

**Topology sub-object**
`BrepVertex`, `BrepEdge`, `BrepLoop`, `BrepFace`, `BrepTrim`. Native-handle wrappers — each holds a reference to its corresponding native entity. Properties (`.point`, `.curve`, `.surface`, etc.) call into native on demand and return COMPAS types. Results are lazily cached per-property to avoid repeated kernel calls.

**NurbsCurve / NurbsSurface**
Pure-Python value types storing control points, knots, and weights. Used as COMPAS-typed return values from topology sub-object properties. No backend delegation — they are data, not wrappers. Like `Brep`, inherit `compas.geometry.Geometry` for `translate`/`scale`/`rotate`/`transform` (see [design doc](.agents/prd/inherit-compas-geometry-geometry.md)).

**Pluggable**
A `@pluggable`-decorated function in `compas_brep.operations`. Raises `NotImplementedError` by default. Each backend registers `@plugin` implementations gated by `requires=["OCP"]` or `requires=["Rhino"]`.

---

## Architecture

```
Brep  (public interface, compas.data.Data)
 └── _native_brep  →  TopoDS_Shape  (OCC)  |  Rhino.Geometry.Brep  (Rhino)

Brep.faces  →  list[BrepFace]  (native-handle wrappers, lazily populated, cached)
BrepFace.surface  →  Plane | CylindricalSurface | ConicalSurface | SphericalSurface | ToroidalSurface | NurbsSurface
```

- `Brep` delegates all operations to pluggables in `compas_brep.operations`.
- Topology lists (`_vertices`, `_edges`, `_loops`, `_faces`) are caches populated lazily on first access via `brep_extract_topology`.
- All inputs to and outputs from `Brep` methods are COMPAS types.

---

## Surface Type Support

OCC has eleven surface types (`GeomAbs`). The table below records what compas_brep can do with each:

| OCC surface type | `face.surface` COMPAS type | Tessellation / viz | JSON serialize | JSON deserialize |
|---|---|---|---|---|
| Plane | `Plane` (exact) | ✓ | ✓ | ✓ |
| Cylinder | `CylindricalSurface` (exact) | ✓ | ✓ | ✓ |
| Cone | `ConicalSurface` (exact) | ✓ | ✓ | ✓ |
| Sphere | `SphericalSurface` (exact) | ✓ | ✓ | ✓ |
| Torus | `ToroidalSurface` (exact) | ✓ | ✓ | ✓ |
| Bezier | `NurbsSurface` (exact, rational) | ✓ | ✓ | ✓ |
| BSpline / NURBS | `NurbsSurface` (exact) | ✓ | ✓ | ✓ |
| Surface of Revolution | `NurbsSurface` (approx) | ✓ | ✓ | ✓ |
| Surface of Extrusion | `NurbsSurface` (approx) | ✓ | ✓ | ✓ |
| Offset Surface | `NurbsSurface` (approx) | ✓ | ✓ | ✓ |
| Other | `NurbsSurface` (approx) | ✓ | ✓ | ✓ |

**Why tessellation always works:** `to_viewmesh()` / `to_tesselation()` call `BRepMesh_IncrementalMesh` on the **native OCC shape** directly — they never touch `face.surface`. The same is true for boolean operations and `to_step()`. The COMPAS-type extraction in `face.surface` is a separate, lossy layer on top.

**Analytic surfaces are exact:** Cylinder, Cone, Sphere, and Torus faces return the matching COMPAS analytic surface type (`CylindricalSurface`, `ConicalSurface`, `SphericalSurface`, `ToroidalSurface`) with correct geometric parameters (radius, frame, etc.) extracted directly from the OCC adaptor. These types expose the same `point_at(u, v)`, `space_u(n)`, `space_v(n)` interface as `NurbsSurface`, so visualization, inspection, and round-tripping all work natively. `BrepFace` exposes `surface_type` (string) and `is_cylinder` / `is_cone` / `is_sphere` / `is_torus` predicates.

**Remaining NURBS approximations:** Surface of Revolution, Surface of Extrusion, Offset (fillet/chamfer), and Other surface types do not have a matching COMPAS analytic type. They are converted to `NurbsSurface` via `GeomConvert::SurfaceToBSplineSurface`. If that conversion fails, `_extract_surface` raises `BrepError` rather than returning silent dummy geometry.

**Implementation:** `_extract_surface()` in `src/compas_brep/backend/occ/conversion.py`. Codec in `src/compas_brep/surfaces/_codec.py`. `BrepFace` API in `src/compas_brep/face.py`.

---

## Serialization

Format: STEP-inspired JSON. Encodes the same semantic entities as STEP (vertices, edges with curves, faces with surfaces, loops with trim curves) but as COMPAS/JSON, not STEP syntax.

- `Brep.__data__` asks the backend to extract geometry/topology entities and encodes them as JSON.
- `Brep.__from_data__` decodes the JSON and calls `brep_rebuild` (a pluggable) to reconstruct the native object. Requires a backend — no display-only fallback.
- `brep_rebuild` is only called from `__from_data__`. After it runs, the native object is source of truth.
- `Brep.to_step` / `Brep.from_step` are always available as the explicit file-level serialization path.

**Version history:**

- **v4** (legacy): only `"plane"` and `"nurbs"` surface types. Cylinder/Cone/Sphere/Torus were serialized as `"nurbs"` (NURBS approximation).
- **v5** (current): adds `"cylinder"`, `"cone"`, `"sphere"`, and `"torus"` surface type tags. Each uses the COMPAS analytic type's native `__data__`/`__from_data__` round-trip. The surface codec (`surfaces/_codec.py`) reads both v4 and v5 documents transparently — v4 files still deserialize correctly.

**Cone parameterization note:** OCC's `gp_Cone` is parameterized by `(Position, RefRadius, SemiAngle)`, where `RefRadius` is the base radius at the location origin and `SemiAngle` is the half-opening angle. COMPAS's `ConicalSurface` uses `(radius, height, frame)`. The conversion is `height = -RefRadius / tan(SemiAngle)` (negative SemiAngle for a tapering cone). The v5 JSON stores the COMPAS `radius` and `height` directly; the OCC SemiAngle is not preserved in the serialized form.

---

## Testing

- Most tests require a backend at runtime. Without one, they are skipped via pytest marks. A minority of tests (e.g. `NurbsCurve`/`NurbsSurface`, which are pure Python) need no backend and carry no marker.
- `@pytest.mark.occ` — requires OCC (`cadquery-ocp-novtk`). Runs on CI.
- `@pytest.mark.rhino` — requires `rhinoinside`. Runs locally on a dev machine with a Rhino license. Skipped on CI (and by default locally — `addopts = "-m 'not rhino'"` in `pyproject.toml`).
- No mock backend. Backend-dependent tests run against the real kernel.
- No test classes. Tests are flat module-level `test_*` functions, not methods on `TestXxx` classes — grouping is expressed with `# =====` section-header comments and a `test_<group>_<name>` naming prefix (e.g. `test_constructors_from_box`), not nesting.

**Before running tests, install the OCC backend:**

```bash
uv pip install "cadquery-ocp-novtk>=7.8"
```

Then run the full OCC test suite:

```bash
pytest -m occ -q
```

All 110+ OCC tests must pass before committing. Do not rely on CI as the only test gate — run locally first.

---

## Rhino Development Workflow

Grasshopper/Rhino is accessible via the **lamcp MCP server** (tools prefixed `mcp__lamcp__`).

After modifying library code, reinstall into the Rhino venv and reload:

```bash
~/.rhinocode/py39-rh8/python3.9 -m pip install . \
  --target ~/.rhinocode/py39-rh8/site-envs/compas_brep_occ-7LvK83j1 \
  --force-reinstall --no-deps --upgrade
```

Then, via the LAMCP bridge, delete stale bytecode and clear the module cache:

```python
import os, sys, shutil

pycache = os.path.expanduser(
    "~/.rhinocode/py39-rh8/site-envs/compas_brep_occ-7LvK83j1/compas_brep"
)
for root, dirs, files in os.walk(pycache):
    if '__pycache__' in dirs:
        shutil.rmtree(os.path.join(root, '__pycache__'))
for k in list(sys.modules):
    if 'compas_brep' in k:
        del sys.modules[k]
```

Then call `mcp__lamcp__solve_grasshopper(expire_all=True)` to recompute all GH components.

**Why both steps are needed**: GH script components run in isolated Python environments that do not share `sys.modules` with the LAMCP bridge. Deleting `__pycache__` forces every environment to recompile from the updated `.py` files on the next import.

The Rhino-side virtual environment is named `compas_brep_occ`.

---

## Backends

| Backend | Module | Activated when |
|---------|--------|----------------|
| OCC | `compas_brep.backend.occ` | `OCP` importable (`cadquery-ocp-novtk`) |
| Rhino | `compas_brep.backend.rhino` | `Rhino` importable (`rhinoinside` or inside Rhino) |

Plugin discovery: `__all_plugins__` in `compas_brep.__init__` lists both backend plugin modules. COMPAS's plugin system loads them conditionally based on `requires`.

---

## Type Annotations

All Python source files use Python 3.9-compatible type annotations.

**Every file must start with:**

```python
from __future__ import annotations
```

This makes all annotations lazy strings at runtime, enabling Python 3.10+ syntax (`X | Y`, `list[X]`, `tuple[X, Y]`) to work safely on Python 3.9 (the Rhino venv).

**Rules:**

1. **Built-in generics** — use `list[X]`, `dict[K, V]`, `tuple[X, Y]`, not `List`, `Dict`, `Tuple` from `typing`.
2. **Unions** — use `X | Y`, not `Union[X, Y]`. Use `X | None`, not `Optional[X]`.
3. **Runtime-unavailable types** — import under `TYPE_CHECKING`:
   ```python
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from compas_brep.brep import Brep          # avoids circular import
       from OCP.TopoDS import TopoDS_Shape        # avoids OCC import at module level
   ```
4. **Docstrings** — do **not** include types in `Parameters` or `Returns` sections. The signature is the authoritative source. Write:
   ```
   Parameters
   ----------
   filepath
       Path to the STEP file.
   ```
   not `filepath : str`.  If a `Returns` section has only a type name and no description, remove the section entirely.
5. **`Any`** — use sparingly for backend-specific native objects (`TopoDS_Shape`, `Rhino.Geometry.Brep`) when typing through `TYPE_CHECKING` is impractical.

---

## Import Style Rules

These rules are enforced by ruff (`isort.force-single-line = true`) and must be followed in all source and test files.

1. **One name per import line.** Never `from X import A, B`. Always:
   ```python
   from X import A
   from X import B
   ```

2. **No multi-line parenthesized imports.** Every import must fit on a single line.

3. **At most 2nd-level depth for `compas_brep` imports.** The module path after `compas_brep` may have at most one component:
   - ✓ `from compas_brep.curves import NurbsCurve`
   - ✗ `from compas_brep.curves.nurbs import NurbsCurve`
   - ✗ `from compas_brep.backend.occ.topology import OccBrepEdge`
   - If a name is only defined deeper, re-export it from the nearest 2nd-level `__init__.py`.

4. **Internal cross-file imports use relative imports.** Files within `backend/occ/`, `backend/rhino/` etc. use `from .sibling import X`, not absolute `from compas_brep.backend.occ.sibling import X`.

5. **Prefer module-level imports.** Only use function-level imports when there is an unavoidable circular dependency or a conditional availability that cannot be handled with try/except at module level.

---

## Key Files

- `src/compas_brep/brep.py` — public `Brep` interface
- `src/compas_brep/operations.py` — all `@pluggable` declarations
- `src/compas_brep/vertex.py`, `edge.py`, `loop.py`, `face.py`, `trim.py` — topology sub-objects (native-handle wrappers)
- `src/compas_brep/curves/nurbs.py`, `surfaces/nurbs.py` — pure-Python COMPAS value types
- `src/compas_brep/backend/occ/` — OCC backend implementation
- `src/compas_brep/backend/rhino/` — Rhino backend implementation
- `src/compas_brep/scene/__init__.py` — one `@plugin(requires=...)` per context; no top-level context imports
- `src/compas_brep/scene/viewer/` — `compas_viewer` scene objects (`BrepObject`, `NurbsCurveObject`, `NurbsSurfaceObject`)
- `src/compas_brep/scene/rhino/` — Rhino scene objects (`RhinoBrepObject`, `RhinoNurbsCurveObject`, `RhinoNurbsSurfaceObject`); bakes geometry into `scriptcontext.doc`
