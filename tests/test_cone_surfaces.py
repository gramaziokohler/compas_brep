"""Tests for cone surface extraction, codec, and round-trip (issue 05).

Parameterization notes
-----------------------
OCC gp_Cone: P(u, v) = L + (R0 + v*sin(alpha)) * (cos(u)*X + sin(u)*Y) + v*cos(alpha)*Z
  where alpha = SemiAngle (negative for tapering, i.e. radius decreases as v increases).
  Apex at V_apex = -R0/sin(alpha); slant height V_apex = sqrt(R0**2 + height**2).

COMPAS ConicalSurface: p(u_c, v_c) = O + (1-v_c)*r*(cos(2*pi*u_c)*Fx+sin(2*pi*u_c)*Fy) + v_c*h*Fz
  u_c in [0,1], v_c in [0,1]; v_c=0 is base (radius r), v_c=1 is apex.

Mapping: u_c = u_occ / (2*pi),  v_c = v_occ / V_apex = v_occ / sqrt(r**2 + h**2)
"""

import json
import math

import pytest
from compas.geometry import Cone
from compas.geometry import ConicalSurface
from compas.geometry import Frame

from compas_brep import Brep

pytestmark = pytest.mark.occ

RADIUS = 1.0
HEIGHT = 2.0


@pytest.fixture
def cone_brep():
    return Brep.from_cone(Cone(RADIUS, HEIGHT))


@pytest.fixture
def cone_face(cone_brep):
    return next(f for f in cone_brep.faces if isinstance(f.surface, ConicalSurface))


# =============================================================================
# 1. ConicalSurface extraction
# =============================================================================


def test_conical_surface_extraction_cone_face_returns_conical_surface(cone_face):
    assert isinstance(cone_face.surface, ConicalSurface)


def test_conical_surface_extraction_cone_radius_correct(cone_face):
    assert abs(cone_face.surface.radius - RADIUS) <= 1e-6


def test_conical_surface_extraction_cone_height_correct(cone_face):
    assert abs(cone_face.surface.height - HEIGHT) <= 1e-6


def test_conical_surface_extraction_cone_frame_is_frame(cone_face):
    assert isinstance(cone_face.surface.frame, Frame)


def test_conical_surface_extraction_cone_frame_origin_near_base_center(cone_face):
    origin = cone_face.surface.frame.point
    assert abs(origin.x) < 1e-6
    assert abs(origin.y) < 1e-6
    assert abs(origin.z) < 1e-6


def test_conical_surface_extraction_cone_point_at_geometric_accuracy(cone_face):
    """COMPAS point_at matches OCC adaptor at equivalent parameters.

    OCC cone: u in [0, 2pi] (azimuth), v in [0, V_apex] (slant height).
    COMPAS cone: u_c = u_occ / 2pi, v_c = v_occ / sqrt(R^2 + h^2).
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    occ_face = cone_face.native_face
    adaptor = BRepAdaptor_Surface(occ_face)
    surface = cone_face.surface

    R = surface.radius
    H = surface.height
    V_apex = math.sqrt(R**2 + H**2)

    test_params = [
        (0.0, 0.0),
        (math.pi / 2, V_apex * 0.25),
        (math.pi, V_apex * 0.5),
        (3 * math.pi / 2, V_apex * 0.75),
    ]
    for u_occ, v_occ in test_params:
        occ_pt = adaptor.Value(u_occ, v_occ)
        u_c = u_occ / (2 * math.pi)
        v_c = v_occ / V_apex
        compas_pt = surface.point_at(u_c, v_c)
        dx = occ_pt.X() - compas_pt.x
        dy = occ_pt.Y() - compas_pt.y
        dz = occ_pt.Z() - compas_pt.z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        assert dist <= 1e-6, f"OCC vs COMPAS mismatch at u={u_occ:.3f}, v={v_occ:.4f}: dist={dist}"


# =============================================================================
# 2. BrepFace API: surface_type, is_cone, __repr__
# =============================================================================


def test_brep_face_cone_api_surface_type_cone(cone_face):
    assert cone_face.surface_type == "cone"


def test_brep_face_cone_api_is_cone_true(cone_face):
    assert cone_face.is_cone is True


def test_brep_face_cone_api_is_nurbs_false_for_cone(cone_face):
    assert cone_face.is_nurbs is False


def test_brep_face_cone_api_is_planar_false_for_cone(cone_face):
    assert cone_face.is_planar is False


def test_brep_face_cone_api_is_cylinder_false_for_cone(cone_face):
    assert cone_face.is_cylinder is False


def test_brep_face_cone_api_is_sphere_false_for_cone(cone_face):
    assert cone_face.is_sphere is False


def test_brep_face_cone_api_is_torus_false_for_cone(cone_face):
    assert cone_face.is_torus is False


def test_brep_face_cone_api_repr_reports_cone(cone_face):
    assert "cone" in repr(cone_face)


def test_brep_face_cone_api_planar_face_surface_type(cone_brep):
    planar_face = next(f for f in cone_brep.faces if f.is_planar)
    assert planar_face.surface_type == "plane"
    assert planar_face.is_cone is False


# =============================================================================
# 3. JSON round-trip
# =============================================================================


def test_cone_round_trip_round_trip_preserves_cone_type(cone_brep):
    data = cone_brep.__data__
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "cone" in surface_types


def test_cone_round_trip_round_trip_face_count(cone_brep):
    data = cone_brep.__data__
    restored = Brep.__from_data__(data)
    assert len(restored.faces) == len(cone_brep.faces)


def test_cone_round_trip_round_trip_volume(cone_brep):
    data = cone_brep.__data__
    restored = Brep.__from_data__(data)
    expected = (math.pi * RADIUS**2 * HEIGHT) / 3.0
    assert abs(restored.volume - expected) < 0.01


def test_cone_round_trip_json_round_trip(cone_brep):
    data = cone_brep.__data__
    restored = Brep.__from_data__(json.loads(json.dumps(data)))
    assert len(restored.faces) == len(cone_brep.faces)
    expected = (math.pi * RADIUS**2 * HEIGHT) / 3.0
    assert abs(restored.volume - expected) < 0.01


def test_cone_round_trip_restored_face_is_conical_surface(cone_brep):
    data = cone_brep.__data__
    restored = Brep.__from_data__(data)
    cone_faces = [f for f in restored.faces if isinstance(f.surface, ConicalSurface)]
    assert len(cone_faces) >= 1


def test_cone_round_trip_restored_viewmesh_non_empty(cone_brep):
    data = cone_brep.__data__
    restored = Brep.__from_data__(data)
    mesh = restored.to_viewmesh()
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0


# =============================================================================
# 4. Analytic surface tessellation (no viewer required)
# =============================================================================


def test_analytic_cone_tessellation_tessellate_conical_surface(cone_face):
    """ConicalSurface tessellates to a non-empty mesh via space_u/space_v/point_at."""
    from compas.datastructures import Mesh

    surface = cone_face.surface
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


def test_analytic_cone_tessellation_tessellate_parametric_surface_helper(cone_face):
    """The shared tessellation helper produces a non-empty mesh for ConicalSurface."""
    from compas_brep.scene.viewer.surfaceobject import _tessellate_parametric_surface

    mesh, boundaries = _tessellate_parametric_surface(cone_face.surface, 16, 8)
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0
    assert len(boundaries) == 4
