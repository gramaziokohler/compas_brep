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

- [ ] Rhino `face.surface` returns `SphericalSurface`, `ConicalSurface`, and
      `ToroidalSurface` for the matching faces, with correct parameters within `TOL`
- [ ] `surface_type` and the `is_sphere` / `is_cone` / `is_torus` predicates hold on the
      Rhino backend
- [ ] An OCC-authored document carrying each tag rebuilds in Rhino as the matching
      native analytic surface — the corresponding `TryGet*` succeeds on the rebuilt
      face, not merely a volume match
- [ ] Rhino's cone extract and rebuild agree with the COMPAS `(radius, height, frame)`
      convention the document stores; a cone survives an OCC → Rhino → OCC trip with
      radius and height intact
- [ ] Rhino-authored sphere, cone, and torus fixtures are committed and read by
      OCC-marked tests on CI
- [ ] All four analytic schema-test xfails are gone and the cases pass on both backends
- [ ] A surface Rhino cannot represent raises `BrepError` — it is neither approximated
      nor skipped, and a test asserts the raise
- [ ] `pytest -m occ -q` passes; `pytest -m rhino` passes on a licensed machine

## Blocked by

- 04-rhino-cylinder-surfaces.md
