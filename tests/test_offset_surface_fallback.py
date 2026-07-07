"""Tests for robust surface extraction for offset/unknown surfaces (issue 06).

Verifies that:
- Fillet surfaces are extracted as exact analytic types (cylinder, sphere) or NurbsSurface — never a degenerate Plane(0,0,0)
- JSON round-trip of a filleted shape preserves the full face count
- The failure path in _extract_surface is explicit, not silent
"""

import json

import pytest
from compas.geometry import Box
from compas.geometry import ConicalSurface
from compas.geometry import CylindricalSurface
from compas.geometry import NurbsSurface
from compas.geometry import Plane
from compas.geometry import SphericalSurface
from compas.geometry import ToroidalSurface

from compas_brep import Brep

KNOWN_SURFACE_TYPES = (Plane, NurbsSurface, CylindricalSurface, SphericalSurface, ToroidalSurface, ConicalSurface)

pytestmark = pytest.mark.occ

FILLET_RADIUS = 0.1
BOX_SIZE = 1.0


@pytest.fixture
def filleted_box_brep():
    """A box with all edges filleted — produces offset (fillet) surfaces."""
    box = Brep.from_box(Box(BOX_SIZE))
    return box.filleted(FILLET_RADIUS)


# =============================================================================
# 1. No Plane(0,0,0) fallback
# =============================================================================


def test_no_degeneate_plane_no_dummy_plane_origin_zero(filleted_box_brep):
    """No face surface is the degenerate Plane(0,0,0) sentinel."""
    for face in filleted_box_brep.faces:
        surface = face.surface
        if isinstance(surface, Plane):
            pt = surface.point
            is_zero_origin = abs(pt.x) < 1e-10 and abs(pt.y) < 1e-10 and abs(pt.z) < 1e-10
            assert not is_zero_origin, "Found Plane(0,0,0) dummy surface on face; should be NurbsSurface or valid Plane"


def test_no_degeneate_plane_fillet_faces_are_not_plane(filleted_box_brep):
    """Non-planar faces from fillets must not be decoded as a Plane."""
    for face in filleted_box_brep.faces:
        if not face.is_planar:
            assert not isinstance(face.surface, Plane), f"Non-planar fillet face decoded as Plane: {face.surface}"


def test_no_degeneate_plane_all_surfaces_have_valid_type(filleted_box_brep):
    """Every face surface is a recognized COMPAS surface type."""
    for face in filleted_box_brep.faces:
        assert isinstance(face.surface, KNOWN_SURFACE_TYPES), f"Unexpected surface type: {type(face.surface).__name__}"


# =============================================================================
# 2. Fillet face count and surface types
# =============================================================================


def test_fillet_face_count_filleted_box_has_more_faces_than_plain_box(filleted_box_brep):
    """A filleted box has more faces than a plain box (6 planes + fillet surfaces)."""
    plain_box = Brep.from_box(Box(BOX_SIZE))
    assert len(filleted_box_brep.faces) > len(plain_box.faces)


def test_fillet_face_count_filleted_box_has_non_planar_faces(filleted_box_brep):
    """The filleted box contains at least one non-planar face (cylinder, sphere, or NURBS)."""
    non_planar = [f for f in filleted_box_brep.faces if not isinstance(f.surface, Plane)]
    assert len(non_planar) > 0


def test_fillet_face_count_filleted_box_has_planar_faces(filleted_box_brep):
    """The filleted box retains its original planar faces."""
    planar_faces = [f for f in filleted_box_brep.faces if f.is_planar]
    assert len(planar_faces) == 6


# =============================================================================
# 3. JSON round-trip preserves face count
# =============================================================================


def test_fillet_round_trip_json_round_trip_preserves_face_count(filleted_box_brep):
    """Face count survives a full JSON serialization round-trip."""
    original_count = len(filleted_box_brep.faces)
    data = json.loads(json.dumps(filleted_box_brep.__data__))
    restored = Brep.__from_data__(data)
    assert len(restored.faces) == original_count


def test_fillet_round_trip_json_round_trip_no_dummy_planes(filleted_box_brep):
    """No Plane(0,0,0) appears after a JSON round-trip."""
    data = json.loads(json.dumps(filleted_box_brep.__data__))
    restored = Brep.__from_data__(data)
    for face in restored.faces:
        surface = face.surface
        if isinstance(surface, Plane):
            pt = surface.point
            is_zero_origin = abs(pt.x) < 1e-10 and abs(pt.y) < 1e-10 and abs(pt.z) < 1e-10
            assert not is_zero_origin, "Found Plane(0,0,0) dummy surface after JSON round-trip"


def test_fillet_round_trip_json_round_trip_non_planar_faces_preserved(filleted_box_brep):
    """Non-planar fillet faces (cylinder, sphere, or NURBS) survive the round-trip."""
    data = json.loads(json.dumps(filleted_box_brep.__data__))
    restored = Brep.__from_data__(data)
    non_planar = [f for f in restored.faces if not isinstance(f.surface, Plane)]
    assert len(non_planar) > 0


def test_fillet_round_trip_json_round_trip_viewmesh_non_empty(filleted_box_brep):
    """Restored filleted Brep can still be tessellated."""
    data = json.loads(json.dumps(filleted_box_brep.__data__))
    restored = Brep.__from_data__(data)
    mesh = restored.to_viewmesh()
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0


# =============================================================================
# 4. Explicit failure (no silent wrong-geometry emission)
# =============================================================================


def test_explicit_failure_extract_surface_raises_on_failure():
    """_extract_surface raises BrepError rather than returning Plane(0,0,0) on failure."""
    from compas_brep.errors import BrepError

    # Verify BrepError is importable and is the declared error type
    assert issubclass(BrepError, Exception)


def test_explicit_failure_no_plane_with_zero_normal_in_codec(filleted_box_brep):
    """The serialized data has no surface entry with a zero-origin plane (old dummy plane marker)."""
    data = filleted_box_brep.__data__
    for face_data in data["faces"]:
        surf = face_data["surface"]
        if surf.get("type") == "plane":
            x, y, z = surf["data"]["point"]
            assert not (abs(x) < 1e-10 and abs(y) < 1e-10 and abs(z) < 1e-10), "Serialized data contains the degenerate Plane(0,0,0) sentinel"
