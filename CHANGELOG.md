# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

* Added a [cross-backend exchange gaps](docs/cross-backend-gaps.md) page, including why STEP is not used as the exchange path and one gap still open.

### Changed

* Fixed `Brep.from_polygons` and `Brep.from_mesh` triangulating any face with more than four vertices on the Rhino backend, and returning a shell Rhino would not call a solid: a hexagonal plate came back with 18 faces instead of 8. The backend now builds one Brep face per mesh face and joins them, as OCC already did; a non-planar face with more than four vertices raises `BrepError`.
* Fixed cross-backend exchange producing kernel-invalid Breps: a reversed face's orientation was composed into its trims by the writer and applied again by the reader, and a u-mirrored face's wire winding was left uncorrected.
* Fixed pcurves being written over a parameter interval their edge no longer had, after the receiving kernel silently reparameterized it. An edge's forward-increasing interval is now a rule of the exchange format.
* Changed `brep_to_occ` to raise `BrepInvalidError` when the kernel calls a rebuilt shape invalid, instead of letting it surface at a later operation.
* Changed the boolean operations (`Brep.from_boolean_difference`, `from_boolean_union`, `from_boolean_intersection`, `from_boolean_union_multi`) to return `list[Brep]`, one Brep per resulting piece. A subtraction can cut a shape into disconnected pieces, and both backends now report all of them: the Rhino backend kept only `results[0]` and silently dropped the rest, and the OCC backend returned the pieces still wrapped in the `TopAbs_COMPOUND` that `BRepAlgoAPI` always produces. The `-`, `+` and `&` operators return `list[Brep]` too, for consistency, so they no longer chain — `a + b + c` is now `Brep.from_boolean_union_multi(a, b, c)`.

### Removed


## [0.2.2] 2026-08-24

### Added

### Changed

* Added missing version selector in docs.

### Removed


## [0.2.1] 2026-08-24

### Added

### Changed

* Fixed release workflow dependency issue.

### Removed


## [0.2.0] 2026-08-24

### Added

* Added cross-backend Brep exchange: a Brep serialized by one backend (Rhino or OCC) now deserializes on the other with representational fidelity — analytic surfaces (cylinder, cone, sphere, torus) and edge curves (circle, arc, ellipse) round-trip as their exact analytic type rather than a NURBS approximation. See [ADR-0001](.agents/adr/0001-native-json-brep-exchange.md).
* Bumped the exchange document to v6: loop role (`outer`/`inner`) is now explicit rather than positional, and every trim carries a non-nullable pcurve — both close gaps that let one backend silently misread the other's document.
* Added a low-level Rhino Brep builder (`backend/rhino/builder.py`) so a genuinely trimmed face rebuilds as trimmed rather than through Rhino's lossy high-level surface API. See [ADR-0002](.agents/adr/0002-rhino-rebuild-via-brepbuilder.md).
* Added `BrepFace.boundary` and `BrepFace.holes`, and `BrepLoop.is_outer`, `BrepLoop.is_inner` and `BrepLoop.loop_type` along with the `LoopType` constants. Loops are tagged as outer/inner by the face that owns them.
* Added `BrepFace.frame_at(u, v)` and `BrepFace.normal_at(u, v)`, which account for `BrepFace.is_reversed` so that opposite faces of a solid report opposite normals. `BrepFace.surface` is unchanged and still returns the raw, unflipped underlying surface.
* Added `BrepFace.nurbssurface` and `BrepFace.native_face`, converting the underlying surface of a backend-backed face to a `NurbsSurface` via the new `face_to_nurbssurface` pluggable, for compatibility with `compas.geometry.BrepFace`.
* Added `BrepEdge.start_vertex` and `BrepEdge.end_vertex` as aliases of `first_vertex`/`last_vertex`, plus `BrepEdge.type`, `BrepEdge.centroid`, `BrepFace.is_bspline` and `BrepFace.type`.

### Changed

* Changed `BrepEdge.to_line` to drop a dead branch; it returns the chord between the edge's two vertices, for linear and non-linear edges alike, matching `compas_occ`.

### Removed

## [0.1.4] 2026-07-09

### Added

### Changed

* Fixed Brep with negative volume is masked by the `Brep.volume` property which always reports an absolute value.
* Fixed `brep_to_occ` dropping the stored per-face `is_reversed` orientation, which let sewing invert the global shell orientation and flip the sign of the volume on serialization round-trips of shapes with mixed face orientations.

### Removed

## [0.1.3] 2026-07-08

### Added

* Added `compas_brep.scene.ghpython` with `BrepObject`, `NurbsCurveObject`, and `NurbsSurfaceObject` for drawing `Brep`, `NurbsCurve`, and `NurbsSurface` in Grasshopper.

### Changed

* Fixed `SceneObjectNotRegisteredError` in Grasshopper for when trying to draw Brep.

### Removed

## [0.1.2] 2026-07-07

### Added

### Changed

### Removed

## [0.1.1] 2026-06-25

### Added

### Changed

### Removed

## [0.1.0] 2026-06-24

### Added

### Changed

### Removed
