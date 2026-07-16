## Parent

../../adr/0001-native-json-brep-exchange.md

## What to build

Widen the exchange document's edge curves from `line | nurbs` to
`line | circle | arc | ellipse | nurbs`, written and read by both backends.

With slices 4 and 5 done, an exact cylinder crosses the wire as a `CylindricalSurface`
but its seams still cross as NURBS approximations of circles. That mismatch between an
exact surface and its approximated edges is the tolerance gap that motivated the
hand-tuned join tolerance in the first place. An exact cylinder should carry exact
circular seams.

- Both writers detect circular, arc, and elliptical edge curves and emit the matching
  tag with the COMPAS type's `__data__`; anything else stays `nurbs`.
- Both readers rebuild the native curve from the tag rather than from an approximation.
- The schema test's edge-tag set grows to the full five, and both backends must
  round-trip every one — this is a contract, not a convention.
- Fixtures gain a case whose seams are exact circles.

Same loss policy as the surfaces: an edge curve type a backend cannot represent raises
`BrepError` rather than degrading to an approximation.

## Acceptance criteria

- [ ] Both writers emit `circle`, `arc`, and `ellipse` tags where the native edge curve
      is one; other curves still emit `nurbs`
- [ ] Both readers rebuild native curves from each tag
- [ ] A cylinder's seam edges cross the wire as `circle`, not `nurbs`, and arrive as
      exact circles on the far side (within `TOL`, checked against the analytic curve —
      not a sampled-point tolerance that a NURBS approximation would also pass)
- [ ] The schema test covers all five edge tags on both backends, with no xfails
- [ ] A fixture with exact circular seams is committed and read by an OCC-marked test
      on CI
- [ ] An unrepresentable edge curve type raises `BrepError`
- [ ] `pytest -m occ -q` passes; `pytest -m rhino` passes on a licensed machine

## Blocked by

- 05-rhino-sphere-cone-torus-surfaces.md
