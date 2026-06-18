# Plan: Accurate Surface Type Support

Status: proposed
Owner: compas_brep
Related: [CONTEXT.md](../CONTEXT.md) §"Surface Type Support"

## Goal

Make `face.surface` return the most accurate COMPAS type for each OCC surface,
instead of collapsing analytic surfaces to a NURBS approximation (and instead of
the wrong `Plane(0,0,0)` fallback for offset/unknown surfaces). The extracted
COMPAS surfaces must be:

1. **Inspectable** — `face.surface` is a real `CylindricalSurface`,
   `SphericalSurface`, etc., with correct `radius` / `frame` / etc.
2. **Visualizable** — viewer and Rhino scene objects can draw them.
3. **Round-trippable** — JSON serialize/deserialize preserves the type, and
   `brep_rebuild` reconstructs a native OCC face from it.

This work is the COMPAS-type extraction layer only. Native-shape operations
(`to_viewmesh`, booleans, `to_step`) already work for every surface type because
they operate on `_native_brep` directly — they are out of scope and must not
regress.

## Background — what exists today

- `_extract_surface()` in [conversion.py](../src/compas_brep/backend/occ/conversion.py#L304)
  dispatches on `BRepAdaptor_Surface.GetType()`. Only `GeomAbs_Plane` is exact;
  everything else goes through `Geom_RectangularTrimmedSurface` →
  `GeomConvert::SurfaceToBSplineSurface` → `NurbsSurface`. On failure it returns
  `Plane(Point(0,0,0), Vector(0,0,1))` — the broken case for offset/unknown surfaces.
- Serialization tags surfaces with a `"type"` string that is only ever
  `"plane"` or `"nurbs"`, in three places that each duplicate the logic:
  - serialize: [face.py `__data__`](../src/compas_brep/face.py#L123),
    [occ conversion `occ_brep_to_data`](../src/compas_brep/backend/occ/conversion.py#L559),
    [rhino conversion](../src/compas_brep/backend/rhino/conversion.py#L633)
  - deserialize: [occ `occ_rebuild`](../src/compas_brep/backend/occ/operations.py#L366),
    [rhino operations](../src/compas_brep/backend/rhino/operations.py#L333)
- `brep_to_occ` ([conversion.py](../src/compas_brep/backend/occ/conversion.py#L620))
  rebuilds native faces only for `Plane` and `NurbsSurface`; any other type hits
  the `else: continue` and the face is silently dropped.
- `BrepFace.surface` is typed `Plane | NurbsSurface`; `is_planar` / `is_nurbs`
  are the only type predicates.
- The viewer `NurbsSurfaceObject`
  ([surfaceobject.py](../src/compas_brep/scene/viewer/surfaceobject.py)) tessellates
  via `surface.space_u()/space_v()/point_at()`.

## Key facts that make this tractable

- COMPAS 2.15 ships analytic surface types with a uniform interface:
  `PlanarSurface`, `CylindricalSurface(radius, frame)`,
  `ConicalSurface(radius, height, frame)`, `SphericalSurface(radius, frame)`,
  `ToroidalSurface(radius_axis, radius_pipe, frame)`. Each is a `compas.data.Data`
  with `__data__` round-trip, and each exposes the **same** `point_at(u,v)`,
  `space_u(n)`, `space_v(n)`, `domain_u`, `domain_v` interface that our
  `NurbsSurface` and the viewer tessellator already rely on. They also provide
  `to_brep()`.
- OCC adaptors give exact parameters:
  `adaptor.Cylinder()` → `gp_Cylinder` (`.Position()` gp_Ax3, `.Radius()`);
  `adaptor.Cone()` → `gp_Cone` (`.Position()`, `.RefRadius()`, `.SemiAngle()`, `.Apex()`);
  `adaptor.Sphere()` → `gp_Sphere` (`.Position()`, `.Radius()`);
  `adaptor.Torus()` → `gp_Torus` (`.Position()`, `.MajorRadius()`, `.MinorRadius()`).
  `gp_Ax3.Location()/XDirection()/YDirection()` → a COMPAS `Frame`.
- This mirrors `compas_occ/conversions/geometry.py`
  (`cylinder_to_compas`, `sphere_to_compas`, `ax3_to_compas`, …). We follow the
  same parameter extraction, but return COMPAS **surface** types (infinite,
  frame-based) rather than the bounded solids `Cylinder`/`Cone`/`Sphere`/`Torus`,
  because a Brep face is a trimmed patch — the trim extent already lives on the
  loops and `BrepFace.domain_u/domain_v`.

## Type mapping (target state)

| OCC `GeomAbs` | `face.surface` COMPAS type | Notes |
|---|---|---|
| Plane | `Plane` (unchanged) | exact, already correct |
| Cylinder | `CylindricalSurface` | `radius`, `frame` from `gp_Cylinder` |
| Cone | `ConicalSurface` | needs semi-angle→(radius,height) mapping; see below |
| Sphere | `SphericalSurface` | `radius`, `frame` from `gp_Sphere` |
| Torus | `ToroidalSurface` | `radius_axis`=Major, `radius_pipe`=Minor |
| Bezier | `NurbsSurface` (unchanged) | exact rational |
| BSpline / NURBS | `NurbsSurface` (unchanged) | exact |
| SurfaceOfRevolution | `NurbsSurface` (approx) | no exact COMPAS type; keep approx, document |
| SurfaceOfExtrusion | `NurbsSurface` (approx) | as above |
| OffsetSurface | `NurbsSurface` (approx) | **fix**: robust NURBS fallback, never `Plane(0,0,0)` |
| Other | `NurbsSurface` (approx) | **fix**: same |

The two ⚠️ broken rows in CONTEXT.md get fixed by making the failure path return
a proper NURBS approximation (the GeomConvert path already succeeds for offset
surfaces in practice) and removing the dummy `Plane(0,0,0)` entirely. If
GeomConvert genuinely fails, raise/log rather than emit silently-wrong geometry.

### Cone mapping caveat

`ConicalSurface(radius, height, frame)` is parameterized differently from OCC's
`gp_Cone(Position, RefRadius, SemiAngle)`. `RefRadius` is the radius in the
reference plane (frame origin); `SemiAngle` is the half-opening angle. COMPAS
derives the half-angle from `radius`/`height` (`atan(radius/height)`) about the
apex. The conversion must produce a COMPAS cone whose surface coincides with the
OCC cone over the face's V-range — do **not** assume the formula is obvious.
Implement it, then assert agreement by sampling `point_at` against the native
surface at several (u,v) in the face domain (see tests). This is the one mapping
that needs an empirical round-trip check, not just a field copy.

## Implementation steps

### 1. Centralize the surface codec (no behavior change yet)

Create one shared encode/decode pair so the three serialize sites and two
deserialize sites stop duplicating the `"type"` dispatch.

- Add `surface_to_data(surface) -> dict` and `surface_from_data(data) -> surface`
  in a backend-neutral module — `src/compas_brep/surfaces/__init__.py` (re-export)
  backed by `surfaces/_codec.py`. Respect the import-depth rule (re-export from the
  2nd-level `__init__`).
- Encoding: `{"type": <tag>, "data": <surface.__data__>}` where tag ∈
  `{"plane", "planar", "cylinder", "cone", "sphere", "torus", "nurbs"}`. Plane
  keeps its existing hand-rolled `{"point","normal"}` payload for backward
  compatibility (don't break v4 files); analytic types use the COMPAS
  `__data__`/`__from_data__` round-trip directly.
- Bump the serialization `"version"` to 5 in `occ_brep_to_data` /
  rhino equivalent. `surface_from_data` must still read v4 (`plane`/`nurbs` only).
- Replace the inline blocks in `face.py`, `occ/conversion.py`, `rhino/conversion.py`
  (serialize) and `occ/operations.py`, `rhino/operations.py` (deserialize) with
  calls to the shared codec. Run the existing suite — pure refactor, all green.

### 2. Extract analytic surfaces (OCC → COMPAS)

In `_extract_surface()`:

- Add branches for `GeomAbs_Cylinder/Cone/Sphere/Torus` that build the COMPAS
  analytic type from the adaptor. Add a `_ax3_to_frame(gp_Ax3) -> Frame` helper
  (mirrors `ax3_to_compas`).
- Rework the fallback: keep the `GeomConvert` → `NurbsSurface` path for
  Bezier/BSpline/Revolution/Extrusion/Offset/Other. On GeomConvert failure, do
  **not** return `Plane(0,0,0)`; surface extraction should raise a clear error (or
  return `None` and let the caller skip), so a wrong dummy never enters a Brep.
- Update the return annotation to the surface union and add a small
  `_SURFACE_UNION` alias used across files.

### 3. Widen `BrepFace` and topology wrappers

- `face.py`: widen `surface` type to the union; add predicates
  `is_cylinder`/`is_cone`/`is_sphere`/`is_torus` and a `surface_type` string
  property. Keep `is_planar`/`is_nurbs`. Fix `__repr__` to report the real type.
- `occ/topology.py` and `rhino/topology.py`: same `__repr__` / predicate updates.
- `_compute_plane()` default stays for faces built without a surface.

### 4. Rebuild analytic surfaces (COMPAS → OCC)

In `brep_to_occ` / `_build_nurbs_face`:

- Add `_analytic_surface_to_occ(surface) -> Geom_Surface` mapping each COMPAS
  analytic type to `Geom_CylindricalSurface`/`Geom_ConicalSurface`/
  `Geom_SphericalSurface`/`Geom_ToroidalSurface` (via the `gp_*` primitives from
  the frame + radii).
- Generalize the `isinstance(surface, NurbsSurface)` branch in `brep_to_occ` to
  "any non-Plane surface": build the `Geom_Surface`, then reuse the existing
  pcurve-based `_build_*_face` path (it already takes a generic `occ_surface` and
  attaches pcurves — periodic cylinders/spheres/tori specifically need those
  pcurves, which we already extract). Rename `_build_nurbs_face` →
  `_build_trimmed_face` to reflect it is surface-type agnostic.
- Remove the silent `else: continue` so an unconvertible surface is loud.

### 5. Visualization / inspection

- Viewer: the analytic COMPAS surfaces share `space_u/space_v/point_at`, so add a
  single generic `AnalyticSurfaceObject` (factor the tessellation out of
  `NurbsSurfaceObject` into a shared helper) and register it for
  `CylindricalSurface`, `ConicalSurface`, `SphericalSurface`, `ToroidalSurface`,
  `PlanarSurface` in `scene/viewer/__init__.py` / the `@plugin` block.
- Rhino: register the analytic types in `scene/rhino/__init__.py`. Prefer baking
  via the COMPAS surface's `to_brep()`/native conversion if available; otherwise
  bake the tessellated mesh, matching the existing `RhinoNurbsSurfaceObject`.
- `BrepObject` already draws faces via the native shape, so whole-Brep viz is
  unaffected; this step is about drawing an individually inspected `face.surface`.

### 6. Docs, tests, examples

See sections below. Update CONTEXT.md last, once behavior is real.

## Testing (`pytest -m occ`, run locally before commit)

New file `tests/test_surface_types.py`, parametrized over primitives built with
`BRepPrimAPI_MakeCylinder/MakeCone/MakeSphere/MakeTorus` (and a fillet for the
offset-surface case):

1. **Type extraction** — for each primitive, find the analytic face and assert
   `face.surface` is the expected COMPAS type with correct `radius` / radii /
   frame origin+axes (within `TOL`).
2. **Geometric fidelity** — sample `face.surface.point_at(u,v)` over the face
   domain and compare to the native surface evaluated at the same (u,v)
   (`BRep_Tool.Surface_s` + `Value`). This is the real check for the **cone**
   mapping. Tolerance tight (1e-6).
3. **JSON round-trip** — `json_loads(json_dumps(brep))` preserves the surface
   type and parameters; the rebuilt Brep has the same face count and is valid
   (`BRepCheck`). Explicitly assert the fillet/offset case no longer drops faces
   and no `Plane(0,0,0)` appears.
4. **Rebuild → native** — after round-trip, `brep_to_occ` yields a valid shape;
   `to_viewmesh()` still returns a non-empty mesh.
5. **Backward compat** — a stored v4 JSON fixture (plane+nurbs only) still loads.
6. **Visualization smoke** — the generic scene object tessellation returns a
   non-empty mesh for each analytic surface (no viewer process needed; call the
   tessellator directly).

Mark Rhino-equivalent extraction tests `@pytest.mark.rhino` if/when the Rhino
backend extracts analytic types (Rhino backend can be a follow-up; OCC first).

## Examples

- `examples/inspect_surface_types.py` — build a cylinder/sphere Brep, iterate
  faces, print `face.surface_type` and parameters, serialize to JSON and reload.
- Extend an existing viewer example (or add `examples/view_analytic_surface.py`)
  showing an extracted `CylindricalSurface` drawn on its own.

## Docs

- Rewrite the CONTEXT.md "Surface Type Support" table to the target state, and
  update the "two broken cases" / "Analytic → NURBS approximation" paragraphs:
  analytic types are now exact; only Revolution/Extrusion/Offset/Other remain
  NURBS approximations, and none of them produce wrong data anymore.
- Note the cone parameterization caveat and the v5 serialization format (with v4
  read compatibility) in the Serialization section.

## Risks / open questions

- **Cone parameterization** is the main correctness risk — covered by the
  fidelity test (#2), not by trusting a formula.
- **Periodic surface rebuild** (cylinder/sphere/torus) depends on pcurves being
  present and correct; the existing pcurve path is reused, but seam handling on
  full-revolution faces needs a round-trip test (closed cylinder).
- **COMPAS surface ↔ OCC `Geom_*Surface`** for rebuild: confirm OCP exposes
  `Geom_ConicalSurface` etc. and that `BRepBuilderAPI_MakeFace`/`UpdateEdge`
  accept them the same way as B-splines. If rebuild of a given analytic type is
  problematic, an acceptable interim is to rebuild via NURBS (geometry preserved,
  exact type lost only on the rebuilt native shape — the COMPAS-side type survives
  in JSON). Decide per-type during step 4.
- Scope: deliver OCC extraction + serialization + rebuild + viewer first; Rhino
  analytic extraction can be a fast follow if it risks ballooning the change.
