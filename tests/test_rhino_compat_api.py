"""Rhino-backend coverage of the compas.geometry.Brep-compatible sub-object API.

Mirrors ``test_compas_brep_compat_api.py`` (which runs on OCC). The two backends
differ in what they can say about a curved face - Rhino converts every non-planar
surface to NURBS, so a cylindrical face reports ``surface_type == "nurbs"`` there -
so faces are selected by ``is_planar`` rather than by ``is_cylinder``.
"""

import pytest
from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import Frame

from compas_brep import Brep
from compas_brep import LoopType

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
    return Brep.from_boolean_difference(box, cylinder)


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
