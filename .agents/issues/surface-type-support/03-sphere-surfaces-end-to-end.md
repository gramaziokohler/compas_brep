## Parent

../../surface-type-support-plan.md

## What to build

Make a spherical OCC face come back as a COMPAS `SphericalSurface` end-to-end,
reusing the scaffolding from the cylinder slice. This is a thin addition: one
extraction branch, one codec tag, one rebuild mapping, one viewer registration,
and tests.

End-to-end behavior:

- `face.surface` on a spherical face returns a `SphericalSurface` with the
  correct `radius` and `frame` (from `adaptor.Sphere()` →
  `gp_Sphere.Position()/.Radius()`).
- The codec gains a `"sphere"` tag round-tripping `SphericalSurface.__data__`.
- `brep_rebuild` reconstructs a native spherical face via
  `_analytic_surface_to_occ`. Spheres are doubly periodic, so confirm the
  pcurve-based trimmed-face path handles the seams; a NURBS rebuild fallback is
  acceptable if the native analytic rebuild is not valid.
- `is_sphere` predicate added; `surface_type` reports `"sphere"`.
- The generic analytic-surface viewer object is registered for
  `SphericalSurface`.

## Acceptance criteria

- [x] `face.surface` for a `BRepPrimAPI_MakeSphere` face is a `SphericalSurface`
      with correct `radius` and `frame` (within `TOL`)
- [x] Sampling `point_at(u, v)` over the face domain matches the native surface
      (≤ 1e-6)
- [x] `BrepFace.is_sphere` and `surface_type == "sphere"`
- [x] JSON round-trip preserves the `SphericalSurface` type and parameters
- [x] After round-trip, the rebuilt Brep passes `BRepCheck` and `to_viewmesh()`
      returns a non-empty mesh
- [x] The viewer object tessellates a `SphericalSurface` into a non-empty mesh
- [x] All `@pytest.mark.occ` tests pass

## Blocked by

- 02-cylinder-surfaces-end-to-end.md
