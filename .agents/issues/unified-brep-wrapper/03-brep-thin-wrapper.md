## Parent

../../prd/unified-brep-wrapper.md

## What to build

Remove Python-owned topology as canonical state from `Brep`. After this slice, `_native_brep` is the only source of truth — the topology lists (`_vertices`, `_edges`, `_loops`, `_faces`) are purely a lazy cache populated from native on first access, never written to as authoritative data.

Concretely: remove any code path that treats the Python topology lists as the primary representation (e.g. constructors or operations that populate topology lists without going through native, the `_topology_loaded` flag semantics that gate on Python data being present). The `_ensure_topology` mechanism stays but its only job is to populate wrapper caches from native via `brep_extract_topology` — it does not fall back to Python-owned data.

Operations that previously returned a `Brep` by building up Python topology directly must instead return a `Brep` whose `_native_brep` is set and whose topology is populated lazily from that native object.

All existing OCC tests must continue to pass.

## Acceptance criteria

- [x] `Brep` has no constructor or operation that sets topology lists as canonical state without a native object present
- [x] `_ensure_topology` only populates caches from `_native_brep` via `brep_extract_topology`
- [x] A `Brep` with no `_native_brep` has empty topology lists — it does not fall back to Python-owned data
- [x] All `@pytest.mark.occ` tests pass
- [x] No public method or property returns a backend type

## Blocked by

- 02-topology-sub-objects-occ.md
