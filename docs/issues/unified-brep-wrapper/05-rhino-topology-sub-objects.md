## Parent

../../prd/unified-brep-wrapper.md

## What to build

Apply the native-handle wrapper pattern to the Rhino backend. Update `brep_extract_topology` (Rhino implementation) to populate topology lists with native-handle wrapper objects — the same `BrepVertex`, `BrepEdge`, `BrepLoop`, `BrepFace`, `BrepTrim` classes used by OCC, but holding `Rhino.Geometry` handles instead of OCC handles.

Audit the Rhino backend's pluggable coverage against the full list of `@pluggable` declarations in `compas_brep.operations`. For any pluggable that has an OCC implementation but no Rhino implementation, either implement it or add an explicit `NotImplementedError` stub with a comment. No silent gaps.

Add a `@pytest.mark.rhino` test module that mirrors the OCC topology tests: verify that `face.surface` returns `NurbsSurface`, `edge.curve` returns `NurbsCurve`, `vertex.point` returns `Point`, and that caching works by identity check.

## Acceptance criteria

- [x] `brep_extract_topology` (Rhino) produces native-handle wrapper objects
- [x] `face.surface`, `edge.curve`, `vertex.point` return COMPAS types when using the Rhino backend
- [x] Repeated property access returns the same cached object (identity check)
- [x] Every `@pluggable` in `compas_brep.operations` has an explicit Rhino entry (implementation or documented stub)
- [x] `pytest -m rhino` topology tests pass on a machine with `rhinoinside` installed
- [x] No Rhino types appear in any public interface return value

## Blocked by

- 02-topology-sub-objects-occ.md
