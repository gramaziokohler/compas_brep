# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

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
