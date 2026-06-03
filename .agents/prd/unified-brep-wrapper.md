# PRD: Unified Brep Wrapper

## Problem Statement

COMPAS users working with Boundary Representation (Brep) geometry face a fragmented experience today. Brep support is split across `compas_rhino` and `compas_occ` — separate packages with overlapping but inconsistent interfaces, non-trivial installation, and no single entry point. Switching between environments (e.g. from a Rhino workflow to a headless OCC pipeline) requires code changes. The packages are hard to maintain because the same operation must be updated in multiple places, and the architecture couples geometry ownership to the backend, making the code difficult to reason about, test, and extend.

## Solution

A single pip-installable package (`compas_brep`) that exposes one stable `Brep` interface regardless of the underlying geometry kernel. The correct backend (OCC or Rhino) is selected automatically at runtime. User code never branches on the environment. The `Brep` class is a thin wrapper: it holds a reference to a native backend object (the source of truth) and delegates all operations to it via the COMPAS plugin system. All inputs and outputs are COMPAS types — backend types never leak through the interface. Topology sub-objects (`BrepFace`, `BrepEdge`, etc.) are native-handle wrappers with lazily cached COMPAS-typed properties.

## User Stories

1. As a COMPAS user, I want to install Brep support with `pip install compas_brep[occ]`, so that I don't need to manually configure plugins or install multiple packages.
2. As a COMPAS user, I want to write `from compas_brep import Brep` and have it work in both Rhino and a headless OCC environment without changing my code, so that my scripts are portable.
3. As a COMPAS user, I want to create a Brep from COMPAS primitives (`Box`, `Cylinder`, `Sphere`, etc.), so that I can start modeling without understanding backend details.
4. As a COMPAS user, I want to run boolean operations (`+`, `-`, `&`) on Breps using Python operators, so that I can compose geometry naturally.
5. As a COMPAS user, I want `brep.faces`, `brep.edges`, `brep.vertices` to return COMPAS-typed objects, so that I can inspect topology without importing backend modules.
6. As a COMPAS user, I want `face.surface` to return a `NurbsSurface`, `edge.curve` to return a `NurbsCurve`, and `vertex.point` to return a `Point`, so that geometry is always in COMPAS terms.
7. As a COMPAS user, I want to serialize a Brep to JSON using COMPAS's standard `Data` protocol, so that I can store and exchange Brep data using existing COMPAS tooling.
8. As a COMPAS user, I want to deserialize a Brep from JSON and have it fully operational (booleans, tessellation, queries), so that I can round-trip Breps through files or network without loss of capability.
9. As a COMPAS user, I want to export a Brep to STEP with `brep.to_step(path)` and import with `Brep.from_step(path)`, so that I can exchange geometry with CAD tools.
10. As a COMPAS user, I want `brep.area`, `brep.volume`, `brep.centroid`, and `brep.aabb` to return correct values, so that I can use Breps in analysis workflows.
11. As a COMPAS user, I want to tessellate a Brep to a `Mesh` with `brep.to_viewmesh()`, so that I can visualize it in `compas_viewer` or export to mesh-based formats.
12. As a COMPAS user, I want to transform a Brep in-place with `brep.transform(T)` or get a transformed copy with `brep.transformed(T)`, so that I can position geometry in a scene.
13. As a COMPAS user, I want to trim, slice, split, fillet, offset, and heal Breps, so that I have the modeling operations I need for architectural and engineering tasks.
14. As a COMPAS user, I want to check `brep.is_solid`, `brep.is_valid`, `brep.is_shell`, etc., so that I can validate geometry before passing it downstream.
15. As a COMPAS user in Rhino, I want the same `Brep` interface to delegate to `Rhino.Geometry`, so that I get native Rhino performance and compatibility without a separate API.
16. As a COMPAS user with OCC installed, I want the same `Brep` interface to delegate to OCC (`cadquery-ocp-novtk`), so that I can run headless on a server or in CI.
17. As a COMPAS user, I want to create a Brep from a native backend object (`Brep.from_native(obj)`), so that I can bridge from existing backend-specific code.
18. As a COMPAS user, I want to loft, sweep, and pipe Breps, so that I can create complex geometry programmatically.
19. As a developer, I want to add a new Brep operation by implementing one pluggable per backend and exposing it once on `Brep`, so that the maintenance cost of new features is low and predictable.
20. As a developer, I want to run the full test suite with `pytest` after installing `compas_brep[occ]`, so that I can verify correctness locally and in CI.
21. As a developer, I want Rhino backend tests to be skipped automatically when `rhinoinside` is not available, so that the test suite runs cleanly in any environment.
22. As a developer, I want CI to run OCC tests on every push via GitHub Actions, so that regressions are caught before merging.
23. As a developer, I want to run Rhino backend tests locally with `pytest -m rhino` when `rhinoinside` is installed, so that I can verify Rhino parity without a separate test harness.

## Implementation Decisions

### Native object as source of truth
`Brep._native_brep` holds the backend-specific object (`TopoDS_Shape` for OCC, `Rhino.Geometry.Brep` for Rhino). This is the source of truth for all geometry and topology. `Brep` itself owns no geometry data.

