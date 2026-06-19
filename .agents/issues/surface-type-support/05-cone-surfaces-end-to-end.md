## Parent

../../surface-type-support-plan.md

## What to build

Make a conical OCC face come back as a COMPAS `ConicalSurface` end-to-end,
reusing the cylinder-slice scaffolding.

This is the one analytic type whose parameterization does not map field-for-field
and so carries real correctness risk. OCC describes a cone as
`gp_Cone(Position, RefRadius, SemiAngle)` — `RefRadius` is the radius in the
reference plane at the frame origin, `SemiAngle` is the half-opening angle. COMPAS
`ConicalSurface(radius, height, frame)` derives the half-angle from
`radius`/`height` about the apex. Do **not** assume the obvious formula — derive
the mapping, then prove it empirically by sampling `point_at` against the native
surface over the face domain and iterating until it agrees. That fidelity check
is the gate for this slice; it makes the work AFK-able despite the risk.

End-to-end behavior:

- `face.surface` on a conical face returns a `ConicalSurface` whose surface
  coincides with the native OCC cone over the face's parameter range.
- The codec gains a `"cone"` tag round-tripping `ConicalSurface.__data__`.
- `brep_rebuild` reconstructs a native conical face via
  `_analytic_surface_to_occ` (NURBS rebuild fallback acceptable if the native
  analytic rebuild is not valid).
- `is_cone` predicate added; `surface_type` reports `"cone"`.
- The generic analytic-surface viewer object is registered for `ConicalSurface`.

## Acceptance criteria

- [x] `face.surface` for a `BRepPrimAPI_MakeCone` face is a `ConicalSurface`
- [x] Sampling `face.surface.point_at(u, v)` over the face domain matches the
      native cone surface evaluated at the same parameters (≤ 1e-6) — this is the
      primary correctness gate, not a field-equality assertion
- [x] `BrepFace.is_cone` and `surface_type == "cone"`
- [x] JSON round-trip preserves the `ConicalSurface` type and parameters
- [x] After round-trip, the rebuilt Brep passes `BRepCheck` and `to_viewmesh()`
      returns a non-empty mesh
- [x] The viewer object tessellates a `ConicalSurface` into a non-empty mesh
- [x] All `@pytest.mark.occ` tests pass

## Blocked by

- 02-cylinder-surfaces-end-to-end.md
