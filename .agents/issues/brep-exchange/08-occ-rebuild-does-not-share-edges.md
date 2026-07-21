## Parent

../../adr/0001-native-json-brep-exchange.md

## Status

Fixed 2026-07-21. First flagged (without a dedicated issue) in slice 02's progress
notes, referenced again by slices 03 and 06 as an unowned defect. Reproduced here
with new, sharper evidence on 2026-07-21: it is not just a seam-invalidity /
edge-count drift, it is an **unstable round trip that destroys the shape**.

## What's broken

`Brep.__from_data__(document).__data__` is not idempotent for the OCC backend.
Every call re-extracts topology from a freshly rebuilt native `TopoDS_Shape`
rather than passing the document's connectivity through, and the rebuild
(`brep_to_occ` / `_edge_to_occ_edge` in `src/compas_brep/backend/occ/conversion.py`)
builds each face's edges independently — minting fresh vertices/edges per face
rather than sharing a common vertex/edge table. Two consecutive round trips are
enough to collapse a real solid into a degenerate point.

Reproduction (`tests/fixtures/occ_cone.json`, no `compas.data` involved — plain
dicts throughout, to rule out the JSON layer entirely):

```python
import json
from compas_brep import Brep

raw = json.load(open("tests/fixtures/occ_cone.json"))
print(len(raw["vertices"]), len(raw["edges"]), len(raw["faces"]))     # 2 3 2

brep1 = Brep.__from_data__(raw)
data1 = brep1.__data__
print(len(data1["vertices"]), len(data1["edges"]), len(data1["faces"]))  # 4 2 2

brep2 = Brep.__from_data__(data1)
data2 = brep2.__data__
print(len(data2["vertices"]), len(data2["edges"]), len(data2["faces"]))  # 1 1 1
print(brep2.volume)                                                      # 0.0

brep3 = Brep.__from_data__(data2).__data__                               # 1 1 1, stays there
```

So the sequence is: `V2 E3 F2 (source doc)` → `V4 E2 F2` (hop 1) → `V1 E1 F1`,
volume `0.0` (hop 2) → `V1 E1 F1` (hop 3, a stable fixed point — it doesn't degrade
further, but it never recovers). A real cone with a real volume is destroyed by two
ordinary round trips through the format that exists specifically to carry it
between backends losslessly.

This was found via `compas.data.json_dump`/`json_load` (which chains exactly two
of these hops: dump calls `__data__`, load calls `__from_data__`), and initially
looked like a `compas.data` serialization bug. It is not — confirmed by reproducing
the identical degradation with plain `json.load`/`Brep.__from_data__`/`.__data__`
and zero `compas.data` machinery anywhere in the chain (see reproduction above).
The bug is entirely in the OCC rebuild/re-extract cycle.

## Why this is worse than previously scoped

Prior mentions of this defect described it as:
- Slice 02: an inner-loop / face-orientation defect on a holed box (fixed
  separately at the time; the edge-sharing note was about *seam invalidity*).
- Slice 03: "the 48->32 edge collapse" on a filleted box during sewing — read as
  an edge-count drift, not full topological collapse.
- Slice 06: "causes the seam invalidity... needs a shared vertex/edge table in
  brep_to_occ" — again framed as an invalidity/seam problem, checked via
  `BRepCheck_Analyzer`, not as something that compounds under repetition.

None of those observations involved re-running the rebuild more than once, so
none of them caught that the defect is a **positive-feedback instability**: each
rebuild's connectivity loss becomes the input to the next rebuild, and it
converges to total collapse rather than to some stable, merely-imperfect state.
Any code path that round-trips an OCC-backed `Brep` through its own document
format more than once — including, unexpectedly, ordinary `compas.data.json_dump`
/ `json_load` — is exposed to this, not just the cross-backend (Rhino↔OCC) paths
the earlier slices were testing.

## Suggested starting point

A shared vertex/edge table in `brep_to_occ` (`src/compas_brep/backend/occ/conversion.py`),
so that two faces referencing the same document edge/vertex index get the *same*
native `TopoDS_Edge`/`TopoDS_Vertex` rather than each minting their own — this was
the fix direction slice 06 already pointed at from the seam-invalidity angle, and
it's plausible it's the same fix that closes this issue too. Worth confirming
directly: instrument `_edge_to_occ_edge` to check whether the cone's 3 document
edges are being rebuilt as 3 distinct native edges that don't get sewn back
together, versus something else (e.g. `BRepBuilderAPI_Sewing`'s tolerance merging
near-coincident-but-unshared vertices from the previous lossy rebuild into one).

## Acceptance criteria

- [x] `Brep.__from_data__(doc).__data__` is idempotent for every committed OCC
      fixture: a second round trip through the same document produces the same
      vertex/edge/face counts and the same volume (within `TOL`) as the first.
- [x] The `occ_cone.json` reproduction above stays at `V2 E3 F2`-equivalent
      connectivity (or an intentionally-documented, stable equivalent) across at
      least 3 consecutive round trips, and volume never drops to `0.0`.
- [x] `compas.data.json_dump(brep, path)` followed by `compas.data.json_load(path)`
      preserves face count and volume for every OCC-authored analytic fixture.
