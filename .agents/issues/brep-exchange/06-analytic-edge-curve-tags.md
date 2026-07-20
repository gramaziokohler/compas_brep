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

> **No Rhino ran against this slice.** The LAMCP bridge was unreachable and there is
> no `rhinoinside` on this machine, so unlike slices 01–05 the Rhino half could not be
> executed anywhere — not by pytest, not through a live-Rhino harness. Criteria whose
> subject is "both" are checked only for the half that was actually observed, and the
> Rhino half is called out as written-but-unrun wherever it appears below.

- [x] Both writers emit `circle`, `arc`, and `ellipse` tags where the native edge curve
      is one; other curves still emit `nurbs`
      <br>**OCC: verified.** A cylinder's seams write `circle`, a sphere's meridian
      `arc`, a tilted cut `ellipse`, a freeform patch's boundary stays `nurbs`.
      **Rhino: written, never run.** `_analytic_edge_curve` asks `TryGetCircle` /
      `TryGetArc` / `TryGetEllipse` at `TOL.absolute`, then recovers the document
      interval and *verifies* it across the whole edge before emitting a tag —
      falling back to `nurbs` when the native parameterization is not affine in the
      document's. That fallback is what keeps an unrun writer from emitting a tag
      that looks right and is wrong (slice 04's trap); `nurbs` reproduces these
      curves exactly, so nothing geometric is lost when it fires.
- [x] Both readers rebuild native curves from each tag
      <br>**OCC: verified** — `test_a_cylinders_seams_arrive_as_native_circles_not_approximations`
      asks the adaptor, and the rebuilt edges come back `GeomAbs_Circle` /
      `GeomAbs_Ellipse`. **Rhino: written, never run** (`_analytic_curve_to_rhino`;
      both branches are exact constructions, not fits).
- [x] A cylinder's seam edges cross the wire as `circle`, not `nurbs`, and arrive as
      exact circles on the far side (within `TOL`, checked against the analytic curve —
      not a sampled-point tolerance that a NURBS approximation would also pass)
      <br>Checked at the *type* level, which is stronger than the criterion asks:
      the rebuilt edge's adaptor reports `GeomAbs_Circle` with radius 0.5 and a full
      `2*pi` interval. Measured payoff: the OCC cylinder round-trip volume error went
      from **1.24e-07 to 2.2e-16**, and the cone from 1.55e-08 to 5.6e-17 while
      regaining an edge it used to lose (3 → 2 edges, now 3 → 3).
- [x] The schema test covers all five edge tags on both backends, with no xfails
      <br>`OCC_UNWRITABLE_EDGE_CURVE_TAGS` and `RHINO_UNWRITABLE_EDGE_CURVE_TAGS` are
      both empty. The Rhino set is empty because **the format requires those tags**,
      not because Rhino was seen writing them — so a Rhino gap surfaces as a failure
      on the first licensed run rather than hiding in a speculative xfail.
- [x] A fixture with exact circular seams is committed and read by an OCC-marked test
      on CI
      <br>`occ_cylinder/cone/sphere/torus.json` regenerated; `test_occ_fixture_carries_exact_analytic_seams`
      asserts each carries its analytic seam tags and **no** `nurbs` edge. The
      documents shrank by ~500 lines — a circle is now 4 numbers, not a degree-11
      approximation. The **Rhino-authored** fixtures could NOT be regenerated (no
      license), so they still carry `nurbs` seams and their `volume_atol` stays at
      1e-3 instead of tightening to `TOL`. That refresh is the first thing to do on
      a licensed machine.
- [x] An unrepresentable edge curve type raises `BrepError`
      <br>`test_an_unrepresentable_edge_curve_raises`, plus
      `test_an_analytic_curve_without_its_domain_raises` — a conic with no interval
      is a *closed* curve, which is not what the edge runs along, so writing one
      would be a silent degradation.
- [x] ~~`pytest -m occ -q` passes~~; ~~`pytest -m rhino` passes on a licensed machine~~
      <br>**`pytest -m occ -q`: 305 passed, 2 xfailed** (was 284 passed / 5 xfailed —
      the three edge-curve xfails became passes, plus 25 new tests).
      `invoke test` (what CI runs): **373 passed, 2 xfailed**. `invoke lint`: passes.
      **`pytest -m rhino` was NOT RUN and could not be** — no bridge, no license, no
      `rhinoinside`. Do not read any checked box above as a Rhino pass.

## Blocked by

- 05-rhino-sphere-cone-torus-surfaces.md
