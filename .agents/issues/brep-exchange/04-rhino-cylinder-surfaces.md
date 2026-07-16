## Parent

../../adr/0001-native-json-brep-exchange.md

## What to build

Make a cylindrical face survive the exchange in both directions through the Rhino
backend: extract, write, read, rebuild. This is the tracer bullet that lays the rail
sphere, cone, and torus reuse.

Rhino's `_extract_surface` currently emits `plane` or `nurbs` only, and Rhino's rebuild
understands nothing else. Every v5 document OCC produced with an analytic tag was
therefore unreadable by Rhino, and the faces were dropped without error. That silent
drop is the failure this slice exists to end.

- `_extract_surface` (Rhino) returns a `CylindricalSurface` for a cylindrical face via
  `Surface.TryGetCylinder`, with radius and frame matching the native surface.
- The writer emits the `"cylinder"` tag through the existing codec — no codec change,
  the tag already exists and OCC already writes it.
- The rebuild builds a native `Rhino.Geometry.Cylinder` surface and hands it to the
  ported builder (slice 1), so the face is trimmed by its pcurves like any other.
- The schema test's `cylinder` xfail (slice 3) flips green, and a Rhino-authored
  cylinder fixture is added that OCC reads on CI.

The bar is representational fidelity, not geometric equivalence: matching volume within
tolerance is not sufficient, because a NURBS approximation would pass that. The rebuilt
face must be a cylinder to Rhino.

## Acceptance criteria

- [ ] `face.surface` on a Rhino cylindrical face is a `CylindricalSurface` with correct
      radius and frame (within `TOL`)
- [ ] `face.surface_type == "cylinder"` and `is_cylinder` hold on the Rhino backend
- [ ] Rhino writes the `"cylinder"` tag; a Rhino round-trip preserves it
- [ ] An OCC-authored document with a `"cylinder"` tag rebuilds in Rhino as a native
      cylindrical face — `TryGetCylinder` succeeds on the rebuilt face, not merely a
      volume match
- [ ] A Rhino-authored cylinder fixture is committed; an OCC-marked test reads it on CI
      and asserts the surface arrives as `CylindricalSurface`
- [ ] The `cylinder` schema-test xfail is removed and the case passes on both backends
- [ ] Sampling the rebuilt face's surface against the original at matching parameters
      agrees within 1e-6
- [ ] `pytest -m occ -q` passes; `pytest -m rhino` passes on a licensed machine

## Blocked by

- 03-cross-backend-contract-harness.md
