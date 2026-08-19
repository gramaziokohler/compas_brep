"""Tests for the compas.geometry.Brep-compatible sub-object API.

Covers the accessors that consumers written against ``compas.geometry.Brep``
(via ``compas_rhino`` or ``compas_occ``) expect to find on the topology
sub-objects: face frames/normals that account for face orientation,
``nurbssurface``, ``boundary``/``holes``, ``start_vertex``/``end_vertex``,
and ``is_outer``/``is_inner``.
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

pytestmark = pytest.mark.occ


@pytest.fixture
def box_brep():
    return Brep.from_box(Box(2.0, 3.0, 4.0))


@pytest.fixture
def holed_brep():
    """A flat box with a cylindrical hole punched through it, so faces have inner loops."""
    box = Brep.from_box(Box(10.0, 10.0, 2.0))
    cylinder = Brep.from_cylinder(Cylinder(2.0, 6.0, frame=Frame.worldXY()))
    return Brep.from_boolean_difference(box, cylinder)


# =============================================================================
# Face orientation
# =============================================================================


def test_opposite_box_faces_report_opposite_normals(box_brep):
    """The bug the API exists to fix: face.surface alone can't tell the pairs apart."""
    normals = [face.normal_at() for face in box_brep.faces]

    for axis in (Vector.Xaxis(), Vector.Yaxis(), Vector.Zaxis()):
        along = [n for n in normals if abs(n.dot(axis)) > 0.9]
        assert len(along) == 2
        assert along[0].dot(along[1]) == pytest.approx(-1.0)


def test_face_normal_matches_boundary_winding(box_brep):
    for face in box_brep.faces:
        assert face.normal_at().dot(face.to_polygon().normal) == pytest.approx(1.0)


def test_face_normals_point_away_from_solid(holed_brep):
    centroid = holed_brep.centroid
    for face in holed_brep.faces:
        if not face.is_planar:
            continue  # the hole wall points inward by design
        outward = Vector(*(face.frame_at().point - centroid))
        assert outward.dot(face.normal_at()) > 0


def test_frame_at_preserves_xaxis_when_flipping(box_brep):
    for face in box_brep.faces:
        frame = face.frame_at()
        surface_frame = Frame.from_plane(face.surface)
        assert frame.xaxis.dot(surface_frame.xaxis) == pytest.approx(1.0)
        expected = -1.0 if face.is_reversed else 1.0
        assert frame.zaxis.dot(surface_frame.zaxis) == pytest.approx(expected)


def test_surface_is_left_unflipped(box_brep):
    """`surface` stays the raw underlying surface, as in compas_occ and compas_rhino."""
    reversed_faces = [f for f in box_brep.faces if f.is_reversed]
    assert reversed_faces
    for face in reversed_faces:
        assert face.surface.normal.dot(face.normal_at()) == pytest.approx(-1.0)


def test_frame_at_does_not_alias_the_cached_surface(box_brep):
    """Callers must not be able to corrupt the face by mutating what they got back."""
    face = box_brep.faces[0]
    before = Vector(*face.surface.normal)

    frame = face.frame_at()
    frame.point.x += 1000.0

    assert face.surface.normal == before
    assert face.frame_at().point.x != frame.point.x


def test_frame_at_accepts_explicit_parameters(box_brep):
    face = box_brep.faces[0]
    frame = face.frame_at(0.0, 0.0)
    assert frame.zaxis.dot(face.normal_at()) == pytest.approx(1.0)


def test_frame_at_on_a_planar_face_defaults_to_the_centroid(box_brep):
    for face in box_brep.faces:
        assert face.frame_at().point.distance_to_point(face.centroid) == pytest.approx(0.0, abs=1e-9)


def test_frame_at_on_a_curved_face_defaults_to_the_middle_of_the_domain(holed_brep):
    face = next(f for f in holed_brep.faces if f.is_cylinder)
    u = 0.5 * (face.domain_u[0] + face.domain_u[1])
    v = 0.5 * (face.domain_v[0] + face.domain_v[1])
    assert face.frame_at().point.distance_to_point(face.frame_at(u, v).point) == pytest.approx(0.0)


def test_frame_at_on_a_curved_face(holed_brep):
    face = next(f for f in holed_brep.faces if f.is_cylinder)
    frame = face.frame_at()
    # the hole wall of a solid faces its own axis
    to_axis = Vector(frame.point.x, frame.point.y, 0.0)
    to_axis.unitize()
    assert frame.zaxis.dot(to_axis) == pytest.approx(-1.0, abs=1e-6)


def test_oriented_plane_via_frame_at(box_brep):
    """A plane for a planar face comes from frame_at; there is no plane-only accessor."""
    planes = [Plane.from_frame(f.frame_at()) for f in box_brep.faces]
    for plane, face in zip(planes, box_brep.faces):
        assert plane.normal.dot(face.normal_at()) == pytest.approx(1.0)

    # and, unlike the raw `surface`, the six normals are three opposite pairs
    for axis in (Vector.Xaxis(), Vector.Yaxis(), Vector.Zaxis()):
        along = [p.normal for p in planes if abs(p.normal.dot(axis)) > 0.9]
        assert len(along) == 2
        assert along[0].dot(along[1]) == pytest.approx(-1.0)


