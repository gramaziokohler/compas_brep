"""Pluggable operations for compas_brep — implemented by the active backend (OCC or Rhino)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from compas.datastructures import Mesh
from compas.geometry import Box
from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Polyline
from compas.geometry import Transformation
from compas.geometry import Vector
from compas.plugins import pluggable

if TYPE_CHECKING:
    from compas_brep.brep import Brep

# ---- Primitive constructors ----


@pluggable(category="brep-factories")
def make_box(box: Box) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_cylinder(cylinder: Any) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_sphere(sphere: Any) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_cone(cone: Any) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_torus(torus: Any) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_mesh(mesh: Mesh) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_extrusion(face_or_curve: Any, vector: Vector) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_loft(profiles: list[Any]) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_native(native_brep: Any) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_sweep(profile: Brep, path: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_pipe(path: Brep, radius: float) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_curves(curves: list[Any]) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_breps(breps: list[Brep]) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_surface(
    surface: Any,
    domain_u: tuple[float, float] | None = None,
    domain_v: tuple[float, float] | None = None,
) -> Brep:
    raise NotImplementedError


# ---- Boolean operations ----


@pluggable(category="brep-operations")
def boolean_difference(brep_a: Brep, brep_b: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def boolean_union(brep_a: Brep, brep_b: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def boolean_intersection(brep_a: Brep, brep_b: Brep) -> Brep:
    raise NotImplementedError


# ---- Instance operations ----


@pluggable(category="brep-operations")
def brep_trimmed(brep: Brep, plane: Plane) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_split(brep: Brep, cutter: Brep) -> list[Brep]:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_slice(brep: Brep, plane: Plane) -> list[Polyline]:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_fillet(brep: Brep, radius: float, edges: list[int] | None = None) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_offset(brep: Brep, distance: float) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_cap_planar_holes(brep: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_overlap(brep_a: Brep, brep_b: Brep, deflection: float | None = None, tolerance: float = 0.0) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_contains(brep: Brep, obj: Point) -> bool:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_fix(brep: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_heal(brep: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_sew(brep: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_make_solid(brep: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_transform(brep: Brep, transformation: Transformation) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_flip(brep: Brep) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_copy(brep: Brep) -> Brep:
    raise NotImplementedError


# ---- Queries ----


@pluggable(category="brep-queries")
def brep_area(brep: Brep) -> float:
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_volume(brep: Brep) -> float:
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_centroid(brep: Brep) -> Point:
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_aabb(brep: Brep) -> Box:
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_is_solid(brep: Brep) -> bool:
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_extract_topology(brep: Brep) -> None:
    """Populate a Brep's topology lists in-place from its native backend shape.

    Called lazily the first time topology (vertices, edges, loops, faces) is
    accessed on a Brep that was returned from a backend operation without
    eager extraction.
    """
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_is_valid(brep: Brep) -> bool:
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_tessellate(
    brep: Brep,
    linear_deflection: float = 0.1,
    n: int = 16,
    n_curves: int = 64,
) -> tuple[Mesh, list[Polyline]]:
    raise NotImplementedError


# ---- Serialization ----


@pluggable(category="brep-operations")
def brep_to_data(brep: Brep) -> dict:
    """Extract a STEP-inspired JSON-serializable dict from the native backend.

    Called from Brep.__data__ to produce the canonical serialization.
    Requires an active backend (OCC or Rhino).
    """
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_rebuild(brep: Brep, data: dict) -> None:
    """Rebuild the native backend object from a STEP-inspired JSON data dict.

    Called from Brep.__from_data__ to reconstruct the native shape.
    Requires an active backend (OCC or Rhino).
    """
    raise NotImplementedError


# ---- File I/O ----


@pluggable(category="brep-io")
def brep_to_step(brep: Brep, filepath: str, **kwargs: Any) -> None:
    raise NotImplementedError


@pluggable(category="brep-io")
def brep_from_step(filepath: str) -> Brep:
    raise NotImplementedError


@pluggable(category="brep-io")
def brep_to_stl(brep: Brep, filepath: str, **kwargs: Any) -> None:
    raise NotImplementedError


@pluggable(category="brep-io")
def brep_to_iges(brep: Brep, filepath: str) -> None:
    raise NotImplementedError


@pluggable(category="brep-io")
def brep_from_iges(filepath: str) -> Brep:
    raise NotImplementedError
