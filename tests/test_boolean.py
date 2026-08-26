"""Tests for boolean operations on Brep."""

import pytest
from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import Frame
from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Vector

from compas_brep import Brep

pytestmark = pytest.mark.occ


def test_brep_from_box():
    box = Box(2.0, 2.0, 2.0)
    brep = Brep.from_box(box)
    assert len(brep.faces) == 6
    assert len(brep.vertices) == 8
    assert brep.is_valid
    assert abs(brep.volume - 8.0) < 0.01


def test_boolean_subtraction():
    box_a = Box(2.0, 2.0, 2.0)
    box_b = Box(1.0, 1.0, 1.0, Frame(Point(0.5, 0.5, 0.5), Vector(1, 0, 0), Vector(0, 1, 0)))

    brep_a = Brep.from_box(box_a)
    brep_b = Brep.from_box(box_b)

    result = (brep_a - brep_b)[0]

    assert result.is_valid
    assert len(result.faces) >= 6  # At least as many faces as original box
    # Volume should be box_a - overlap
    assert result.volume < brep_a.volume
    assert result.volume > 0


def test_boolean_union():
    box_a = Box(2.0, 2.0, 2.0)
    box_b = Box(2.0, 2.0, 2.0, Frame(Point(1.0, 0, 0), Vector(1, 0, 0), Vector(0, 1, 0)))

    brep_a = Brep.from_box(box_a)
    brep_b = Brep.from_box(box_b)

    result = (brep_a + brep_b)[0]

    assert result.is_valid
    assert result.volume > brep_a.volume
    assert result.volume < brep_a.volume + brep_b.volume  # Less due to overlap


def test_boolean_intersection():
    box_a = Box(2.0, 2.0, 2.0)
    box_b = Box(2.0, 2.0, 2.0, Frame(Point(0.5, 0.5, 0.5), Vector(1, 0, 0), Vector(0, 1, 0)))

    brep_a = Brep.from_box(box_a)
    brep_b = Brep.from_box(box_b)

    result = (brep_a & brep_b)[0]

    assert result.is_valid
    assert result.volume < brep_a.volume
    assert result.volume < brep_b.volume
    assert result.volume > 0


def test_to_viewmesh():
    box = Box(1.0, 1.0, 1.0)
    brep = Brep.from_box(box)
    mesh = brep.to_viewmesh()
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0


def test_to_meshes():
    box = Box(1.0, 1.0, 1.0)
    brep = Brep.from_box(box)
    meshes = brep.to_meshes()
    assert len(meshes) == 1  # One combined mesh


def test_boolean_subtraction_splitting_returns_one_brep_per_solid():
    """A slab cut clean through a box leaves two disconnected solids, not one."""
    box = Brep.from_box(Box(4.0, 4.0, 4.0))
    slab = Brep.from_box(Box(6.0, 6.0, 1.0))

    results = Brep.from_boolean_difference(box, slab)

    assert len(results) == 2
    for result in results:
        assert result.is_valid
        assert len(result.faces) == 6
        assert abs(result.volume - 24.0) < 1e-6
    assert abs(sum(result.volume for result in results) - 48.0) < 1e-6


def test_boolean_subtraction_operator_matches_from_boolean_difference():
    """`-` is the operator spelling of from_boolean_difference, list result and all."""
    box = Brep.from_box(Box(4.0, 4.0, 4.0))
    slab = Brep.from_box(Box(6.0, 6.0, 1.0))

    results = box - slab

    assert len(results) == 2
    assert [round(result.volume, 6) for result in results] == [24.0, 24.0]


def test_boolean_difference_returns_list_even_when_connected():
    """One solid still comes back as a list of one, not a bare Brep."""
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    corner = Brep.from_box(Box(1.0, 1.0, 1.0, Frame(Point(1.0, 1.0, 1.0), Vector(1, 0, 0), Vector(0, 1, 0))))

    results = Brep.from_boolean_difference(box, corner)

    assert len(results) == 1
    # boxes are centred, so the corner overlaps an 0.5 cube: 8.0 - 0.125
    assert abs(results[0].volume - 7.875) < 1e-6


def test_boolean_intersection_of_disjoint_breps_is_empty():
    box_a = Brep.from_box(Box(1.0, 1.0, 1.0))
    box_b = Brep.from_box(Box(1.0, 1.0, 1.0, Frame(Point(10.0, 0, 0), Vector(1, 0, 0), Vector(0, 1, 0))))

    assert Brep.from_boolean_intersection(box_a, box_b) == []


def test_boolean_difference_on_a_surface_returns_the_trimmed_face():
    """A boolean on a surface yields a face, not a solid, and must not be filtered out."""
    surface = Brep.from_plane(Plane.worldXY(), domain_u=(-2, 2), domain_v=(-2, 2))
    hole = Brep.from_cylinder(Cylinder(0.5, 4.0, frame=Frame.worldXY()))

    results = Brep.from_boolean_difference(surface, hole)

    assert len(results) == 1
    assert len(results[0].faces) == 1
    assert not results[0].is_solid


def test_boolean_union_of_disjoint_breps_returns_both():
    """A union cannot merge what does not touch, so both solids come back."""
    a = Brep.from_box(Box(2.0, 2.0, 2.0))
    far = Brep.from_box(Box(1.0, 1.0, 1.0, Frame(Point(50.0, 0, 0), Vector(1, 0, 0), Vector(0, 1, 0))))

    results = Brep.from_boolean_union(a, far)

    assert len(results) == 2
    assert sorted(round(result.volume, 6) for result in results) == [1.0, 8.0]


def test_boolean_intersection_can_return_several_pieces():
    """Two *connected* solids can share a region that is itself disconnected."""
    block = Brep.from_box(Box(6.0, 2.0, 4.0))
    notch = Brep.from_box(Box(3.0, 4.0, 3.0, Frame(Point(0, 0, 0.9), Vector(1, 0, 0), Vector(0, 1, 0))))
    u_shape = Brep.from_boolean_difference(block, notch)
    assert len(u_shape) == 1  # the U itself is a single connected solid

    # a bar spanning both prongs, clear of the notch between them
    crossbar = Brep.from_box(Box(8.0, 1.0, 0.8, Frame(Point(0, 0, 1.6), Vector(1, 0, 0), Vector(0, 1, 0))))

    results = Brep.from_boolean_intersection(u_shape[0], crossbar)

    assert len(results) == 2
    assert [round(result.volume, 6) for result in results] == [1.2, 1.2]
