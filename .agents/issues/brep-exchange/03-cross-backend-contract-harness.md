## Parent

../../adr/0001-native-json-brep-exchange.md

## What to build

Pin the exchange contract with committed fixtures and a schema test, so that "Rhino
writes a tag OCC cannot read" is caught on CI rather than on one laptop.

CI has no Rhino license, and `addopts = "-m 'not rhino'"` skips Rhino tests by default
even locally — so any test needing a live Rhino is a test that effectively never runs.
This is not hypothetical: `test_rhino_serialization.py` asserted `version == 4` for an
entire release after the writer moved to 5, and nobody saw it fail. Live cross-backend
round-trips are therefore rejected as the verification mechanism.

Three pieces, built against the v6 format:

1. **Golden fixtures** — real Rhino-authored exchange documents committed under
   `tests/fixtures/`, covering the format's shapes: a box (plane), a filleted box
   (nurbs), a sphere (pole/singular trims), a box with a through-hole (inner loop).
   OCC-marked tests read them on CI and assert the tags survive into the rebuilt shape.
2. **Fixture regeneration** — a Rhino-marked test that regenerates each fixture from
   the same source geometry and asserts it still matches the committed file, so drift
   surfaces on a dev machine.
3. **Schema test** — both backends must round-trip every tag in the format's tag set.
   Cheap, runs on CI, and would have caught the dropped-cylinder bug on day one.

The schema test's tag set is the format's, not any one backend's — so the four analytic
surface tags Rhino cannot yet write (`cylinder`, `sphere`, `cone`, `torus`) go in now,
marked `xfail`. Slices 4 and 5 flip them green. Their presence as xfail is the point:
the gap is recorded in the test suite instead of in an ADR.

Also fix `test_rhino_serialization.py`, which still asserts `version == 4`.

## Acceptance criteria

- [ ] `tests/fixtures/` holds committed Rhino-authored v6 documents for box, filleted
      box, sphere, and box-with-hole
- [ ] OCC-marked tests read each fixture on CI, rebuild it, and assert the surface tags,
      loop roles, and face count survive — these tests fail if a fixture is malformed
- [ ] A Rhino-marked test regenerates every fixture and asserts it matches the committed
      file, with a documented way to refresh them intentionally
- [ ] A schema test asserts both backends round-trip every surface tag and every edge
      curve tag in the format's tag set
- [ ] The four analytic surface tags Rhino cannot write are present in the schema test
      as `xfail`, not omitted
- [ ] `test_rhino_serialization.py` asserts the real current version
- [ ] `pytest -m occ -q` passes on CI with no Rhino present

## Blocked by

- 02-v6-explicit-loop-roles-and-pcurves.md
