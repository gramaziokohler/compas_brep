"""Tests for Brep STEP-inspired JSON serialization and tessellation."""

import json
import math

import pytest
from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import Sphere

from compas_brep import Brep

pytestmark = pytest.mark.occ


def test_serialize_step_format_box():
    """__data__ produces STEP-inspired JSON (version 4) with correct entity counts."""
    box = Box(2.0, 2.0, 2.0)
    brep = Brep.from_box(box)
    data = brep.__data__

    assert data["version"] == 4
    assert "vertices" in data
    assert "edges" in data
    assert "faces" in data
    assert len(data["vertices"]) == 8
    assert len(data["edges"]) == 12
    assert len(data["faces"]) == 6


def test_serialize_json_roundtrip():
    """__data__ is JSON-serializable and round-trips via json.dumps/loads."""
    box = Box(1.0, 1.0, 1.0)
    brep = Brep.from_box(box)
    data = brep.__data__
    json_str = json.dumps(data)
    data_back = json.loads(json_str)
    restored = Brep.__from_data__(data_back)
    assert len(restored.faces) == 6
    assert abs(restored.volume - 1.0) < 0.01


def test_roundtrip_box():
    """Round-trip: box → serialize → deserialize → volume and topology match."""
    box = Box(2.0, 2.0, 2.0)
    brep = Brep.from_box(box)
    data = brep.__data__

    restored = Brep.__from_data__(data)
    assert len(restored.faces) == 6
    assert len(restored.vertices) == 8
    assert abs(restored.volume - brep.volume) < 0.01
    # Confirm topology is accessible
    assert len(restored.edges) == 12


def test_roundtrip_boolean_difference():
    """Round-trip: boolean-subtracted shape → serialize → deserialize → volume within 5%."""
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    cyl = Brep.from_cylinder(Cylinder(0.3, 4.0))
    result = box - cyl
    expected_volume = result.volume

    data = result.__data__
    restored = Brep.__from_data__(data)
    # Allow 5% relative error for NURBS surface round-trip approximation
    assert abs(restored.volume - expected_volume) / expected_volume < 0.05


def test_serialize_step_format_cylinder():
    """Cylinder __data__ contains NURBS surface data in STEP format."""
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)
    data = brep.__data__

    assert data["version"] == 4
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "nurbs" in surface_types


def test_roundtrip_cylinder():
    """Round-trip: cylinder → serialize → deserialize → face count and volume match."""
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)
    data = brep.__data__

    restored = Brep.__from_data__(data)
    assert len(restored.faces) == len(brep.faces)
    expected = math.pi * 0.5**2 * 2.0
    assert abs(restored.volume - expected) < 0.1


def test_serialize_with_tessellation_cache():
    """Tessellation cache is preserved through serialization."""
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)

    assert brep.cache_tessellation is True
    mesh, boundaries = brep.to_tesselation(n=16)
    assert mesh.number_of_vertices() > 50

    data = brep.__data__
    assert "tessellation" in data
    assert len(data["tessellation"]["vertices"]) > 50

    restored = Brep.__from_data__(data)
    assert restored._tessellation_cache is not None
    mesh_r, bounds_r = restored.to_tesselation()
    assert mesh_r.number_of_vertices() == mesh.number_of_vertices()
    assert len(bounds_r) == len(boundaries)


def test_serialize_json_roundtrip_with_cache():
    """Tessellation cache survives a full json.dumps/loads round-trip."""
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)
    brep.to_tesselation(n=16)

    data = brep.__data__
    json_str = json.dumps(data)
    data_back = json.loads(json_str)
    restored = Brep.__from_data__(data_back)
    assert restored._tessellation_cache is not None

    expected = math.pi * 0.5**2 * 2.0
    assert abs(restored.volume - expected) < 0.1


def test_serialize_boolean_result():
    """Boolean result with mixed planar+NURBS faces serializes correctly."""
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    cyl = Brep.from_cylinder(Cylinder(0.3, 4.0))
    result = box - cyl

    data = result.__data__
    assert data["version"] == 4
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "plane" in surface_types
    assert "nurbs" in surface_types

    restored = Brep.__from_data__(data)
    assert len(restored.faces) == len(result.faces)


def test_viewmesh_box():
    """Box viewmesh has correct structure."""
    box = Brep.from_box(Box(1.0, 1.0, 1.0))
    mesh = box.to_viewmesh()
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0


def test_viewmesh_cylinder_smooth():
    """Cylinder viewmesh produces smooth tessellation."""
    cyl = Brep.from_cylinder(Cylinder(0.5, 2.0))
    mesh = cyl.to_viewmesh(n=16)
    assert mesh.number_of_vertices() > 50
    assert mesh.number_of_faces() > 50


def test_to_meshes_cylinder():
    """to_meshes produces a single combined mesh via brep_tessellate."""
    cyl = Brep.from_cylinder(Cylinder(0.5, 2.0))
    meshes = cyl.to_meshes(u=8)
    assert len(meshes) == 1
    assert meshes[0].number_of_faces() > 10


def test_tesselation_cylinder():
    """to_tesselation produces smooth mesh and boundary polylines."""
    cyl = Brep.from_cylinder(Cylinder(0.5, 2.0))
    mesh, boundaries = cyl.to_tesselation(n=16)
    assert mesh.number_of_vertices() > 50
    assert len(boundaries) > 0
    max_pts = max(len(b.points) for b in boundaries)
    assert max_pts > 4


def test_viewmesh_sphere_smooth():
    """Sphere viewmesh produces smooth tessellation."""
    sph = Brep.from_sphere(Sphere(1.0))
    mesh = sph.to_viewmesh(n=16)
    assert mesh.number_of_vertices() > 100
    assert mesh.number_of_faces() > 100


def test_tessellation_cache_invalidation():
    """Tessellation cache is cleared when the brep is modified."""
    box = Brep.from_box(Box(1.0, 1.0, 1.0))
    box.to_tesselation()
    assert box._tessellation_cache is not None

    box._invalidate_native()
    assert box._tessellation_cache is None


def test_restored_brep_tessellatable():
    """A deserialized Brep can be tessellated without errors."""
    box = Brep.from_box(Box(1.0, 1.0, 1.0))
    data = box.__data__
    restored = Brep.__from_data__(data)
    mesh = restored.to_viewmesh()
    assert mesh.number_of_vertices() > 0
