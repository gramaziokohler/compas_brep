## Parent

../../adr/0002-rhino-rebuild-via-brepbuilder.md

## What to build

Replace the Rhino backend's face-rebuild path with the low-level RhinoCommon Brep
construction API, ported from `compas_rhino.geometry.brep.builder._RhinoBrepBuilder`.
After this slice, a genuinely trimmed face survives a Rhino round-trip as a trimmed
face rather than as a rectangular parametric crop.

Today `brep_to_rhino` calls `ToBrep()` on each surface, crops it to the `(u, v)`
bounding box of its outer loop's trim-curve endpoints, and stitches the results with
`JoinBreps`. That cannot represent a trimmed face: every fillet, every boolean-cut
cylinder wall, every non-rectangular patch is rebuilt as a rectangular sheet, and the
pcurves the writer faithfully serialized are discarded on read. The port replaces this
with `AddSurface`, `Faces.Add`, `AddEdgeCurve`, `AddTrimCurve`, `Trims.Add`, and
`Trims.AddSingularTrim`.

Two workarounds go away with it, because both are symptoms of the same cause:

- The hand-tuned `1e-6` join tolerance is dropped for `TOL.absolute`. The builder
  shares edges by index instead of rediscovering them by proximity, so there is
  nothing left to fudge.
- Singular trims are no longer dropped. Both `rhino_extract_topology` and
  `rhino_brep_to_data` currently skip trims with no edge ("singular trim (e.g. at pole
  of sphere) — skip"), which is exactly what `Trims.AddSingularTrim` handles. A
  sphere's poles must survive the round-trip.

The format stays at v5 here — only the rebuild path and the singular-trim handling
change. The format work is the next slice.

Scope note: port the builder, do not adopt `compas_rhino`'s document schema
(`surface_type`, `uv_domain`, `frame`, its edge type set). The v6 format converges on
analytic types independently, with the OCC backend as the format's primary author.

## Acceptance criteria

- [x] `brep_to_rhino` builds faces through `AddSurface` / `Faces.Add` / `AddEdgeCurve` /
      `AddTrimCurve` / `Trims.Add`; `_trim_nurbs_surface_from_2d` and the `JoinBreps`
      stitch are gone
- [x] `JoinBreps`-era tolerance fudging is gone — the builder runs at `TOL.absolute`
- [x] `rhino_extract_topology` and `rhino_brep_to_data` no longer skip edgeless trims;
      the rebuild emits them via `Trims.AddSingularTrim`
- [x] Rhino round-trip of a boolean-cut cylinder preserves the trimmed wall face —
      face count matches and volume matches within `TOL`, where the rectangular-crop
      path did not
      <br>**Correction:** the old path already passed this case (7/7 faces, exact
      volume). A through-cut cylinder's wall *is* a rectangle in parameter space, so
      the rectangular crop was adequate for it. The filleted box is the case that
      actually discriminates — see below.
- [x] Rhino round-trip of a sphere preserves the pole trims; the rebuilt Brep reports
      `IsValid`
      <br>The writer now emits the 2 pole trims (`edge: -1` + `vertex`) and the rebuild
      restores them via `AddSingularTrim`. Note the old path also reported `IsValid`
      here — but only because `ToBrep()` regenerated an *untrimmed* sphere, so the
      dropped poles never showed up. Validity alone does not pin this; the trim count does.
- [x] Rhino round-trip of a filleted box preserves face count and volume within `TOL`
      <br>This is the criterion that caught the real defect: old path 26 → 18 faces,
      volume 7.563414 → 7.063681. New path 26 → 26, volume exact.
- [ ] `pytest -m rhino` passes on a machine with a Rhino license
      <br>**Not run as pytest.** This machine has no `rhinoinside`, so `-m rhino` skips
      every test. Instead all 47 Rhino-marked tests (24 serialization + 23 topology)
      were executed inside a live Rhino 8 via the LAMCP bridge, and all 47 pass.
      Leaving unchecked until a real `pytest -m rhino` run confirms it.
- [x] `pytest -m occ -q` still passes (no OCC regression) — 217 passed

## Blocked by

None - can start immediately.
