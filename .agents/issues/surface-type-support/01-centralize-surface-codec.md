## Parent

../../surface-type-support-plan.md

## What to build

Collapse the duplicated surface `{"type", "data"}` encode/decode logic into a
single backend-neutral codec, so that adding new surface types later touches one
place instead of five.

Today the dispatch on the surface `"type"` tag (`"plane"` / `"nurbs"`) is
hand-rolled in five sites: the serialize side in `BrepFace.__data__`, the OCC
`occ_brep_to_data`, and the Rhino conversion; and the deserialize side in the OCC
`occ_rebuild` and the Rhino operations. Replace all of them with calls to a
shared `surface_to_data(surface) -> dict` / `surface_from_data(data) -> surface`
pair, re-exported from the 2nd-level `compas_brep.surfaces` package per the
import-depth rule.

Encoding stays `{"type": <tag>, "data": <payload>}`. `Plane` keeps its existing
hand-rolled `{"point", "normal"}` payload so existing files still load; the
codec is structured so analytic types can be added later via their COMPAS
`__data__`/`__from_data__` round-trip. Bump the serialization `"version"` to 5,
and ensure `surface_from_data` still reads v4 documents (which only ever contain
`"plane"` and `"nurbs"`).

This slice introduces no new surface types and no behavior change — it is a pure
refactor gated by the existing test suite.

## Acceptance criteria

- [x] `surface_to_data` / `surface_from_data` exist and are importable from
      `compas_brep.surfaces`
- [x] `BrepFace.__data__`, OCC `occ_brep_to_data`, Rhino conversion, OCC
      `occ_rebuild`, and Rhino operations all delegate to the shared codec
- [x] Serialized format reports `"version": 5`
- [x] A stored v4 JSON document (plane + nurbs only) still deserializes correctly
- [x] `json_loads(json_dumps(brep))` is geometrically identical to before for
      plane and nurbs faces
- [x] All existing `@pytest.mark.occ` tests pass

## Blocked by

- None - can start immediately
