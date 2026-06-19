## Parent

../../surface-type-support-plan.md

## What to build

Make a toroidal OCC face come back as a COMPAS `ToroidalSurface` end-to-end,
reusing the cylinder-slice scaffolding. Thin addition: one extraction branch,
one codec tag, one rebuild mapping, one viewer registration, and tests.

End-to-end behavior:

- `face.surface` on a toroidal face returns a `ToroidalSurface` with
  `radius_axis` from `gp_Torus.MajorRadius()`, `radius_pipe` from
  `MinorRadius()`, and `frame` from `Position()` (via `adaptor.Torus()`).
- The codec gains a `"torus"` tag round-tripping `ToroidalSurface.__data__`.
- `brep_rebuild` reconstructs a native toroidal face via
  `_analytic_surface_to_occ`. Tori are doubly periodic; confirm seam handling,
  NURBS rebuild fallback acceptable if needed.
- `is_torus` predicate added; `surface_type` reports `"torus"`.
- The generic analytic-surface viewer object is registered for `ToroidalSurface`.

## Acceptance criteria

- [x] `face.surface` for a `BRepPrimAPI_MakeTorus` face is a `ToroidalSurface`
      with correct `radius_axis`, `radius_pipe`, and `frame` (within `TOL`)
- [x] Sampling `point_at(u, v)` over the face domain matches the native surface
      (≤ 1e-6)
- [x] `BrepFace.is_torus` and `surface_type == "torus"`
- [x] JSON round-trip preserves the `ToroidalSurface` type and parameters
- [x] After round-trip, the rebuilt Brep passes `BRepCheck` and `to_viewmesh()`
      returns a non-empty mesh
- [x] The viewer object tessellates a `ToroidalSurface` into a non-empty mesh
- [x] All `@pytest.mark.occ` tests pass

## Blocked by

- 02-cylinder-surfaces-end-to-end.md
