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

- [ ] Both writers emit `"version": 6` and tagged loops
      (`{"type": "outer"|"inner", "trims": [...]}`)
- [ ] Both readers select the outer loop by tag, not by position; a face with zero or
      multiple outer loops raises `BrepError`
- [ ] Reordering the `loops` array of a v6 document does not change the rebuilt shape
      (the test that makes positional decoding unrepresentable)
- [ ] `curve_2d` is never `null` in a v6 document; a writer that cannot produce a
      pcurve raises `BrepError`
- [ ] The `is not None` pcurve branches are gone from both rebuild paths
- [ ] A v5 document still deserializes (positional outer-loop fallback, confined to the
      v5 read path); the existing v4 read test still passes
- [ ] An inner loop (box with a through-hole) round-trips on both backends with the
      hole intact — face count and volume within `TOL`
- [ ] `pytest -m occ -q` passes; `pytest -m rhino` passes on a licensed machine

## Blocked by

- 01-rhino-rebuild-via-brep-builder.md
