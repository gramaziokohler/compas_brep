"""Tests for torus surface extraction, codec, and round-trip (issue 04)."""

import json
import math

import pytest
from compas.geometry import Frame
from compas.geometry import ToroidalSurface
from compas.geometry import Torus
from compas.tolerance import TOL

from compas_brep import Brep

pytestmark = pytest.mark.occ

RADIUS_AXIS = 1.5
RADIUS_PIPE = 0.3


@pytest.fixture
def torus_brep():
    return Brep.from_torus(Torus(RADIUS_AXIS, RADIUS_PIPE))


@pytest.fixture
def torus_face(torus_brep):
    return next(f for f in torus_brep.faces if isinstance(f.surface, ToroidalSurface))


# =============================================================================
# 1. ToroidalSurface extraction
# =============================================================================


def test_toroidal_surface_extraction_torus_face_returns_toroidal_surface(torus_face):
    assert isinstance(torus_face.surface, ToroidalSurface)


def test_toroidal_surface_extraction_torus_radius_axis_correct(torus_face):
    assert abs(torus_face.surface.radius_axis - RADIUS_AXIS) <= TOL.absolute


def test_toroidal_surface_extraction_torus_radius_pipe_correct(torus_face):
    assert abs(torus_face.surface.radius_pipe - RADIUS_PIPE) <= TOL.absolute


def test_toroidal_surface_extraction_torus_frame_is_frame(torus_face):
    assert isinstance(torus_face.surface.frame, Frame)


def test_toroidal_surface_extraction_torus_frame_origin_near_center(torus_face):
    origin = torus_face.surface.frame.point
    assert abs(origin.x) < TOL.absolute
    assert abs(origin.y) < TOL.absolute
    assert abs(origin.z) < TOL.absolute


def test_toroidal_surface_extraction_torus_point_at_geometric_accuracy(torus_face):
    """COMPAS point_at agrees with OCC adaptor at equivalent parameters.

    OCC torus: u ∈ [0, 2π] (azimuth around axis), v ∈ [0, 2π] (meridional angle).
    COMPAS torus: u ∈ [0, 1] (u_occ / 2π), v ∈ [0, 1] (v_occ / 2π).
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    occ_face = torus_face.native_face
    adaptor = BRepAdaptor_Surface(occ_face)
    surface = torus_face.surface

    test_params = [
        (0.0, 0.0),
        (math.pi / 2, 0.0),
        (math.pi, math.pi / 2),
        (3 * math.pi / 2, math.pi),
    ]
    for u_occ, v_occ in test_params:
        occ_pt = adaptor.Value(u_occ, v_occ)
        u_compas = u_occ / (2 * math.pi)
        v_compas = v_occ / (2 * math.pi)
        compas_pt = surface.point_at(u_compas, v_compas)
        dx = occ_pt.X() - compas_pt.x
        dy = occ_pt.Y() - compas_pt.y
        dz = occ_pt.Z() - compas_pt.z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        assert dist <= 1e-6, f"OCC vs COMPAS mismatch at u={u_occ:.3f}, v={v_occ:.3f}: dist={dist}"


# =============================================================================
# 2. BrepFace API: surface_type, is_torus, __repr__
# =============================================================================


def test_brep_face_torus_api_surface_type_torus(torus_face):
    assert torus_face.surface_type == "torus"


def test_brep_face_torus_api_is_torus_true(torus_face):
    assert torus_face.is_torus is True


def test_brep_face_torus_api_is_nurbs_false_for_torus(torus_face):
    assert torus_face.is_nurbs is False


def test_brep_face_torus_api_is_planar_false_for_torus(torus_face):
    assert torus_face.is_planar is False


def test_brep_face_torus_api_is_cylinder_false_for_torus(torus_face):
    assert torus_face.is_cylinder is False


def test_brep_face_torus_api_is_sphere_false_for_torus(torus_face):
    assert torus_face.is_sphere is False


def test_brep_face_torus_api_repr_reports_torus(torus_face):
    assert "torus" in repr(torus_face)


# =============================================================================
# 3. JSON round-trip
# =============================================================================


def test_torus_round_trip_round_trip_preserves_torus_type(torus_brep):
    data = torus_brep.__data__
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "torus" in surface_types


def test_torus_round_trip_round_trip_face_count(torus_brep):
    data = torus_brep.__data__
    restored = Brep.__from_data__(data)
    assert len(restored.faces) == len(torus_brep.faces)


def test_torus_round_trip_round_trip_volume(torus_brep):
    data = torus_brep.__data__
    restored = Brep.__from_data__(data)
    expected = 2 * math.pi**2 * RADIUS_AXIS * RADIUS_PIPE**2
    assert abs(restored.volume - expected) < 0.01


def test_torus_round_trip_json_round_trip(torus_brep):
    data = torus_brep.__data__
    restored = Brep.__from_data__(json.loads(json.dumps(data)))
    assert len(restored.faces) == len(torus_brep.faces)
    expected = 2 * math.pi**2 * RADIUS_AXIS * RADIUS_PIPE**2
    assert abs(restored.volume - expected) < 0.01


def test_torus_round_trip_restored_face_is_toroidal_surface(torus_brep):
    data = torus_brep.__data__
    restored = Brep.__from_data__(data)
    tor_faces = [f for f in restored.faces if isinstance(f.surface, ToroidalSurface)]
    assert len(tor_faces) >= 1


def test_torus_round_trip_restored_viewmesh_non_empty(torus_brep):
    data = torus_brep.__data__
    restored = Brep.__from_data__(data)
    mesh = restored.to_viewmesh()
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0


# =============================================================================
# 4. Analytic surface tessellation (no viewer required)
# =============================================================================


def test_analytic_torus_tessellation_tessellate_toroidal_surface(torus_face):
    """ToroidalSurface tessellates to a non-empty mesh via space_u/space_v/point_at."""
    from compas.datastructures import Mesh

    surface = torus_face.surface
    u_params = list(surface.space_u(16))
    v_params = list(surface.space_v(16))

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


def test_analytic_torus_tessellation_tessellate_parametric_surface_helper(torus_face):
    """The shared tessellation helper produces a non-empty mesh for ToroidalSurface."""
    from compas_brep.scene.viewer.surfaceobject import _tessellate_parametric_surface

    mesh, boundaries = _tessellate_parametric_surface(torus_face.surface, 16, 16)
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0
    assert len(boundaries) == 4
