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

- [x] `face.surface` on a Rhino cylindrical face is a `CylindricalSurface` with correct
      radius and frame (within `TOL`)
      <br>`_extract_surface` via `TryGetCylinder`, but only when the face's
      parameterization maps affinely onto the document's — see the note below, which is
      the whole story of this slice.
- [x] `face.surface_type == "cylinder"` and `is_cylinder` hold on the Rhino backend
      <br>Both follow from the extracted type; `RhinoBrepFace.__repr__` no longer
      hardcodes plane/nurbs either.
- [x] Rhino writes the `"cylinder"` tag; a Rhino round-trip preserves it
      <br>No codec change was needed, as the issue predicted. The pcurves were another
      matter entirely — see below.
- [x] An OCC-authored document with a `"cylinder"` tag rebuilds in Rhino as a native
      cylindrical face — `TryGetCylinder` succeeds on the rebuilt face, not merely a
      volume match
      <br>Verified in live Rhino against a committed **OCC-authored** fixture
      (`tests/fixtures/occ_cylinder.json`) — the mirror of the existing fixtures, since
      neither kernel is importable in the other's process. Read the volume note below
      before trusting any OCC→Rhino volume: it is broken for a *plain box* too, and was
      before this slice.
- [x] A Rhino-authored cylinder fixture is committed; an OCC-marked test reads it on CI
      and asserts the surface arrives as `CylindricalSurface`
      <br>`tests/fixtures/rhino_cylinder.json`. `rhino_box_with_hole.json`'s wall also
      flipped `nurbs` → `cylinder`, and is asserted the same way.
- [x] The `cylinder` schema-test xfail is removed and the case passes on both backends
      <br>Confirmed in live Rhino: 5 passed / 6 xfailed, no XPASS — so the remaining
      strict xfails (cone/sphere/torus, circle/arc/ellipse) still genuinely fail.
- [x] Sampling the rebuilt face's surface against the original at matching parameters
      agrees within 1e-6
      <br>`test_rebuilt_surface_samples_match_the_original`, 45 sample points. This is
      the criterion that forced the parameterization work: "at matching parameters" is
      exactly what Rhino did not honor.
- [x] `pytest -m occ -q` passes; ~~`pytest -m rhino` passes on a licensed machine~~
      <br>**`pytest -m occ -q`: 261 passed, 6 xfailed.** `pytest -m rhino` was **NOT
      RUN** — there is no `rhinoinside` on this machine and `-m 'not rhino'` skips it by
      default anyway. Do not read the checked box as a `pytest -m rhino` pass. All 78
      Rhino-marked tests were instead executed inside live Rhino 8 through the LAMCP
      bridge, where all 78 pass (6 xfail, 0 XPASS). Real kernel verification, not a
      pytest run.

## Blocked by

- 03-cross-backend-contract-harness.md

## Notes from implementation

**The tag was the easy half. The parameterization was the slice.** A COMPAS
`CylindricalSurface` is parameterized `(angle, height)`, and that is what OCC's pcurves
already are. Rhino does not agree: it parameterizes a cylinder wall by **arc length**,
so its native `u` is `radius * angle` — a wall of radius 0.5 runs `u` from 0 to π for a
full turn, and radius 0.3 runs it to 0.6π. Emitting the `cylinder` tag with Rhino's
pcurves untouched would have put every trim at the wrong angle: a document that is
worse than the `nurbs` tag it replaced, because it looks right. `_cylinder_and_param_map`
recovers the map by probing and then **checks it across the whole domain** rather than
assuming it.

**Why a fillet face is still tagged `nurbs`, and why that is not a degradation.** Rhino's
12 fillet faces on a filleted box are exactly cylinders to `TryGetCylinder` (at 1e-9),
and OCC tags them `cylinder`. They are still written `nurbs` here, because Rhino stores
them as rational NURBS whose angle is **not linear** in either parameter — and which
swap the roles of `u` and `v`. Only an affine map can be carried onto a pcurve's control
points exactly, so the conversion would have to refit. The `nurbs` tag reproduces those
faces exactly (they are natively NURBS), so nothing is lost geometrically; what is lost
is the analytic tag. This is a real remaining OCC/Rhino divergence and it needs the
parameterization question settled — the same one slice 02 flagged for `plane`.

**Two cross-backend defects fell out, both pre-existing, both found by trying to read an
OCC document in Rhino — which nothing had ever done.**

1. **`curve_2d` meant opposite things in the two writers.** OCC writes a pcurve in its
   **edge's** direction and reads it that way; Rhino wrote it in the **trim's**. Measured
   on both, not assumed: on a reversed trim, OCC's pcurve starts at the edge's start
   (dist 0) and Rhino's started at the edge's end. Rhino's own *planar* rebuild already
   assumed edge-direction, so Rhino's non-planar writer was the lone dissenter.
   Edge-direction won.
2. **Rhino's pcurve domain was unrelated to its edge curve's.** OCC requires the two to
   share a parameterization; Rhino does not. Rhino's circular seam pcurve ran over
   `(0, π)` while its edge curve ran over `(-π, 0)`, and OCC read that as an edge with no
   range and failed to sew the face at all (`Bnd_Box is void`). `_align_pcurve_to_edge`
   remaps the knots only — control points untouched, so it is exact.

Together these mean **no Rhino-authored non-planar face has ever been readable by OCC
correctly**. That is most of slice 03's "OCC flips the orientation of curved faces": the
filleted box fixture went from 4.054412 to 7.063681 (true 7.563414) on this change alone.
It is *not* all of it — both remain wrong and stay `strict` xfail, and slice 03 already
proved an OCC-authored filleted box breaks the same way inside OCC, so a separate
OCC-side defect is still there.

**A volume trap, measured rather than assumed.** OCC→Rhino gets the volume wrong, and it
is tempting to blame the cylinder. It is not the cylinder: with the **pre-slice-04** code
an OCC-authored **plain box** rebuilds in Rhino at volume `-0.0` with `IsSolid False`,
while OCC cylinders simply raised. So OCC→Rhino has never produced a solid for anything.
The criterion above asks for `TryGetCylinder`, "not merely a volume match", which is met.
**No slice owns the OCC→Rhino volume defect** — it needs its own issue.

**The cylinder fixture's residual 1.5e-4 belongs to slice 06.** Rhino writes a circle
edge as an exact rational degree-2 NURBS; OCC writes it as a degree-11 *polynomial
approximation* (all weights 1.0). A NURBS circle's parameter is not its angle, so the
wall's pcurve (linear in angle) and its edge curve trace the same circle at different
rates, and OCC's rebuilt wall is off by 1.5e-4. Analytic `circle` edge tags are what make
a seam exact — the fixture's `volume_atol` should tighten to `TOL` when slice 06 lands.
The invalidity is the *already known* seam defect: confirmed not Rhino-specific, since an
OCC-authored cylinder rebuilds invalid with the same edge count.
