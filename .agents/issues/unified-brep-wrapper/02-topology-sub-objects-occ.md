## Parent

../../prd/unified-brep-wrapper.md

## What to build

Refactor the topology sub-objects — `BrepVertex`, `BrepEdge`, `BrepLoop`, `BrepFace`, `BrepTrim` — from Python data objects into native-handle wrappers for the OCC backend.

Each sub-object holds a reference to its corresponding native OCC entity. Properties such as `.point`, `.curve`, `.surface`, `.is_reversed` call into the native entity on demand and return COMPAS types (`Point`, `NurbsCurve`, `NurbsSurface`, etc.). Each property result is cached on the instance after first access so repeated calls do not re-enter the kernel.

Update `brep_extract_topology` (OCC implementation) to populate the topology lists on `Brep` with these wrapper objects rather than populated Python data objects. The topology lists remain lazily populated on first access.

`NurbsCurve` and `NurbsSurface` remain pure-Python value types. The OCC conversion functions in `backend/occ/conversion.py` handle the translation between native OCC curve/surface types and these value types at the boundary.

## Acceptance criteria

- [x] `BrepFace`, `BrepEdge`, `BrepVertex`, `BrepLoop`, `BrepTrim` each hold a native OCC handle as their primary state
- [x] `face.surface` returns a `NurbsSurface`; `edge.curve` returns a `NurbsCurve`; `vertex.point` returns a `Point`
- [x] Repeated property access returns the same object (identity check confirms caching)
- [x] No COMPAS type anywhere in the public interface is a backend type
- [x] All existing `@pytest.mark.occ` topology tests pass
- [x] `brep_extract_topology` (OCC) produces the new wrapper objects

## Blocked by

- 01-test-infrastructure.md
