"""Rhino-backend coverage of the compas.geometry.Brep-compatible sub-object API.

Mirrors ``test_compas_brep_compat_api.py`` (which runs on OCC). The two backends
differ in what they can say about a curved face - Rhino converts every non-planar
surface to NURBS, so a cylindrical face reports ``surface_type == "nurbs"`` there -
so faces are selected by ``is_planar`` rather than by ``is_cylinder``.
"""

import pytest
from compas.geometry import Box
from compas.geometry import CurveType
from compas.geometry import Cylinder
from compas.geometry import Frame
from compas.geometry import Line
from compas.geometry import Plane
from compas.geometry import SurfaceType
from compas.geometry import Vector

from compas_brep import Brep
from compas_brep import LoopType
from compas_brep.surfaces import NurbsSurface

pytestmark = pytest.mark.rhino


@pytest.fixture
def box_brep():
    return Brep.from_box(Box(2.0, 3.0, 4.0))


@pytest.fixture
def holed_brep():
    """A flat box with a cylindrical hole through it.

    On the Rhino backend this is also the case that produces a genuinely reversed
    face - the hole wall - so it exercises the orientation flip.
    """
    box = Brep.from_box(Box(10.0, 10.0, 2.0))
    cylinder = Brep.from_cylinder(Cylinder(2.0, 6.0, frame=Frame.worldXY()))
    return (box - cylinder)[0]


# =============================================================================
# Face orientation
# =============================================================================


def test_opposite_box_faces_report_opposite_normals(box_brep):
    normals = [face.normal_at() for face in box_brep.faces]

    for axis in (Vector.Xaxis(), Vector.Yaxis(), Vector.Zaxis()):
        along = [n for n in normals if abs(n.dot(axis)) > 0.9]
        assert len(along) == 2
        assert along[0].dot(along[1]) == pytest.approx(-1.0)


def test_face_normal_matches_boundary_winding(box_brep):
    for face in box_brep.faces:
        assert face.normal_at().dot(face.to_polygon().normal) == pytest.approx(1.0)


def test_boolean_produces_a_reversed_face(holed_brep):
    """Rhino leaves a box unreversed, so the flip is only exercised after a boolean."""
    assert any(face.is_reversed for face in holed_brep.faces)


def test_face_normals_point_away_from_solid(holed_brep):
    centroid = holed_brep.centroid
    for face in holed_brep.faces:
        if not face.is_planar:
            continue  # the hole wall points inward by design
        outward = Vector(*(face.frame_at().point - centroid))
        assert outward.dot(face.normal_at()) > 0


def test_hole_wall_normal_points_into_the_void(holed_brep):
    face = next(f for f in holed_brep.faces if not f.is_planar)
    frame = face.frame_at()
    away_from_axis = Vector(frame.point.x, frame.point.y, 0.0)
    away_from_axis.unitize()
    assert frame.zaxis.dot(away_from_axis) == pytest.approx(-1.0, abs=1e-6)


def test_frame_at_preserves_xaxis_when_flipping(box_brep):
    for face in box_brep.faces:
        frame = face.frame_at()
        surface_frame = Frame.from_plane(face.surface)
        assert frame.xaxis.dot(surface_frame.xaxis) == pytest.approx(1.0)
        expected = -1.0 if face.is_reversed else 1.0
        assert frame.zaxis.dot(surface_frame.zaxis) == pytest.approx(expected)


def test_frame_at_matches_the_old_compas_rhino_path(box_brep):
    """Drop-in check: on unreversed faces the flip is a no-op, so nothing moved."""
    for face in box_brep.faces:
        assert not face.is_reversed
        old = Plane.from_frame(face.nurbssurface.frame_at(0, 0)).normal
        assert old.dot(face.normal_at()) == pytest.approx(1.0)


def test_frame_at_does_not_alias_the_cached_surface(box_brep):
    face = box_brep.faces[0]
    before = Vector(*face.surface.normal)

    frame = face.frame_at()
    frame.point.x += 1000.0

    assert face.surface.normal == before
    assert face.frame_at().point.x != frame.point.x


