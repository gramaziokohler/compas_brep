"""Tests for the compas.geometry.Brep-compatible sub-object API.

Covers the accessors that consumers written against ``compas.geometry.Brep``
(via ``compas_rhino`` or ``compas_occ``) expect to find on the topology
sub-objects.
"""

import pytest
from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import Frame

from compas_brep import Brep
from compas_brep import LoopType

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
