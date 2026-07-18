## Parent

../../adr/0001-native-json-brep-exchange.md

## What to build

Complete Rhino's analytic surface coverage on the rail slice 4 laid: sphere, cone, and
torus extract, write, read, and rebuild as their COMPAS analytic types. After this
slice the Rhino backend matches OCC's analytic coverage, which is the bar ADR-0001 sets
— anything less fails representational fidelity.

- `_extract_surface` (Rhino) gains `TryGetSphere`, `TryGetCone`, and `TryGetTorus`
  branches returning `SphericalSurface`, `ConicalSurface`, and `ToroidalSurface`.
- The rebuild builds the corresponding native Rhino surface and hands it to the ported
  builder, as the cylinder branch does.
- The three remaining schema-test xfails flip green, and Rhino-authored fixtures for
  each are committed for OCC to read on CI.

**Cone parameterization.** COMPAS `ConicalSurface` is `(radius, height, frame)`; the OCC
side derives that from `gp_Cone`'s `(Position, RefRadius, SemiAngle)` via
`height = -RefRadius / tan(SemiAngle)`. The v6 document stores the COMPAS `radius` and
`height` directly, so the Rhino side reads those — it does not need OCC's SemiAngle,
which is not preserved in the serialized form. Confirm Rhino's `TryGetCone` maps to the
same convention on extract rather than assuming it.

**Loss policy.** A surface Rhino meets that it cannot represent as one of the format's
tags raises `BrepError`. It does not fall back to an approximation and does not skip the
face. This generalizes the rule OCC's `_extract_surface` already follows, and it exists
because the opposite behavior is what let `brep_to_rhino` silently drop every analytic
face for an entire release. The cost — an exotic surface produces a hard error rather
than an approximation — is accepted.

## Acceptance criteria

- [x] Rhino `face.surface` returns `SphericalSurface`, `ConicalSurface`, and
      `ToroidalSurface` for the matching faces, with correct parameters within `TOL`
      <br>`_extract_surface` now goes through `_compas_analytic_surface`, which asks
      `TryGetSphere` / `TryGetCone` / `TryGetTorus` at `TOL.absolute`. Verified in live
      Rhino: sphere r=1.3, torus (2.0, 0.4), cone base r=0.6 all extract exactly.
- [x] `surface_type` and the `is_sphere` / `is_cone` / `is_torus` predicates hold on the
      Rhino backend
      <br>Both follow from the extracted COMPAS type in shared `face.py` code.
- [x] An OCC-authored document carrying each tag rebuilds in Rhino as the matching
      native analytic surface — the corresponding `TryGet*` succeeds on the rebuilt
      face, not merely a volume match
      <br>Verified in live Rhino against committed OCC-authored fixtures
      (`occ_sphere/cone/torus.json`). This uncovered the degenerate-edge bridge: OCC
      spells a pole/apex as a zero-length edge, Rhino as a singular trim — see the
      progress log.
- [x] Rhino's cone extract and rebuild agree with the COMPAS `(radius, height, frame)`
      convention the document stores; a cone survives an OCC → Rhino → OCC trip with
      radius and height intact
      <br>`_compas_cone_from_rhino` maps Rhino's apex-origin cone to the document's
      base-origin `(radius, height)`. Measured OCC → Rhino → OCC: radius 0.5, height 1.0
      preserved. The document's parameter space is pinned against OCC's `gp_Cone` in
      `test_exchange_parameterization.py`, which runs on CI.
- [x] Rhino-authored sphere, cone, and torus fixtures are committed and read by
      OCC-marked tests on CI
      <br>`rhino_sphere.json` flipped `nurbs` → `sphere`; `rhino_cone.json` and
      `rhino_torus.json` are new. `test_occ_reads_a_rhino_authored_analytic_surface`
      asserts the analytic type arrives on CI.
- [x] All four analytic schema-test xfails are gone and the cases pass on both backends
      <br>`RHINO_UNWRITABLE_SURFACE_TAGS` is now empty. Confirmed in live Rhino: all six
      surface tags write and rebuild, 0 XPASS; the three edge-curve tags stay xfail for
      slice 06.
- [x] A surface Rhino cannot represent raises `BrepError` — it is neither approximated
      nor skipped, and a test asserts the raise
      <br>`test_rebuild_raises_on_a_surface_type_it_cannot_represent` drives
      `_surface_to_rhino` with an unknown surface; the raises-shim was self-checked in
      live Rhino before its green was trusted.
- [x] `pytest -m occ -q` passes; ~~`pytest -m rhino` passes on a licensed machine~~
      <br>**`pytest -m occ -q`: 284 passed, 5 xfailed** (one fewer xfail than slice 04:
      the sphere's OCC rebuild volume now clears the 1e-3 bar as an analytic surface).
      `pytest -m rhino` was **NOT RUN** — no `rhinoinside` on this machine and
      `-m 'not rhino'` skips it by default. Do not read the checked box as a
      `pytest -m rhino` pass. All Rhino-marked tests were instead executed in live
      Rhino 8 through the LAMCP bridge: 95 existing/new surface + serialization +
      topology tests pass, all 7 fixtures regenerate with zero drift, and the full
      schema table matches. Real kernel verification, not a pytest run.

## Blocked by

- 04-rhino-cylinder-surfaces.md
