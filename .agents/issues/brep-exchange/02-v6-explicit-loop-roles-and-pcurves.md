## Parent

../../adr/0001-native-json-brep-exchange.md

## What to build

Bump the exchange document to v6 and make two things that were previously implied
explicit: loop role and pcurve presence. Both backends read and write the new shape.

**Loop role.** v5 encodes role positionally — `occ_rebuild` treats `loops[0]` as the
outer loop and the rest as inner — while neither writer guarantees that ordering. The
Rhino writer emits loops as bare trim lists in `rf.Loops` order. A loop becomes:

```json
{"type": "outer" | "inner", "trims": [...]}
```

Position stops being load-bearing. Readers use the tag; a document with no outer loop
on a face, or more than one, is an error rather than a silent guess.

**Pcurve.** `curve_2d` becomes non-nullable. Today the Rhino writer emits
`"curve_2d": null` whenever `_extract_trim_pcurve` returns `None`, and OCC's rebuild
branches on `t.curve_2d is not None` to decide whether it can build a trimmed face at
all. A writer that cannot produce a pcurve now raises `BrepError` instead of emitting
`null`, and the readers drop their None-handling branches. This is what the ported
builder (slice 1) needs: it requires a pcurve for every trim.

Version goes to 6 in both writers. The surface codec continues to read v4, v5, and v6
transparently — a v5 document still loads, with `loops[0]` interpreted as outer for
backward compatibility, and that positional fallback is confined to the v5 read path.

## Acceptance criteria

- [x] Both writers emit `"version": 6` and tagged loops
      (`{"type": "outer"|"inner", "trims": [...]}`)
      <br>OCC tags by `BRepTools.OuterWire_s`; Rhino by `BrepLoopType`. Rhino's other
      loop types (Slit, Curveonsurface, Ptonsurface, Unknown) raise rather than being
      mapped onto a role they don't have.
- [x] Both readers select the outer loop by tag, not by position; a face with zero or
      multiple outer loops raises `BrepError`
- [x] Reordering the `loops` array of a v6 document does not change the rebuilt shape
      (the test that makes positional decoding unrepresentable)
      <br>The test asserts the reversal actually moves an outer loop off index 0, so it
      cannot pass against a positional reader.
- [x] `curve_2d` is never `null` in a v6 document; a writer that cannot produce a
      pcurve raises `BrepError`
      <br>Measured first: OCC and Rhino both already emit a pcurve for every trim of a
      box / holed box / sphere, so this cost nothing at either writer.
- [x] The `is not None` pcurve branches are gone from both rebuild paths
      <br>OCC's `_build_trimmed_face` fallback (`all_have_pcurves` → domain-bounded or
      untrimmed face) and Rhino's two None-guards are gone. The one surviving None is
      the v4/v5 legacy concession, confined to `exchange.trim_pcurve_from_data`.
- [x] A v5 document still deserializes (positional outer-loop fallback, confined to the
      v5 read path); the existing v4 read test still passes
      <br>Non-nullability is a property of **v6 documents**, not of the reader: the
      committed v4 fixture is planar-only with `curve_2d: null` throughout, so enforcing
      it retroactively would have broken the v4 read test this slice must keep passing.
- [x] An inner loop (box with a through-hole) round-trips on both backends with the
      hole intact — face count and volume within `TOL`
      <br>This did **not** work before, on OCC, and the fix is the substance of the
      slice — see the note below on the hole that added volume instead of removing it.
- [ ] `pytest -m occ -q` passes; `pytest -m rhino` passes on a licensed machine
      <br>`pytest -m occ -q`: **227 passed**. `pytest -m rhino`: **not run as pytest** —
      no `rhinoinside` here, and `-m 'not rhino'` skips it by default anyway. All 53
      Rhino-marked tests were executed inside a live Rhino 8 via the LAMCP bridge and
      all 53 pass, but that is not a pytest run, so this box stays unchecked.

## Blocked by

- 01-rhino-rebuild-via-brep-builder.md

## Notes from implementation

**The inner-loop criterion caught a real defect, and it was not in the format.**
A box with a through-hole never round-tripped on OCC: volume 7.434513 → 7.623009,
and the restored shape was invalid. Measured against the pre-slice code, the numbers
are identical, so this predates v6 — the AC is what surfaced it.

The cause: a planar face is rebuilt from its **3D wires**, and a 3D wire's winding
says nothing about whether it is a hole. OCC reads that from wire orientation, and
`BRepBuilderAPI_MakeFace(face, wire)` adds a wire without reorienting it. One of the
two holed faces got an inner wire winding with its outer wire, so OCC *added* the
hole's area (4.283 = 4 + π·0.3²) instead of subtracting it (3.717 = 4 − π·0.3²). Only
one of the two failed, which is why a symmetric shape hid it: the top and bottom faces
have opposite orientations. `ShapeFix_Face.FixOrientation` now settles each wire's role.
Volume delta after the fix: 4.5e-08.

**Why not just use the pcurves for planar faces too?** That would dissolve the whole
3D-wire path, and it is what slice 01's note anticipated — but it still doesn't work.
`Plane.__data__` is point + normal, which pins no x-axis, so a reader re-deriving the
plane picks an arbitrary UV frame and the serialized pcurve lands somewhere else
entirely. Planar pcurves remain write-only: OCC ignores them, Rhino re-derives its own
by projection. v6 makes them non-nullable but not yet *meaningful* — closing that needs
the plane's frame pinned in the document, which ADR-0002 explicitly declined.

## Known defect, not this slice

A cylinder loses its **seam edge** on rebuild and the result reports invalid — a plain
cylinder goes 3 edges → 2, `BRepCheck_Analyzer` says invalid; the holed box goes 15 → 14.
Verified as pre-existing (identical before this slice) and not covered by any criterion
here: face count and volume are both unaffected, which is exactly why it has survived.
Slice 06 (analytic edge tags) touches seam curves and is the natural place for it.
