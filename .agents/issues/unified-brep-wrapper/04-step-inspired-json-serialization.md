## Parent

../../prd/unified-brep-wrapper.md

## What to build

Replace the current v3 JSON serialization format with a STEP-inspired JSON format written from the native backend object. No backward compatibility with v3 is required.

`Brep.__data__` asks the OCC backend to extract the Brep's geometry and topology as a JSON-serializable dict, encoding the same semantic entities that STEP uses — vertices (with 3D point coordinates), edges (with associated 3D curve data and start/end vertex references), faces (with associated surface data and orientation), loops (with ordered trim references), and trim curves (2D parameter-space curves). The encoding is COMPAS/JSON, not STEP syntax.

`Brep.__from_data__` decodes this dict and calls `brep_rebuild` (OCC implementation) to reconstruct the native `TopoDS_Shape`. After `brep_rebuild` returns, `_native_brep` is set and is the source of truth. No Python topology is retained from the deserialized dict — topology is populated lazily from native on first access as usual.

A backend is required for both serialization and deserialization. Attempting either without a backend raises `NotImplementedError` via the pluggable mechanism.

## Acceptance criteria

- [x] `brep.to_data()` / `json.dumps(brep.__data__)` produces a valid JSON dict with STEP-inspired entity structure
- [x] `Brep.__from_data__(data)` reconstructs a fully operational `Brep` (booleans, queries, tessellation all work)
- [x] Round-trip test: serialize a unit box → deserialize → volume matches, face count matches, topology accessible
- [x] Round-trip test: serialize a boolean-subtracted shape → deserialize → volume matches
- [x] Attempting deserialization without a backend raises `NotImplementedError`
- [x] No v3-format data is written; old `_deserialize_brep_data` code is removed
- [x] All `@pytest.mark.occ` serialization tests pass

## Blocked by

- 03-brep-thin-wrapper.md
