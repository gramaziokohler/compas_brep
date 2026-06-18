## Parent

../../surface-type-support-plan.md

## What to build

Document the new accurate surface-type support and ship runnable examples that
demonstrate inspecting and visualizing extracted analytic surfaces.

End-to-end behavior:

- The CONTEXT.md "Surface Type Support" table is rewritten to the target state:
  Cylinder/Cone/Sphere/Torus are exact COMPAS analytic types (not approximations);
  only Surface of Revolution / Extrusion / Offset / Other remain NURBS
  approximations, and none of them produce wrong data anymore. The "two broken
  cases" and "Analytic → NURBS approximation" paragraphs are updated accordingly.
- The Serialization section notes the v5 format and its v4 read compatibility,
  and the cone parameterization caveat.
- An example script builds a primitive Brep (e.g. cylinder, sphere), iterates its
  faces, prints `surface_type` and key parameters, then serializes to JSON and
  reloads — showing the type survives the round-trip.
- An example (new or extension of an existing viewer example) draws an extracted
  analytic `face.surface` on its own through the viewer scene object.

## Acceptance criteria

- [ ] CONTEXT.md surface table and surrounding prose reflect actual behavior
      after slices 2–6
- [ ] Serialization section documents v5 + v4 read-compat and the cone caveat
- [ ] An inspect example prints surface types/parameters and demonstrates a JSON
      round-trip preserving the analytic type
- [ ] A visualization example draws an extracted analytic surface
- [ ] Example scripts run without error against the OCC backend

## Blocked by

- 02-cylinder-surfaces-end-to-end.md
- 03-sphere-surfaces-end-to-end.md
- 04-torus-surfaces-end-to-end.md
- 05-cone-surfaces-end-to-end.md
- 06-robust-fallback-offset-unknown.md
