# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

* Added `BrepFace.frame_at(u, v)` and `BrepFace.normal_at(u, v)`, which account for `BrepFace.is_reversed` so that opposite faces of a solid report opposite normals. `BrepFace.surface` is unchanged and still returns the raw, unflipped underlying surface.

* Added `BrepFace.boundary` and `BrepFace.holes`, and `BrepLoop.is_outer`, `BrepLoop.is_inner` and `BrepLoop.loop_type` along with the `LoopType` constants. Loops are tagged as outer/inner by the face that owns them.

### Changed

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
