# Plan: Multi-Context Scene Objects

## Goal

Make `compas_brep` geometry (`Brep`, `NurbsCurve`, `NurbsSurface`) drawable in **multiple
visualization contexts**, not just `compas_viewer`. Add a **Rhino** context now; leave a clean
seam for **Blender** later. The hard constraint: each context depends on libraries that are *not
importable in other environments* (`compas_viewer` is absent inside Rhino; `Rhino`/`scriptcontext`
are absent in a headless OCC + viewer setup). The package must import cleanly everywhere and only
pull in a context's dependencies when that context is actually live.

## Background — how COMPAS scene registration works

- `compas.scene` keeps a registry `ITEM_SCENEOBJECT[context][item_type] = sceneobject_type`.
- Contexts are the string keys `"Viewer"`, `"Rhino"`, `"Grasshopper"`, `"Blender"` (and `None` for
  the base/context-agnostic objects). `detect_current_context()` picks one at runtime.
- Registration happens through the **pluggable** `register_scene_objects` (selector
  `collect_all`): COMPAS imports every module listed in a package's `__all_plugins__`, then calls
  *all* discovered `@plugin(category="factories")` implementations. Each one is gated by
  `requires=[...]` — it is skipped unless those modules import successfully.
- `compas_brep.__init__.__all_plugins__` already lists `"compas_brep.scene"`, so
  `compas_brep/scene/__init__.py` is imported in **every** environment. **Its module top level must
  never import a context library.**

Reference pattern (from `compas_rhino/scene/`): a `@plugin(category="factories", requires=["Rhino"])`
function calls `register(SomeType, SomeRhinoObject, context="Rhino")`, and each Rhino scene object
subclasses `RhinoSceneObject, GeometryObject` and implements `.draw()` that bakes native geometry
into `scriptcontext.doc`.

## Current state

```
src/compas_brep/scene/
  __init__.py          # one @plugin requires=["compas_viewer"], registers the 3 types -> context "Viewer"
  brepobject.py        # imports compas_viewer at MODULE TOP LEVEL
  curveobject.py       # imports compas_viewer at MODULE TOP LEVEL
  surfaceobject.py     # imports compas_viewer at MODULE TOP LEVEL
```

This works today only because `register_scene_objects` imports the three object modules *lazily
inside the function body*, so `compas_viewer` is touched only when the `requires` gate has already
passed. The arrangement is correct but flat — there is no separation by context, and adding Rhino
objects to this same directory would mix `compas_viewer` and `scriptcontext` imports in one
namespace.

## Target structure

Split scene objects into one subpackage per context. Each subpackage is free to import its own
context library at top level, because it is only ever imported from inside a `requires`-gated
registration function.

```
src/compas_brep/scene/
  __init__.py              # context-agnostic; declares one gated @plugin per context. NO heavy imports.
  viewer/
    __init__.py            # re-exports the three viewer objects
    brepobject.py          # (moved) imports compas_viewer
    curveobject.py         # (moved)
    surfaceobject.py       # (moved)
  rhino/
    __init__.py            # re-exports the three rhino objects
    brepobject.py          # imports scriptcontext / Rhino; bakes into doc
    curveobject.py
    surfaceobject.py
  # blender/  -> future, same shape
```

### `scene/__init__.py`

Holds one registration plugin per context, each gated by `requires`. No top-level context imports;
all object-class imports stay lazy inside the function bodies (same discipline as today).

```python
from compas.plugins import plugin
from compas.scene import register


@plugin(category="factories", requires=["compas_viewer"])
def register_scene_objects_viewer():
    from compas_brep.brep import Brep
    from compas_brep.curves.nurbs import NurbsCurve
    from compas_brep.surfaces.nurbs import NurbsSurface
    from compas_brep.scene.viewer import BrepObject, NurbsCurveObject, NurbsSurfaceObject

    register(Brep, BrepObject, context="Viewer")
    register(NurbsCurve, NurbsCurveObject, context="Viewer")
    register(NurbsSurface, NurbsSurfaceObject, context="Viewer")


@plugin(category="factories", requires=["Rhino"])
def register_scene_objects_rhino():
    from compas_brep.brep import Brep
    from compas_brep.curves.nurbs import NurbsCurve
    from compas_brep.surfaces.nurbs import NurbsSurface
    from compas_brep.scene.rhino import RhinoBrepObject, RhinoNurbsCurveObject, RhinoNurbsSurfaceObject

    register(Brep, RhinoBrepObject, context="Rhino")
    register(NurbsCurve, RhinoNurbsCurveObject, context="Rhino")
    register(NurbsSurface, RhinoNurbsSurfaceObject, context="Rhino")
```

Notes:
- The `collect_all` selector means COMPAS calls *both* registration functions; each independently
  no-ops if its `requires` is unmet. The two contexts never collide in the registry (different keys).
- `requires=["Rhino"]` is the same gate `compas_rhino` and `compas_brep.backend.rhino.plugins` use,
  so it is true both inside Rhino and under `rhinoinside`.
- `drawing-utils` plugins (`clear`, `before_draw`, `after_draw`) are **already provided** by
  `compas_rhino` (Rhino) and `compas_viewer` (Viewer). We do not re-declare them.

### `scene/viewer/` — moved, not rewritten

Move the three existing files unchanged (only fixing their own intra-package imports if any) into
`scene/viewer/` and re-export them from `scene/viewer/__init__.py`. Behavior is identical to today.

### `scene/rhino/` — new

