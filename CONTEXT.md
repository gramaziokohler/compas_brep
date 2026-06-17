# compas_brep — Project Context

## Purpose

`compas_brep` is a unified, pip-installable wrapper around Rhino and OpenCASCADE (OCC) Brep implementations, built on top of the [COMPAS](https://github.com/compas-dev/compas) framework.

The project consolidates the compas Brep wrappers (previously split across `compas_rhino` and `compas_occ`) into a single coherent package with a stable public interface, matching the `compas.geometry.Brep` interface without inheriting from it.

---

## Glossary

**Brep**
The single public interface class. A thin wrapper holding a reference to a native backend object. Owns no geometry data itself. All properties and methods delegate to the backend via the COMPAS plugin system. All argument and return types are COMPAS types — never backend types.

**Backend**
A geometry kernel that owns and operates on the native Brep object. Selected automatically at runtime based on what is importable. Current backends: OCC, Rhino.

**Native object**
The backend-specific Brep representation (e.g. `TopoDS_Shape` for OCC, `Rhino.Geometry.Brep` for Rhino). The **source of truth** for all geometry and topology. Held by `Brep._native_brep`.

**Topology sub-object**
`BrepVertex`, `BrepEdge`, `BrepLoop`, `BrepFace`, `BrepTrim`. Native-handle wrappers — each holds a reference to its corresponding native entity. Properties (`.point`, `.curve`, `.surface`, etc.) call into native on demand and return COMPAS types. Results are lazily cached per-property to avoid repeated kernel calls.

**NurbsCurve / NurbsSurface**
Pure-Python value types storing control points, knots, and weights. Used as COMPAS-typed return values from topology sub-object properties. No backend delegation — they are data, not wrappers.

**Pluggable**
A `@pluggable`-decorated function in `compas_brep.operations`. Raises `NotImplementedError` by default. Each backend registers `@plugin` implementations gated by `requires=["OCP"]` or `requires=["Rhino"]`.

---

## Architecture

```
Brep  (public interface, compas.data.Data)
 └── _native_brep  →  TopoDS_Shape  (OCC)  |  Rhino.Geometry.Brep  (Rhino)

Brep.faces  →  list[BrepFace]  (native-handle wrappers, lazily populated, cached)
BrepFace.surface  →  NurbsSurface  (COMPAS value type, lazily extracted, cached)
```

- `Brep` delegates all operations to pluggables in `compas_brep.operations`.
- Topology lists (`_vertices`, `_edges`, `_loops`, `_faces`) are caches populated lazily on first access via `brep_extract_topology`.
- All inputs to and outputs from `Brep` methods are COMPAS types.

---

## Serialization

Format: STEP-inspired JSON. Encodes the same semantic entities as STEP (vertices, edges with curves, faces with surfaces, loops with trim curves) but as COMPAS/JSON, not STEP syntax.

- `Brep.__data__` asks the backend to extract geometry/topology entities and encodes them as JSON.
- `Brep.__from_data__` decodes the JSON and calls `brep_rebuild` (a pluggable) to reconstruct the native object. Requires a backend — no display-only fallback.
- `brep_rebuild` is only called from `__from_data__`. After it runs, the native object is source of truth.
- `Brep.to_step` / `Brep.from_step` are always available as the explicit file-level serialization path.

---

## Testing

- Tests require a backend at runtime. Without one, they are skipped via pytest marks.
- `@pytest.mark.occ` — requires OCC (`cadquery-ocp-novtk`). Runs on CI.
- `@pytest.mark.rhino` — requires `rhinoinside`. Runs locally on a dev machine with a Rhino license. Skipped on CI.
- No mock backend. Tests run against the real kernel.

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
