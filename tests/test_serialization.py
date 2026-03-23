"""Tests for Brep serialization and smooth visualization."""

import json
import math

from compas.geometry import Box, Cylinder, Sphere

from compas_brep import Brep


def test_serialize_box_roundtrip():
    """Box Brep serializes and deserializes preserving topology."""
    box = Box(2.0, 2.0, 2.0)
    brep = Brep.from_box(box)
    data = brep.__data__

    assert data["version"] == 3
    assert len(data["faces"]) == 6

    # Round-trip
    restored = Brep.__from_data__(data)
    assert len(restored.faces) == 6
    assert len(restored.vertices) == 8
    assert abs(restored.volume - brep.volume) < 0.01


def test_serialize_cylinder_roundtrip():
    """Cylinder Brep preserves NURBS surface data through serialization."""
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)
    data = brep.__data__

    assert data["version"] == 3
    # Check that we have at least one NURBS surface (the barrel)
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "nurbs" in surface_types

    # Round-trip
    restored = Brep.__from_data__(data)
    assert len(restored.faces) == len(brep.faces)
    # Check NURBS faces survived
    nurbs_faces = [f for f in restored.faces if f.is_nurbs]
    assert len(nurbs_faces) >= 1

    # Volume should roughly match. After round-trip, tessellation uses the
    # pure-Python UV-space trimmed path (no native OCC), so resolution is lower
    # and volume estimation is less precise.
    vol_original = brep.volume
    vol_restored = restored.volume
    expected = math.pi * 0.5**2 * 2.0
    assert abs(vol_original - expected) < 0.1
    assert abs(vol_restored - expected) < 0.4


def test_serialize_json_roundtrip():
    """Brep data is JSON-serializable (all native Python types)."""
    box = Box(1.0, 1.0, 1.0)
    brep = Brep.from_box(box)
    data = brep.__data__
    json_str = json.dumps(data)
    data_back = json.loads(json_str)
    restored = Brep.__from_data__(data_back)
    assert len(restored.faces) == 6
    assert abs(restored.volume - 1.0) < 0.01


def test_serialize_boolean_result():
    """Boolean result with mixed planar+NURBS faces serializes correctly."""
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    cyl = Brep.from_cylinder(Cylinder(0.3, 4.0))
    result = box - cyl

    data = result.__data__
    assert data["version"] == 3

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
    """Cylinder viewmesh produces smooth tessellation (many more verts than topology verts)."""
    cyl = Brep.from_cylinder(Cylinder(0.5, 2.0))
    mesh = cyl.to_viewmesh(n=16)
    # The NURBS barrel face should produce a UV grid (17*17 = 289 verts just for barrel)
    # Plus planar caps. Total should be much more than the 4 topology vertices.
    assert mesh.number_of_vertices() > 50
    assert mesh.number_of_faces() > 50


def test_to_meshes_cylinder():
    """to_meshes produces one mesh per face with smooth NURBS tessellation."""
    cyl = Brep.from_cylinder(Cylinder(0.5, 2.0))
    meshes = cyl.to_meshes(u=8)
    assert len(meshes) == len(cyl.faces)
    # The barrel mesh should have many faces (UV grid)
    barrel_meshes = [m for m in meshes if m.number_of_faces() > 10]
    assert len(barrel_meshes) >= 1


def test_tesselation_cylinder():
    """to_tesselation produces smooth mesh and boundary polylines."""
    cyl = Brep.from_cylinder(Cylinder(0.5, 2.0))
    mesh, boundaries = cyl.to_tesselation(n=16)
    assert mesh.number_of_vertices() > 50
    assert len(boundaries) > 0
    # At least one boundary should have many points (curved edge)
    max_pts = max(len(b.points) for b in boundaries)
    assert max_pts > 4  # More than a simple rectangle = curved edge sampled


def test_viewmesh_sphere_smooth():
    """Sphere viewmesh produces smooth tessellation."""
    sph = Brep.from_sphere(Sphere(1.0))
    mesh = sph.to_viewmesh(n=16)
    assert mesh.number_of_vertices() > 100
    assert mesh.number_of_faces() > 100
