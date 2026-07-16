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

- [x] `tests/fixtures/` holds committed Rhino-authored v6 documents for box, filleted
      box, sphere, and box-with-hole
      <br>Authored inside live Rhino 8 through the LAMCP bridge, not hand-written.
      `tests/exchange_fixtures.py` is the single definition of the source geometry.
- [x] OCC-marked tests read each fixture on CI, rebuild it, and assert the surface tags,
      loop roles, and face count survive — these tests fail if a fixture is malformed
      <br>`tests/test_exchange_fixtures.py`. Tags, roles and face count all survive.
      Volume does **not**, on two fixtures — see the note below; those assertions are
      kept as strict `xfail` rather than dropped.
- [x] A Rhino-marked test regenerates every fixture and asserts it matches the committed
      file, with a documented way to refresh them intentionally
      <br>`pytest -m rhino tests/test_exchange_fixtures.py --refresh-fixtures` rewrites
      them. The comparison is structure-exact and float-tolerant, so it detects drift in
      our writer rather than tripping on Rhino's own last digit — and it was checked
      against six perturbed documents before its green was trusted.
- [x] A schema test asserts both backends round-trip every surface tag and every edge
      curve tag in the format's tag set
      <br>`tests/test_exchange_schema.py`. Each tag has a source shape that genuinely
      contains it, verified against the OCC adaptor rather than assumed — the `ellipse`
      source really does yield `GeomAbs_Ellipse` edges, the `arc` source real quarter
      circles.
- [x] The four analytic surface tags Rhino cannot write are present in the schema test
      as `xfail`, not omitted
      <br>`strict=True`, so slices 04 and 05 are told when they flip green. Confirmed in
      live Rhino that all four genuinely fail today, and that `plane`/`nurbs`/`line` pass
      — a strict xfail on a tag Rhino could already write would be worse than none.
      The `circle`/`arc`/`ellipse` **edge** tags are xfail too, on both backends: the
      criterion says "every edge curve tag in the format's tag set", and slice 06 owns them.
- [x] `test_rhino_serialization.py` asserts the real current version
      <br>Already fixed in slice 02 (`version == 6`); nothing to do here.
- [x] `pytest -m occ -q` passes on CI with no Rhino present
      <br>**252 passed, 6 xfailed** (was 227). No Rhino import on the OCC path.

## Blocked by

- 02-v6-explicit-loop-roles-and-pcurves.md

## Notes from implementation

**The harness found a real defect on its first run, and it is not a cross-backend one.**
The OCC rebuild of a filleted box loses 26% of its volume and reports invalid. The
first read looked like a Rhino→OCC failure, which is what this slice exists to catch —
but measuring OCC against itself killed that theory: an **OCC-authored** filleted box
round-trips through OCC the same way (volume 7.572619 → 4.054412). `src/` was untouched
at the time, so it is in committed code.

The cause is orientation, not trimming. Per-face areas of the rebuilt shape come back
as `[-0.6597 ×6, -0.1414 ×4, +0.1414 ×4, +0.6608 ×6, +1.96 ×6]` — the magnitudes are
right and the signs are not, so ten of the twenty-six faces are inside out and the
divergence integral cancels most of the volume away. Only curved faces are affected;
the six planes are exact. `occ_rebuild` honors `is_reversed` for the whole face, so
the suspect is `_build_trimmed_face`, which rebuilds each face's edges independently
and never shares them (this also explains 48 edges → 32 after sewing).

This belongs to no existing slice: 04 and 05 change what Rhino *writes*, and 06 owns
seam edges. It needs its own issue. It is recorded as `strict=True` xfail on the
volume assertions rather than deleted, so it cannot be quietly lost, and whoever fixes
it is told to un-xfail.

**A trap worth knowing about:** `BrepFace.area` is a polygon approximation over the
loop's points and returns `0.0` for these faces, which first read as "every NURBS face
rebuilds empty". That was wrong. Real per-face areas come from OCC's `BRepGProp`.

**`Brep.from_surface` had never worked on the Rhino backend.** `backend/rhino/plugins.py`
imported `_compas_nurbs_surface_to_rhino`; the function is called `nurbs_surface_to_rhino`,
so the call raised `ImportError` every time. Found because the schema test needs a NURBS
surface from both backends. Fixed here (one word) rather than filed, because the criterion
"both backends round-trip every surface tag" cannot be met for `nurbs` without it. Nothing
could regress: the previous behaviour was an unconditional raise.

**On the v4 document.** Slice 01 asked this slice to replace the hand-written
`UNIT_BOX_OCC_DATA` with a real backend-authored fixture. It can't be: no backend has
written v4 for two versions, so there is nothing to author it with — regenerating it
would produce a v6 document under a v4 name. It stays hand-written, but moved to
`tests/fixtures/legacy_v4_box.json` and is now read by an **OCC**-marked test. Slice 02's
warning was that it was the only v4 document under test; it was also Rhino-marked, so the
v4 read path was covered only where `-m rhino` runs, which is nowhere. It runs on CI now.
