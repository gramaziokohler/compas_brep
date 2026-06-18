## Parent

../../surface-type-support-plan.md

## What to build

Make a cylindrical OCC face come back as a COMPAS `CylindricalSurface` all the
way through: extraction, inspection, serialization, native rebuild, and
visualization. This is the thick tracer bullet that lays the shared rail every
other analytic surface type reuses — sphere, torus, and cone slices build on the
scaffolding established here.

End-to-end behavior:

- `face.surface` on a cylindrical face returns a `CylindricalSurface` with the
  correct `radius` and `frame` (extracted from `adaptor.Cylinder()` →
  `gp_Cylinder.Position()/.Radius()`), instead of a NURBS approximation. The
  trim extent stays on the loops and `BrepFace.domain_u/domain_v` as today.
- `BrepFace.surface` is typed as the widened surface union. Add a `surface_type`
  string property and an `is_cylinder` predicate alongside the existing
  `is_planar` / `is_nurbs`. `__repr__` reports the real type (also in the OCC
  topology wrapper).
- The codec from slice 1 gains a `"cylinder"` tag round-tripping the COMPAS
  `CylindricalSurface.__data__`.
- `brep_rebuild` reconstructs a native cylindrical face: a generic
  `_analytic_surface_to_occ` builds the `Geom_*Surface` from frame + radius, and
  the existing pcurve-based trimmed-face builder is generalized to accept any
  `Geom_Surface` (not just NURBS) so periodic-seam handling is reused. If
  building the native analytic surface proves problematic, falling back to a
  NURBS rebuild is acceptable (the COMPAS-side exact type still survives in JSON);
  decide based on whether the rebuilt shape is valid.
- A generic `AnalyticSurfaceObject` viewer scene object (factored out of the
  existing NURBS surface tessellation, which already uses
  `space_u`/`space_v`/`point_at`) is registered for `CylindricalSurface` so an
  individually inspected `face.surface` can be drawn.

Shared scaffolding introduced here and reused by later slices: `_ax3_to_frame`
helper, the `BrepFace` union widening + `surface_type`, the
`_analytic_surface_to_occ` + generalized trimmed-face builder, and the generic
viewer object.

## Acceptance criteria

- [x] `face.surface` for a `BRepPrimAPI_MakeCylinder` face is a
      `CylindricalSurface` with correct `radius` and `frame` (within `TOL`)
- [x] Sampling `face.surface.point_at(u, v)` over the face domain matches the
      native surface evaluated at the same parameters (≤ 1e-6)
- [x] `BrepFace` exposes `surface_type` and `is_cylinder`; `__repr__` reports it
- [x] JSON round-trip preserves the `CylindricalSurface` type and parameters
- [x] After round-trip, the rebuilt Brep has the same face count, passes
      `BRepCheck`, and `to_viewmesh()` returns a non-empty mesh
- [x] The generic analytic-surface viewer object tessellates a
      `CylindricalSurface` into a non-empty mesh
- [x] All `@pytest.mark.occ` tests pass

## Blocked by

- 01-centralize-surface-codec.md
