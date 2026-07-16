# Rhino rebuild uses the low-level Brep builder, not surface `ToBrep()` + `JoinBreps`

## Status

accepted

## Decision

`brep_to_rhino` reconstructs faces through RhinoCommon's low-level Brep construction API —
`AddSurface`, `Faces.Add`, `AddEdgeCurve`, `AddTrimCurve`, `Trims.Add`,
`Trims.AddSingularTrim` — ported from `compas_rhino.geometry.brep.builder._RhinoBrepBuilder`.
It does not build faces by calling `ToBrep()` on a surface and stitching the results with
`JoinBreps`.

## Why

The `ToBrep()` + `JoinBreps` approach cannot represent a trimmed face. The v5 implementation
handled trims via `_trim_nurbs_surface_from_2d`, which read only the **endpoints** of each
2D trim curve, took their min/max to form a `(u, v)` bounding box, and called
`Surface.Trim(u_interval, v_interval)`. That is a rectangular parametric crop. Every face
whose boundary is not an axis-aligned rectangle in parameter space — every fillet, every
boolean-cut cylinder wall, every trimmed patch — was rebuilt as a rectangular sheet. The
pcurves were serialized faithfully and then discarded on read, making `curve_2d` write-only
on the Rhino side.

The builder also removes two workarounds that were symptoms of the same cause:

- **Tolerance fudging.** `JoinBreps` was called with a hand-tuned `1e-6` rather than
  `TOL.absolute`, with a comment noting that the tighter tolerance left edges unjoined.
  The builder shares edges by index instead of rediscovering them by proximity, so there is
  nothing to fudge.
- **Dropped singular trims.** `rhino_extract_topology` skipped trims with no edge ("singular
  trim (e.g. at pole of sphere) — skip"), which is precisely what `Trims.AddSingularTrim`
  exists to handle. A sphere's poles could not survive a round-trip.

## Why porting rather than writing fresh

`compas_rhino`'s builder is proven, shipped code from one of the two libraries this project
exists to consolidate. Reimplementing it — worse — was not a decision anyone made; it is
what happened. The builder additionally mirrors OCC's `BRepBuilderAPI` structure, so after
the port both backends' rebuild paths are structurally symmetric, which makes the exchange
contract legible from either side.

## Consequences

- The builder requires a pcurve for every trim, which is why v6 makes `curve_2d`
  non-nullable (see ADR-0001). A writer that cannot produce a pcurve raises rather than
  emitting `null`.
- `compas_rhino`'s richer document schema (`surface_type`, `uv_domain`, `frame`, and
  `line/circle/ellipse/arc/nurbs` edge types) was **not** adopted wholesale — only the
  builder. The v6 format converges on the analytic edge and surface types independently,
  keeping the OCC backend as the format's primary author rather than making compas_brep's
  format a derivative of compas_rhino's.
