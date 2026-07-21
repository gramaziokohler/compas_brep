## Parent

../../adr/0001-native-json-brep-exchange.md

## Status

Filed, not fixed. Diagnosed on 2026-07-21 during the first live-Rhino run of the
slice 06 code (the LAMCP bridge was down for slice 06 itself; this is the first time
any of it has executed against a real Rhino kernel).

## What's broken

A **reversed** analytic curved face — a cylindrical or conic wall bounding a hole or
void rather than solid material — rebuilds in the Rhino backend as a `Brep` that
`IsValidWithLog()` reports valid (`True`, no log message), but:

- `Rhino.Geometry.AreaMassProperties.Compute(face)` returns `None` for that one face
  (every other face on the same Brep computes fine).
- `VolumeMassProperties.Compute(brep)` returns `None` / the wrapper's `.volume`
  comes back `0.0`.
- `brep.IsSolid` is `False`.

Reproduces on:
- `Brep.from_box(Box(2,2,2)) - Brep.from_cylinder(Cylinder(0.3, 4.0))`
  (`box_with_hole`) — round-tripped through the Rhino backend's own document
  writer/rebuilder (Rhino-authored, Rhino-rebuilt, no OCC involved).
- The same shape's cylindrical wall specifically (`test_roundtrip_of_a_trimmed_wall_keeps_its_hole`).
- `Brep.from_box(Box(2,2,2)).filleted(0.3)` — 4 of its 26 faces are reversed fillet
  patches; same symptom.

Does **not** reproduce on a plain (unreversed) `Brep.from_cylinder(Cylinder(0.5, 2.0))`:
that round-trips exactly — `IsSolid True`, volume error `0.0`. This isolates the
defect to `face.is_reversed == True` on a curved analytic surface.

## What it is not

This session added a face-reversal loop-winding compensation to
`brep_to_rhino` (`src/compas_brep/backend/rhino/conversion.py`, around the
`trims = list(reversed(loop.trims)) if face.is_reversed else ...` block) to fix a
different, confirmed bug: a reversed face's loop arriving with the wrong winding
in Rhino's parameter space. That fix is real and necessary — before it, `box_with_hole`
didn't reach this code path at all; it hard-crashed earlier with
`BrepError: Cannot project curve of type Circle onto a plane`, because the old
committed code never handled `circle`/`ellipse` edges on planar caps.

The defect in this issue was measured **with and without** that compensation
(reverted to `trims = list(loop.trims)` / `is_reversed = trim.is_reversed` and
re-ran the exact same `box_with_hole` case): identical result both times
(`AreaMassProperties` still `None`, volume still `0.0`). So the loop-winding fix is
not the cause, and reverting it would not fix this either.

This is very likely the same defect flagged and left unowned across three earlier
slices without ever being reproduced against a real kernel:
- Slice 04: "OCC->Rhino gets the volume wrong... OCC->Rhino has never produced a
  solid for ANYTHING... NO SLICE OWNS THE OCC->RHINO VOLUME DEFECT."
- Slice 05: "Cylinder/cone rebuild valid-but-not-solid in OCC->Rhino: the
  planar-cap / seam story, still open."
This issue is the first time it has actually been reproduced and isolated (to
reversed curved faces specifically) rather than just observed as "not solid."

## Suggested starting point

`IsValidWithLog` passing while `AreaMassProperties` fails on one specific face
suggests a geometric degeneracy that Rhino's structural/topology validator doesn't
check — e.g. a trim loop that is topologically closed but numerically
self-tangent, or a seam-adjacent zero-width sliver, on the *reversed* side of a
periodic surface specifically. Worth comparing the trim loop's `To3dCurve()` (which
came back `IsValid: False` in the `box_with_hole` wall case, despite the Brep-level
check passing) against the same loop's un-reversed counterpart to find exactly what
differs.

## Acceptance criteria

- [ ] `box_with_hole`, `filleted_box`, and a boolean-cut cylinder all round-trip
      through the Rhino backend as valid, solid Breps with volume within `TOL` of
      the original.
- [ ] A reversed analytic face's `AreaMassProperties` computes (non-`None`) and its
      sign matches the face's orientation.
- [ ] The currently-failing Rhino-marked tests pass without weakening their
      assertions: `test_builder_boolean_cut_cylinder_volume_preserved`,
      `test_builder_filleted_box_volume_preserved`,
      `test_round_trip_boolean_diff_volume_matches`, `test_roundtrip_box_with_hole`,
      `test_v6_loop_order_does_not_change_the_rebuilt_shape`,
      `test_roundtrip_of_a_trimmed_wall_keeps_its_hole`.