Each object subclasses `RhinoSceneObject, GeometryObject` and implements `.draw()` that bakes a
native Rhino object into `scriptcontext.doc`, mirroring `RhinoBrepObject` in `compas_rhino`.

Conversion to native Rhino geometry reuses the helpers that already exist in the Rhino backend
(`src/compas_brep/backend/rhino/conversion.py`):
- `Brep` → `brep_to_rhino(brep)` returns the underlying `Rhino.Geometry.Brep`. It returns the
  cached `_native_brep` when present (Rhino backend active) and otherwise rebuilds the Rhino brep
  from the wrapper's faces/surfaces/loops — i.e. it already covers the cross-backend case.
- `NurbsSurface` → `_compas_nurbs_surface_to_rhino(surface)`.
- `NurbsCurve` → `_compas_nurbs_curve_to_rhino(curve)`.

`brep_to_rhino` is already public. The two nurbs converters are private (`_`-prefixed) today.
Decision: **promote the two nurbs converters to public names** (e.g. `nurbs_surface_to_rhino`,
`nurbs_curve_to_rhino`) in `backend/rhino/conversion.py` and have the scene objects import those,
so scene code does not reach into private backend internals.

Sketch (`scene/rhino/brepobject.py`):

```python
import scriptcontext as sc  # type: ignore

from compas.scene import GeometryObject
from compas_rhino.conversions import transformation_to_rhino
from compas_rhino.scene.sceneobject import RhinoSceneObject

from compas_brep.backend.rhino.conversion import brep_to_rhino


class RhinoBrepObject(RhinoSceneObject, GeometryObject):
    """Scene object for baking a compas_brep Brep into the Rhino document."""

    def draw(self):
        attr = self.compile_attributes()
        geometry = brep_to_rhino(self.geometry)
        geometry.Transform(transformation_to_rhino(self.worldtransformation))
        self._guids = [sc.doc.Objects.AddBrep(geometry, attr)]
        return self.guids
```

`RhinoNurbsCurveObject.draw()` → `sc.doc.Objects.AddCurve(...)`;
`RhinoNurbsSurfaceObject.draw()` → `sc.doc.Objects.AddSurface(...)`. Same `compile_attributes()` +
`worldtransformation` flow.

## Why this separation is the right shape

- **Import safety is structural, not incidental.** Today's safety relies on remembering to keep the
  three object imports lazy. After the split, a whole context's heavy imports live behind its own
  package boundary and are only reached through a `requires`-gated function — the failure mode
  (importing `scriptcontext` in a viewer-only env) becomes impossible by construction.
- **Adding Blender is a copy of the Rhino seam:** new `scene/blender/` subpackage + one more
  `@plugin(requires=["bpy"])` in `scene/__init__.py`. No churn to existing contexts.
- **Conversions are not duplicated:** the Rhino scene objects reuse the backend's existing
  compas↔Rhino converters rather than reimplementing NURBS marshaling.

## Edge cases / open questions

- **Cross-backend draw in Rhino.** If a `Brep` was built on the OCC backend but drawn inside Rhino,
  `brep_to_rhino` already rebuilds a Rhino brep from the wrapper's faces/surfaces/loops (verified in
  `conversion.py`). Primary path — Rhino backend active in Rhino — is a cached no-op pass-through.
  Worth a `@pytest.mark.rhino` test to confirm the OCC-built → Rhino-drawn path is well-behaved.
- **Grasshopper context.** `detect_current_context()` distinguishes `"Grasshopper"` from `"Rhino"`.
  If GH display is wanted, add a separate `register(..., context="Grasshopper")` returning the raw
  native geometry instead of baking. Out of scope for this pass unless desired.
- **`worldtransformation` on NURBS value types.** Curve/surface converters produce fresh Rhino
  geometry each draw; applying the transform on the native object (as in the Brep path) is fine.

## Work breakdown

1. Create `scene/viewer/`; move `brepobject.py`, `curveobject.py`, `surfaceobject.py` into it;
   add `scene/viewer/__init__.py` re-exporting the three classes.
2. Promote `_compas_nurbs_surface_to_rhino` / `_compas_nurbs_curve_to_rhino` to public names in
   `backend/rhino/conversion.py` (keep private aliases if anything internal uses them).
3. Create `scene/rhino/` with `brepobject.py`, `curveobject.py`, `surfaceobject.py` and an
   `__init__.py` re-exporting them.
4. Rewrite `scene/__init__.py` to declare the two `requires`-gated registration plugins; keep all
   object-class imports lazy inside the functions; no context imports at module top level.
5. Update `CONTEXT.md` "Key Files" to describe `scene/viewer/`, `scene/rhino/`, and the
   per-context registration scheme.

## Testing / verification

- **Import safety (CI, no Rhino):** `import compas_brep` and `import compas_brep.scene` must
  succeed; `register_scene_objects_rhino`'s `requires` gate keeps `scriptcontext` untouched.
  Add a test asserting `compas_brep.scene` imports without `compas_viewer` or `Rhino` present.
- **Viewer parity:** existing viewer behavior is unchanged (files moved, not edited) — a smoke
  import of `compas_brep.scene.viewer` confirms it.
- **Rhino (`@pytest.mark.rhino`, local only):** build a `Brep`/`NurbsCurve`/`NurbsSurface`, run the
  registered scene object's `.draw()` via the lamcp Rhino bridge, assert a GUID is returned and the
  object lands in the document. Not run in CI (no Rhino license).
```
