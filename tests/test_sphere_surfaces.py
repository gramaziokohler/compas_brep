"""Tests for sphere surface extraction, codec, and round-trip (issue 03)."""

import json
import math

import pytest
from compas.geometry import Frame
from compas.geometry import Sphere
from compas.geometry import SphericalSurface
from compas.tolerance import TOL

from compas_brep import Brep

pytestmark = pytest.mark.occ

RADIUS = 0.75


@pytest.fixture
def sphere_brep():
    return Brep.from_sphere(Sphere(RADIUS))


@pytest.fixture
def sphere_face(sphere_brep):
    return next(f for f in sphere_brep.faces if isinstance(f.surface, SphericalSurface))


# =============================================================================
# 1. SphericalSurface extraction
# =============================================================================


def test_spherical_surface_extraction_sphere_face_returns_spherical_surface(sphere_face):
    assert isinstance(sphere_face.surface, SphericalSurface)


def test_spherical_surface_extraction_sphere_radius_correct(sphere_face):
    assert abs(sphere_face.surface.radius - RADIUS) <= TOL.absolute


def test_spherical_surface_extraction_sphere_frame_is_frame(sphere_face):
    assert isinstance(sphere_face.surface.frame, Frame)


def test_spherical_surface_extraction_sphere_frame_origin_near_center(sphere_face):
    origin = sphere_face.surface.frame.point
    assert abs(origin.x) < TOL.absolute
    assert abs(origin.y) < TOL.absolute
    assert abs(origin.z) < TOL.absolute


def test_spherical_surface_extraction_sphere_point_at_geometric_accuracy(sphere_face):
    """COMPAS point_at agrees with OCC adaptor at equivalent parameters.

    OCC sphere: u ∈ [0, 2π] (azimuth), v ∈ [-π/2, π/2] (latitude).
    COMPAS sphere: u ∈ [0, 1] (u_occ / 2π), v ∈ [0, 1] (0.5 - v_occ / π).
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    occ_face = sphere_face.native_face
    adaptor = BRepAdaptor_Surface(occ_face)
    surface = sphere_face.surface

    test_params = [
        (0.0, 0.0),
        (math.pi / 2, 0.0),
        (math.pi, math.pi / 4),
        (3 * math.pi / 2, -math.pi / 4),
    ]
    for u_occ, v_occ in test_params:
        occ_pt = adaptor.Value(u_occ, v_occ)
        u_compas = u_occ / (2 * math.pi)
        v_compas = 0.5 - v_occ / math.pi
        compas_pt = surface.point_at(u_compas, v_compas)
        dx = occ_pt.X() - compas_pt.x
        dy = occ_pt.Y() - compas_pt.y
        dz = occ_pt.Z() - compas_pt.z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        assert dist <= 1e-6, f"OCC vs COMPAS mismatch at u={u_occ:.3f}, v={v_occ:.3f}: dist={dist}"


# =============================================================================
# 2. BrepFace API: surface_type, is_sphere, __repr__
# =============================================================================


def test_brep_face_sphere_api_surface_type_sphere(sphere_face):
    assert sphere_face.surface_type == "sphere"


def test_brep_face_sphere_api_is_sphere_true(sphere_face):
    assert sphere_face.is_sphere is True


def test_brep_face_sphere_api_is_nurbs_false_for_sphere(sphere_face):
    assert sphere_face.is_nurbs is False


def test_brep_face_sphere_api_is_planar_false_for_sphere(sphere_face):
    assert sphere_face.is_planar is False


def test_brep_face_sphere_api_is_cylinder_false_for_sphere(sphere_face):
    assert sphere_face.is_cylinder is False


def test_brep_face_sphere_api_repr_reports_sphere(sphere_face):
    assert "sphere" in repr(sphere_face)


# =============================================================================
# 3. JSON round-trip
# =============================================================================


def test_sphere_round_trip_round_trip_preserves_sphere_type(sphere_brep):
    data = sphere_brep.__data__
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "sphere" in surface_types


def test_sphere_round_trip_round_trip_face_count(sphere_brep):
    data = sphere_brep.__data__
    restored = Brep.__from_data__(data)
    assert len(restored.faces) == len(sphere_brep.faces)


def test_sphere_round_trip_round_trip_volume(sphere_brep):
    data = sphere_brep.__data__
    restored = Brep.__from_data__(data)
    expected = (4.0 / 3.0) * math.pi * RADIUS**3
    assert abs(restored.volume - expected) < 0.01


def test_sphere_round_trip_json_round_trip(sphere_brep):
    data = sphere_brep.__data__
    restored = Brep.__from_data__(json.loads(json.dumps(data)))
    assert len(restored.faces) == len(sphere_brep.faces)
    expected = (4.0 / 3.0) * math.pi * RADIUS**3
    assert abs(restored.volume - expected) < 0.01


def test_sphere_round_trip_restored_face_is_spherical_surface(sphere_brep):
    data = sphere_brep.__data__
    restored = Brep.__from_data__(data)
    sph_faces = [f for f in restored.faces if isinstance(f.surface, SphericalSurface)]
    assert len(sph_faces) >= 1


def test_sphere_round_trip_restored_viewmesh_non_empty(sphere_brep):
    data = sphere_brep.__data__
    restored = Brep.__from_data__(data)
    mesh = restored.to_viewmesh()
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0


# =============================================================================
# 4. Analytic surface tessellation (no viewer required)
# =============================================================================


def test_analytic_sphere_tessellation_tessellate_spherical_surface(sphere_face):
    """SphericalSurface tessellates to a non-empty mesh via space_u/space_v/point_at."""
    from compas.datastructures import Mesh

    surface = sphere_face.surface
    u_params = list(surface.space_u(16))
    v_params = list(surface.space_v(8))

    vertices = []
    for u in u_params:
        for v in v_params:
            p = surface.point_at(u, v)
            vertices.append([p.x, p.y, p.z])

    faces = []
    nv = len(v_params)
    for i in range(len(u_params) - 1):
        for j in range(len(v_params) - 1):
            v0 = i * nv + j
            v1 = i * nv + (j + 1)
            v2 = (i + 1) * nv + (j + 1)
            v3 = (i + 1) * nv + j
            faces.append([v0, v1, v2])
            faces.append([v0, v2, v3])

    mesh = Mesh.from_vertices_and_faces(vertices, faces)
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0


def test_analytic_sphere_tessellation_tessellate_parametric_surface_helper(sphere_face):
    """The shared tessellation helper produces a non-empty mesh for SphericalSurface."""
    from compas_brep.scene.viewer.surfaceobject import _tessellate_parametric_surface

    mesh, boundaries = _tessellate_parametric_surface(sphere_face.surface, 16, 8)
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0
    assert len(boundaries) == 4
