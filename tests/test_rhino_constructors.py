"""Rhino-backend coverage of the mesh/polygon constructors.

The n-gon cases exist because the Rhino backend used to route ``from_polygons``
and ``from_mesh`` through ``Rhino.Geometry.Brep.CreateFromMesh``, which builds a
face per *Rhino mesh* face. A Rhino mesh cannot hold an n-gon except as a group
of triangles, so a plate with a hexagonal outline came back with 18 triangulated
faces instead of 8, and was no longer a solid.
"""

import math

import pytest
from compas.datastructures import Mesh
from compas.geometry import Box
from compas.geometry import Point
from compas.geometry import Polygon

from compas_brep import Brep
from compas_brep.errors import BrepError

pytestmark = pytest.mark.rhino

# Must match ``PLANARITY_TOLERANCE`` in the Rhino backend, which in turn matches the
# limit OCC hardcodes. Pinned as a literal on purpose: a test that read the constant
# back out of the source could not catch a change to it, and a change to it is a change
# to what both backends accept.
PLANARITY_TOLERANCE = 2e-6


def _ngon_plate_polygons(n, radius=2.0, thickness=0.5):
    """The polygons of a plate with two n-gon caps, as compas_timber builds them."""
    bottom = [Point(radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
    top = [Point(point.x, point.y, thickness) for point in bottom]

    polygons = [Polygon(bottom[::-1]), Polygon(top)]
    for i in range(n):
        j = (i + 1) % n
        polygons.append(Polygon([bottom[i], top[i], top[j], bottom[j]]))

    return polygons


def test_from_polygons_keeps_ngon_faces():
    """A polygon with more than four points must stay one face, not a fan of triangles."""
    brep = Brep.from_polygons(_ngon_plate_polygons(6))
    assert len(brep.faces) == 8
    assert sorted(len(face.vertices) for face in brep.faces) == [4, 4, 4, 4, 4, 4, 6, 6]


def test_from_polygons_ngon_plate_is_a_solid():
    """The triangulated caps left the plate shell unsolid, which broke booleans downstream."""
    brep = Brep.from_polygons(_ngon_plate_polygons(6))
    assert brep.is_valid
    assert brep.is_solid
    assert brep.volume == pytest.approx(1.5 * math.sqrt(3) * 2.0**2 * 0.5)


def test_from_polygons_quads_only():
    brep = Brep.from_polygons(Brep.from_box(Box(1, 1, 1)).to_polygons())
    assert len(brep.faces) == 6
    assert brep.is_solid
    assert brep.volume == pytest.approx(1.0)


def test_from_mesh_triangles():
    brep = Brep.from_mesh(Mesh.from_polyhedron(4))
    assert len(brep.faces) == 4
    assert brep.is_valid
    assert brep.is_solid


def _warped_quad_mesh(warp):
    """A unit quad with one corner lifted out of the plane of the other three."""
    mesh = Mesh()
    corners = [(0, 0, 0), (1, 0, 0), (1, 1, warp), (0, 1, 0)]
    mesh.add_face([mesh.add_vertex(x=x, y=y, z=z) for x, y, z in corners])
    return mesh


def test_from_mesh_non_planar_quad_raises():
    """A quad OCC would refuse must be refused here too, not built as a warped patch."""
    with pytest.raises(BrepError):
        Brep.from_mesh(_warped_quad_mesh(0.5))


def test_from_mesh_quad_within_planarity_tolerance():
    """Rounding noise in a nominally flat quad must not be mistaken for a bend."""
    brep = Brep.from_mesh(_warped_quad_mesh(PLANARITY_TOLERANCE / 2))
    assert len(brep.faces) == 1
    assert brep.is_valid


def test_from_mesh_quad_beyond_planarity_tolerance_raises():
    with pytest.raises(BrepError):
        Brep.from_mesh(_warped_quad_mesh(PLANARITY_TOLERANCE * 2))


def test_from_mesh_non_planar_ngon_raises():
    """Refuse the face rather than silently fanning it into triangles."""
    mesh = Mesh()
    corners = [(0, 0, 0), (2, 0, 0), (3, 1, 0), (2, 2, 1.0), (0, 2, 0)]
    mesh.add_face([mesh.add_vertex(x=x, y=y, z=z) for x, y, z in corners])

    with pytest.raises(BrepError):
        Brep.from_mesh(mesh)
