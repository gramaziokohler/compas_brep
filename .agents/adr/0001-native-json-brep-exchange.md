# Rhino↔OCC Brep exchange via native COMPAS JSON, not STEP

## Status

accepted

## Decision

Brep exchange between the Rhino and OCC backends happens through the native COMPAS JSON
document (`Brep.__data__` / `Brep.__from_data__`), not through STEP import/export. The
document is a **file/wire handoff**: one backend is live per process, the JSON crosses a
file or network boundary, and the receiving process rebuilds a native shape with its own
kernel. Both kernels are never required in one process, so no runtime backend-selection
API is needed.

The bar for a successful exchange is **representational fidelity**: a cylinder that leaves
Rhino must arrive at OCC as a `CylindricalSurface`, not as a NURBS approximation of one.
Geometric equivalence (matching volume/area within tolerance) is not sufficient, because
downstream kernel operations — fillets, booleans, `IsValid` checks — behave measurably
differently on analytic surfaces than on their NURBS approximations.

## Why not STEP

STEP already round-trips geometry between the kernels and is already implemented on both
backends (`to_step` / `from_step`). It is retained as the file-level interop path for
third-party CAD. It is rejected as the *internal* exchange mechanism because:

- It requires a filesystem round-trip through a kernel-specific reader/writer, so the
  exchanged data is whatever each kernel's STEP translator chose to emit — the project
  controls neither the fidelity nor the failure modes.
- The Rhino STEP path writes through `RhinoDoc.ActiveDoc` and must be marshalled to the
  UI thread (see `backend/rhino/io.py`), which makes it unusable from a headless or
  worker context.
- It cannot carry COMPAS-native semantics, and the project's purpose is a COMPAS-native
  Brep interface.

## Why the format is explicit (v6)

v5 encoded loop role **positionally** — `occ_rebuild` treated `loops[0]` as the outer loop
and the rest as inner — while neither writer guaranteed that ordering. This is the class of
bug that a format should make unrepresentable rather than rely on every backend
independently honoring an undocumented convention. v6 tags each loop `"outer" | "inner"`
explicitly and makes `curve_2d` non-nullable.

## Consequences

- **No silent degradation.** A backend that meets a surface or curve type it cannot
  represent raises `BrepError`. This extends the precedent already set by OCC's
  `_extract_surface`, which raises rather than returning dummy geometry. The cost is that
  an exotic surface produces a hard error instead of an approximation — accepted, because
  the alternative is what allowed OCC→Rhino to silently drop every analytic face.
- **Deserialization always requires a backend.** There is no display-only Brep. A consumer
  without a kernel should be sent a `Mesh`, not a `Brep`. The `cache_tessellation` flag and
  its "serialized for backendless transit" documentation described a capability that was
  never wired and contradicted this decision; both are removed.
- **CI cannot verify the Rhino half.** CI has no Rhino license, and `-m 'not rhino'` skips
  Rhino tests by default even locally. The exchange contract is therefore pinned by
  committed Rhino-authored JSON fixtures that OCC tests read on CI, plus Rhino-marked tests
  that regenerate the fixtures and assert they still match. Live tests alone were rejected:
  a test that only runs on one laptop is what let `test_rhino_serialization.py` keep
  asserting `version == 4` long after the writer moved to 5.
