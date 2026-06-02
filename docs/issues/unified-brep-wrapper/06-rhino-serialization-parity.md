## Parent

../../prd/unified-brep-wrapper.md

## What to build

Implement `brep_rebuild` for the Rhino backend so that STEP-inspired JSON round-trips through the Rhino backend. After this slice, a `Brep` serialized in an OCC environment can be deserialized in a Rhino environment (and vice versa), because the JSON format is backend-agnostic and both backends can reconstruct a native object from it.

Add a `@pytest.mark.rhino` serialization test module that mirrors the OCC serialization tests: round-trip a unit box and a boolean-subtracted shape, verify volume and face count match.

## Acceptance criteria

- [x] `brep_rebuild` (Rhino) reconstructs a native `Rhino.Geometry.Brep` from STEP-inspired JSON
- [x] Round-trip test (Rhino): serialize a unit box → deserialize → volume matches, face count matches
- [x] Round-trip test (Rhino): serialize a boolean-subtracted shape → deserialize → volume matches
- [x] A JSON payload produced by the OCC backend deserializes correctly via the Rhino backend
- [x] `pytest -m rhino` serialization tests pass on a machine with `rhinoinside` installed

## Blocked by

- 04-step-inspired-json-serialization.md
- 05-rhino-topology-sub-objects.md