def test_frame_at_on_a_planar_face_defaults_to_the_centroid(box_brep):
    for face in box_brep.faces:
        assert face.frame_at().point.distance_to_point(face.centroid) == pytest.approx(0.0, abs=1e-9)


# =============================================================================
# Deriving a plane from a face
# =============================================================================


def test_oriented_plane_via_frame_at(box_brep):
    planes = [Plane.from_frame(f.frame_at()) for f in box_brep.faces]
    for axis in (Vector.Xaxis(), Vector.Yaxis(), Vector.Zaxis()):
        along = [p.normal for p in planes if abs(p.normal.dot(axis)) > 0.9]
        assert len(along) == 2
        assert along[0].dot(along[1]) == pytest.approx(-1.0)


# =============================================================================
# nurbssurface and type
# =============================================================================


def test_nurbssurface_of_a_planar_face(box_brep):
    face = box_brep.faces[0]
    surface = face.nurbssurface
    assert isinstance(surface, NurbsSurface)

    u = 0.5 * (surface.domain_u[0] + surface.domain_u[1])
    v = 0.5 * (surface.domain_v[0] + surface.domain_v[1])
    assert abs(surface.normal_at(u, v).dot(face.surface.normal)) == pytest.approx(1.0)


def test_nurbssurface_of_a_curved_face(holed_brep):
    face = next(f for f in holed_brep.faces if not f.is_planar)
    assert isinstance(face.nurbssurface, NurbsSurface)


def test_old_lap_two_step_still_works(box_brep):
    planes = [Plane.from_frame(f.nurbssurface.frame_at(0, 0)) for f in box_brep.faces]
    assert len(planes) == 6


def test_face_type_of_a_planar_face(box_brep):
    assert box_brep.faces[0].type == SurfaceType.PLANE
    assert not box_brep.faces[0].is_bspline


# =============================================================================
# Loops
# =============================================================================


def test_boundary_is_the_outer_loop(box_brep):
    for face in box_brep.faces:
        assert face.boundary is face.outer_loop
        assert face.boundary.is_outer
        assert face.holes == []


def test_holes_are_the_inner_loops(holed_brep):
    faces_with_holes = [f for f in holed_brep.faces if f.holes]
    assert len(faces_with_holes) == 2
    for face in faces_with_holes:
        assert len(face.holes) == 1
        assert face.holes[0].is_inner
        assert face.holes[0].loop_type == LoopType.INNER
        assert face.holes[0] is not face.boundary


def test_loop_is_outer_and_is_inner_are_complementary(holed_brep):
    for loop in holed_brep.loops:
        assert loop.is_outer != loop.is_inner


def test_loop_marking_survives_serialization(holed_brep):
    from compas.data import json_dumps
    from compas.data import json_loads

    other = json_loads(json_dumps(holed_brep))
    assert sum(len(f.holes) for f in other.faces) == 2
    for face in other.faces:
        assert face.boundary.is_outer
        for loop in face.holes:
            assert loop.is_inner


# =============================================================================
# Edges
# =============================================================================


def test_edge_vertex_aliases(box_brep):
    for edge in box_brep.edges:
        assert edge.start_vertex is edge.first_vertex
        assert edge.end_vertex is edge.last_vertex


def test_edge_to_line(box_brep):
    edge = box_brep.edges[0]
    line = edge.to_line()
    assert isinstance(line, Line)
    assert line.start == edge.start_vertex.point
    assert line.end == edge.end_vertex.point


def test_edge_type(box_brep, holed_brep):
    assert box_brep.edges[0].type == CurveType.LINE

    curved = [e for e in holed_brep.edges if not e.is_line]
    assert curved
    assert curved[0].type == CurveType.CIRCLE


def test_edge_centroid_of_a_line(box_brep):
    edge = box_brep.edges[0]
    expected = (edge.start_vertex.point + edge.end_vertex.point) * 0.5
    assert edge.centroid.distance_to_point(expected) == pytest.approx(0.0)


def test_edge_centroid_of_a_curve(holed_brep):
    edge = next(e for e in holed_brep.edges if not e.is_line)
    assert edge.centroid.x == pytest.approx(0.0, abs=1e-6)
    assert edge.centroid.y == pytest.approx(0.0, abs=1e-6)
