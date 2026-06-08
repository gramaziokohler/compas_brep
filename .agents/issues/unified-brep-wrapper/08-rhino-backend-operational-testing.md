## Parent

../../prd/unified-brep-wrapper.md

## What to build

Run a comprehensive end-to-end test of every supported Brep operation in the **Rhino backend**, executed live in Grasshopper/Rhino via the LAMCP bridge. Fix any bugs found. Also verify OCC↔Rhino serialization round-trips (a JSON payload produced by the OCC backend deserializes correctly in Rhino and vice versa using `compas.json_dumps` / `compas.json_loads`).

### Operations to test

**Group 1 — Primitives**: Box, Cylinder, Sphere, Cone, Torus  
**Group 2 — Booleans**: `+` (union), `-` (difference), `&` (intersection)  
**Group 3 — Queries**: `area`, `volume`, `centroid`, `aabb`, `is_solid`, `is_valid`  
**Group 4 — Topology**: `faces`, `edges`, `vertices`; `face.surface → NurbsSurface`, `edge.curve → NurbsCurve`, `vertex.point → Point`; caching by identity  
**Group 5 — Transforms**: `transform(T)`, `transformed(T)`, `flip()`  
**Group 6 — Modeling ops**: `trimmed(plane)`, `split(plane)`, `slice(plane)`, `fillet(r)`, `cap_planar_holes`, `fix`, `sew`, `make_solid`  
**Group 7 — I/O**: `to_step` / `from_step`, `to_viewmesh()`  
**Group 8 — Generators**: `from_extrusion`, `from_loft`, `from_sweep`, `from_pipe`, `from_mesh`, `from_native`  
**Group 9 — Serialization round-trips**: Rhino→JSON→Rhino, OCC→JSON→Rhino, Rhino→JSON→OCC (verify volume + face count)

## Acceptance criteria

- [ ] All Group 1–5 operations produce geometrically correct results (volumes, face counts, centroid) without raising
- [ ] All Group 4 topology properties return COMPAS types; caching confirmed by identity
- [ ] Group 6 modeling ops either succeed or raise `NotImplementedError` (no silent failures, no wrong type returns)
- [ ] Group 7 STEP round-trip volume within 1%; `to_viewmesh()` returns non-trivial mesh
- [ ] Group 8 generators produce `is_solid = True` or `is_valid = True` shapes
- [ ] Group 9: OCC→JSON payload deserializes in Rhino with matching volume; Rhino→JSON payload deserializes via `compas.json_loads` with matching volume
- [ ] No operation returns a `list` where a `Brep` is expected (fix the existing `_native_brep` error on list)
- [ ] All fixes committed; progress.txt updated

## Rhino Development Workflow

Grasshopper/Rhino is accessible via the **lamcp MCP server** (tools prefixed `mcp__lamcp__`).

After modifying library code, reinstall into the Rhino venv and reload:

```bash
~/.rhinocode/py39-rh8/python3.9 -m pip install . \
  --target ~/.rhinocode/py39-rh8/site-envs/compas_brep_occ-7LvK83j1 \
  --force-reinstall --no-deps --upgrade
```

Then call `mcp__lamcp__unload_python_modules` so Rhino picks up the new code. The Rhino-side venv is named `compas_brep_occ`.

## Blocked by

- 06-rhino-serialization-parity.md (already done)
