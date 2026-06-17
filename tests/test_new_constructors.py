"""Smoke tests for Brep constructors and operations."""

import math

import pytest
from compas.datastructures import Mesh
from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Sphere
from compas.geometry import Vector

from compas_brep import Brep

pytestmark = pytest.mark.occ


def test_from_mesh():
    mesh = Mesh.from_polyhedron(6)
    brep = Brep.from_mesh(mesh)
    assert len(brep.faces) > 0


def test_from_cylinder():
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)
    assert len(brep.faces) >= 3
    vol = brep.volume
    expected = math.pi * 0.5**2 * 2.0
    assert abs(vol - expected) < 0.1


def test_from_sphere():
    sph = Sphere(1.0)
    brep = Brep.from_sphere(sph)
    assert len(brep.faces) > 0
    vol = brep.volume
    expected = (4.0 / 3.0) * math.pi
    assert abs(vol - expected) < 0.3


def test_from_plane():
    brep = Brep.from_plane(Plane.worldXY(), domain_u=(-5, 5), domain_v=(-5, 5))
    assert len(brep.faces) == 1


def test_from_extrusion():
    box = Box(1, 1, 0.01)
    face_brep = Brep.from_box(box)
    ext = Brep.from_extrusion(face_brep.faces[0], Vector(0, 0, 2))
    assert len(ext.faces) >= 4


def test_split():
    box_brep = Brep.from_box(Box(2, 2, 2))
    plane = Plane(Point(0, 0, 0), Vector(1, 0, 0))
    halves = box_brep.split(Brep.from_plane(plane, domain_u=(-5, 5), domain_v=(-5, 5)))
    assert len(halves) == 2
    for h in halves:
        assert h.volume > 0


def test_slice():
    box_brep = Brep.from_box(Box(2, 2, 2))
    plane = Plane(Point(0, 0, 0), Vector(1, 0, 0))
    slices = box_brep.slice(plane)
    assert len(slices) > 0


def test_trimmed():
    box_brep = Brep.from_box(Box(2, 2, 2))
    plane = Plane(Point(0, 0, 0), Vector(1, 0, 0))
    half = box_brep.trimmed(plane)
    assert len(half.faces) > 0
    assert abs(half.volume - 4.0) < 0.1
