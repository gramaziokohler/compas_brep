## Parent

../../surface-type-support-plan.md

## What to build

Remove the silently-wrong `Plane(0, 0, 0)` fallback so that surfaces without an
exact COMPAS type — offset surfaces (from fillets/chamfers), surfaces of
revolution, surfaces of extrusion, and any "Other" — always come back as a
faithful NURBS approximation, never as corrupt dummy data.

This slice is independent of the analytic-type slices; it only needs the codec.
It can run in parallel with the cylinder/sphere/torus/cone work.

End-to-end behavior:

- `_extract_surface` returns a real NURBS approximation for offset / revolution /
  extrusion / other surfaces via the existing `GeomConvert` path. The
  `Plane(0, 0, 0)` fallback is deleted: if `GeomConvert` genuinely fails,
  extraction fails loudly (raise or return a sentinel the caller skips) rather
  than emitting wrong geometry.
- A Brep containing fillet faces (offset surfaces) round-trips through JSON
  without dropping those faces, and no `Plane(0, 0, 0)` appears anywhere.

## Acceptance criteria

- [x] No code path returns `Plane(Point(0,0,0), ...)` as a surface fallback
- [x] A filleted box (offset surfaces) has every fillet face come back as a
      `NurbsSurface`, not a degenerate plane
- [x] JSON round-trip of a filleted shape preserves the full face count
- [x] If surface conversion truly fails, the failure is explicit (no silent
      wrong-geometry emission)
- [x] All `@pytest.mark.occ` tests pass

## Blocked by

- 01-centralize-surface-codec.md