# =============================================================================
# Face: nurbssurface and type
# =============================================================================


def test_nurbssurface_of_a_planar_face(box_brep):
    face = box_brep.faces[0]
    surface = face.nurbssurface
    assert isinstance(surface, NurbsSurface)

    u = 0.5 * (surface.domain_u[0] + surface.domain_u[1])
    v = 0.5 * (surface.domain_v[0] + surface.domain_v[1])
    assert surface.point_at(u, v).distance_to_point(face.frame_at().point) == pytest.approx(0.0, abs=1e-6)
    # like the old implementations, the NURBS surface is the unflipped one
    assert abs(surface.normal_at(u, v).dot(face.surface.normal)) == pytest.approx(1.0)


def test_nurbssurface_of_a_curved_face(holed_brep):
    face = next(f for f in holed_brep.faces if f.is_cylinder)
    assert isinstance(face.nurbssurface, NurbsSurface)


def test_nurbssurface_returns_a_nurbs_surface_as_is():
    brep = Brep.from_box(Box(1.0, 1.0, 1.0))
    face = brep.faces[0]
    face.surface = face.nurbssurface
    assert face.nurbssurface is face.surface


def test_face_type_and_is_bspline(box_brep, holed_brep):
    assert box_brep.faces[0].type == SurfaceType.PLANE
    assert not box_brep.faces[0].is_bspline

    cylindrical = next(f for f in holed_brep.faces if f.is_cylinder)
    assert cylindrical.type == SurfaceType.CYLINDER


# =============================================================================
# Face: loop accessors
# =============================================================================


def test_boundary_is_the_outer_loop(box_brep):
    for face in box_brep.faces:
        assert face.boundary is face.outer_loop
        assert face.boundary.is_outer


def test_holes_are_the_inner_loops(holed_brep):
    faces_with_holes = [f for f in holed_brep.faces if f.holes]
    assert len(faces_with_holes) == 2
    for face in faces_with_holes:
        assert len(face.holes) == 1
        assert face.holes[0] in face.loops
        assert face.holes[0] is not face.boundary


def test_box_faces_have_no_holes(box_brep):
    for face in box_brep.faces:
        assert face.holes == []


# =============================================================================
# Loop: is_outer / is_inner / loop_type
# =============================================================================


def test_loop_is_outer_and_is_inner_are_complementary(holed_brep):
    for loop in holed_brep.loops:
        assert loop.is_outer != loop.is_inner


def test_inner_loops_are_marked_inner(holed_brep):
    inner = [lp for f in holed_brep.faces for lp in f.holes]
    assert len(inner) == 2
    for loop in inner:
        assert loop.is_inner
        assert loop.loop_type == LoopType.INNER


def test_outer_loops_are_marked_outer(box_brep):
    for loop in box_brep.loops:
        assert loop.is_outer
        assert loop.loop_type == LoopType.OUTER


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
# Edge
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
    assert curved[0].type == CurveType.BSPLINE


def test_edge_centroid_of_a_line(box_brep):
    edge = box_brep.edges[0]
    expected = (edge.start_vertex.point + edge.end_vertex.point) * 0.5
    assert edge.centroid.distance_to_point(expected) == pytest.approx(0.0)


def test_edge_centroid_of_a_curve(holed_brep):
    edge = next(e for e in holed_brep.edges if not e.is_line)
    # the hole rim is a full circle centred on the world z-axis
    assert edge.centroid.x == pytest.approx(0.0, abs=1e-6)
    assert edge.centroid.y == pytest.approx(0.0, abs=1e-6)


# =============================================================================
# Faces not backed by a kernel
# =============================================================================


def test_nurbssurface_of_a_detached_face_is_a_clear_error():
    from compas_brep import BrepEdge
    from compas_brep import BrepError
    from compas_brep import BrepFace
    from compas_brep import BrepLoop
    from compas_brep import BrepVertex

    points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    vertices = [BrepVertex(p) for p in points]
    edges = [BrepEdge(vertices[i], vertices[(i + 1) % 4]) for i in range(4)]
    face = BrepFace(BrepLoop(edges=edges))

    assert face.native_face is None
    with pytest.raises(BrepError):
        face.nurbssurface


def test_detached_face_frame_at_still_works():
    from compas_brep import BrepEdge
    from compas_brep import BrepFace
    from compas_brep import BrepLoop
    from compas_brep import BrepVertex

    points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    vertices = [BrepVertex(p) for p in points]
    edges = [BrepEdge(vertices[i], vertices[(i + 1) % 4]) for i in range(4)]
    face = BrepFace(BrepLoop(edges=edges))

    assert face.normal_at().dot(Vector.Zaxis()) == pytest.approx(1.0)