### Thin delegation via COMPAS plugin system
All operations are declared as `@pluggable` functions in `compas_brep.operations`. Each backend registers `@plugin` implementations gated by `requires=["OCP"]` or `requires=["Rhino"]`. Plugin discovery is via `__all_plugins__` in `compas_brep.__init__`. No backend types escape through the interface — all arguments and return values are COMPAS types.

### Topology sub-objects as native-handle wrappers
`BrepVertex`, `BrepEdge`, `BrepLoop`, `BrepFace`, `BrepTrim` each hold a reference to a native entity. Properties (`.point`, `.curve`, `.surface`, etc.) call into native on demand and return COMPAS types. Results are cached per-property instance to avoid repeated kernel calls. Topology lists on `Brep` (`_vertices`, `_edges`, `_loops`, `_faces`) are populated lazily on first access via the `brep_extract_topology` pluggable.

### NurbsCurve and NurbsSurface as pure-Python value types
These are COMPAS-typed data objects (control points, knots, weights). They are used as return values from topology sub-object properties. They do not delegate to a backend. Backend conversion functions (in `backend/occ/conversion.py` etc.) translate between native curve/surface types and these value types at the boundary.

### Serialization: STEP-inspired JSON
`Brep.__data__` encodes geometry and topology as JSON using STEP's semantic model as a guide — the same entity types (vertices, edges with associated curves, faces with associated surfaces, loops, trim curves) but expressed as COMPAS/JSON rather than STEP syntax. `Brep.__from_data__` decodes this JSON and calls `brep_rebuild` (a pluggable) to reconstruct the native object. A backend is required for both serialization and deserialization. `brep_rebuild` is only invoked from `__from_data__`.

### Explicit file I/O via to_step / from_step
`brep.to_step(path)` and `Brep.from_step(path)` are always available as the explicit file-level exchange format. These are distinct from COMPAS `Data` serialization.

### Backend selection
Automatic at runtime via the COMPAS plugin system. OCC is active when `OCP` is importable. Rhino is active when `Rhino` is importable (via `rhinoinside` or when running inside Rhino). No user code branching required.

### pyproject.toml structure
Core package depends only on `compas>=2.0`. OCC support is an optional extra: `pip install compas_brep[occ]` adds `cadquery-ocp-novtk`. Rhino support comes via `rhinoinside` installed separately.

## Testing Decisions

### What makes a good test
Tests verify observable behavior of the `Brep` public interface — geometry correctness (volumes, face counts, topology queries), operation outcomes (booleans reduce volume correctly), and round-trip integrity (serialize → deserialize → same geometry). Tests do not assert on internal state (`_native_brep`, cache fields, plugin dispatch internals).

### Backend requirement and skip markers
All tests require a live backend. `@pytest.mark.occ` tests are skipped if `OCP` is not importable. `@pytest.mark.rhino` tests are skipped if `rhinoinside` is not importable. A `conftest.py` registers these marks and applies the skip condition automatically.

### OCC test suite (CI)
Covers all public `Brep` constructors, properties, topology queries, operations, boolean operators, serialization round-trips, and file I/O. Runs on GitHub Actions with `cadquery-ocp-novtk` installed. The existing `tests/test_brep_api.py`, `test_boolean.py`, `test_serialization.py`, and `test_new_constructors.py` are the prior art; they will be updated to carry `@pytest.mark.occ` and updated to test against the new native-handle wrapper behavior.

### Rhino test suite (local only)
Mirrors the OCC test suite in scope. Runs locally on a developer machine with `rhinoinside` installed. Marked `@pytest.mark.rhino`. Not run in CI. Tests confirm that the Rhino backend produces geometrically equivalent results to OCC for the same operations.

### Topology sub-object tests
Verify that properties on `BrepFace`, `BrepEdge`, `BrepVertex` return the correct COMPAS types and that repeated access returns cached values (checked via identity, not timing).

## Out of Scope

- Pure-Python Brep implementation or geometry kernel.
- Support for backends other than OCC and Rhino.
- Display-only deserialization (loading a Brep without a backend installed).
- Tessellation cache embedded in serialized JSON.
- Rhino Compute integration.
- `NurbsCurve` and `NurbsSurface` backend delegation.
- Documentation site, API reference, or developer guide.
- Performance benchmarking against `compas_occ`.

## Further Notes

- The project previously attempted a pure-Python CSG/Brep engine (BSP-tree booleans, scipy NURBS). That work is abandoned. The `NurbsCurve` and `NurbsSurface` pure-Python classes are retained as value types but the CSG machinery is gone.
- The v3 JSON serialization format (Python-owned topology) currently in the codebase will be replaced by the STEP-inspired format. No backward compatibility is required.
- `Brep` matches the `compas.geometry.Brep` interface by convention but does not inherit from it (deliberate decision from early in the project).
- Rhino backend testing via `rhinoinside` is the recommended local path. Rhino Compute is a possible future CI path if Rhino coverage becomes a priority.
