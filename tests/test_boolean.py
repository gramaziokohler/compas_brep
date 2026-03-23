"""Tests for boolean operations on Brep."""

from compas.geometry import Box, Frame, Point, Vector

from compas_brep import Brep


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

    result = brep_a - brep_b

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

    result = brep_a + brep_b

    assert result.is_valid
    assert result.volume > brep_a.volume
    assert result.volume < brep_a.volume + brep_b.volume  # Less due to overlap


def test_boolean_intersection():
    box_a = Box(2.0, 2.0, 2.0)
    box_b = Box(2.0, 2.0, 2.0, Frame(Point(0.5, 0.5, 0.5), Vector(1, 0, 0), Vector(0, 1, 0)))

    brep_a = Brep.from_box(box_a)
    brep_b = Brep.from_box(box_b)

    result = brep_a & brep_b

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
    assert len(meshes) == 6  # One mesh per face
