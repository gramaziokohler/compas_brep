"""Tests for Brep STEP-inspired JSON serialization and tessellation."""

import copy
import json
import math

import pytest
from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import Sphere
from compas.tolerance import TOL

from compas_brep import Brep
from compas_brep.errors import BrepError

pytestmark = pytest.mark.occ


def test_serialize_step_format_box():
    """__data__ produces STEP-inspired JSON (version 6) with correct entity counts."""
    box = Box(2.0, 2.0, 2.0)
    brep = Brep.from_box(box)
    data = brep.__data__

    assert data["version"] == 6
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
    """Cylinder __data__ contains cylinder surface data in STEP format (not NURBS approximation)."""
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)
    data = brep.__data__

    assert data["version"] == 6
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "cylinder" in surface_types


def test_roundtrip_cylinder():
    """Round-trip: cylinder → serialize → deserialize → face count and volume match."""
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)
    data = brep.__data__

    restored = Brep.__from_data__(data)
    assert len(restored.faces) == len(brep.faces)
    expected = math.pi * 0.5**2 * 2.0
    assert abs(restored.volume - expected) < 0.1


def test_serialize_json_roundtrip_cylinder():
    """Brep survives a full json.dumps/loads round-trip."""
    cyl = Cylinder(0.5, 2.0)
    brep = Brep.from_cylinder(cyl)

    data = brep.__data__
    json_str = json.dumps(data)
    data_back = json.loads(json_str)
    restored = Brep.__from_data__(data_back)

    expected = math.pi * 0.5**2 * 2.0
    assert abs(restored.volume - expected) < 0.1


def test_serialize_boolean_result():
    """Boolean result with mixed planar+spherical faces serializes correctly."""
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    sph = Brep.from_sphere(Sphere(0.3))
    result = box - sph

    data = result.__data__
    assert data["version"] == 6
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "plane" in surface_types
    assert "sphere" in surface_types

    restored = Brep.__from_data__(data)
    assert len(restored.faces) == len(result.faces)


# =============================================================================
# v6 format: explicit loop roles, non-nullable pcurves
# =============================================================================


def _downgrade_document(data, version):
    """Rewrite a v6 document into its v4/v5 shape: bare trim lists, outer loop first.

    Those versions encoded loop role by position, so this is what a pre-v6 writer
    would have emitted for the same shape.
    """
    legacy = copy.deepcopy(data)
    legacy["version"] = version
    for face in legacy["faces"]:
        outer = [loop["trims"] for loop in face["loops"] if loop["type"] == "outer"]
        inner = [loop["trims"] for loop in face["loops"] if loop["type"] == "inner"]
        face["loops"] = outer + inner
    return legacy


def _box_with_hole():
    """A box with a cylinder cut clean through it, so two faces carry an inner loop."""
    return Brep.from_box(Box(2.0, 2.0, 2.0)) - Brep.from_cylinder(Cylinder(0.3, 4.0))


def test_v6_loops_are_tagged_with_a_role():
    """Every loop carries an explicit role, and every face has exactly one outer loop."""
    data = _box_with_hole().__data__

    assert data["version"] == 6
    for face in data["faces"]:
        roles = [loop["type"] for loop in face["loops"]]
        assert set(roles) <= {"outer", "inner"}
        assert roles.count("outer") == 1
        for loop in face["loops"]:
            assert len(loop["trims"]) > 0

    # The hole gives at least one face an inner loop, so the tag is load-bearing here.
    assert any("inner" in [loop["type"] for loop in face["loops"]] for face in data["faces"])


def test_v6_pcurve_is_never_null():
    """curve_2d is non-nullable in v6: every trim carries a pcurve."""
    data = _box_with_hole().__data__

    trims = [t for f in data["faces"] for loop in f["loops"] for t in loop["trims"]]
    assert len(trims) > 0
    assert all(t["curve_2d"] is not None for t in trims)


def test_v6_null_pcurve_raises():
    """A v6 document with a null pcurve is rejected rather than rebuilt approximately."""
    data = _box_with_hole().__data__
    data["faces"][0]["loops"][0]["trims"][0]["curve_2d"] = None

    with pytest.raises(BrepError):
        Brep.__from_data__(data)


def test_v5_null_pcurve_still_deserializes():
    """v5 allowed a null pcurve, so a v5 document carrying one still loads."""
    original = Brep.from_box(Box(2.0, 2.0, 2.0))
    legacy = _downgrade_document(original.__data__, 5)
    for face in legacy["faces"]:
        for trims in face["loops"]:
            for trim in trims:
                trim["curve_2d"] = None

    restored = Brep.__from_data__(json.loads(json.dumps(legacy)))
    assert len(restored.faces) == len(original.faces)
    assert TOL.is_close(restored.volume, original.volume)


def test_v6_loop_order_does_not_change_the_rebuilt_shape():
    """Reordering the loops array is a no-op: role comes from the tag, not the position."""
    original = _box_with_hole()
    data = original.__data__

    shuffled = copy.deepcopy(data)
    for face in shuffled["faces"]:
        face["loops"].reverse()

    # Guard the test itself: reversing must actually move an outer loop off index 0,
    # otherwise this would pass against a positional reader too.
    assert any(face["loops"][0]["type"] == "inner" for face in shuffled["faces"])

    restored = Brep.__from_data__(json.loads(json.dumps(shuffled)))
    assert len(restored.faces) == len(original.faces)
    assert TOL.is_close(restored.volume, original.volume)


def test_v6_face_with_no_outer_loop_raises():
    """A face whose loops are all tagged inner is an error, not a silent guess."""
    data = _box_with_hole().__data__
    for loop in data["faces"][0]["loops"]:
        loop["type"] = "inner"

    with pytest.raises(BrepError):
        Brep.__from_data__(data)


def test_v6_face_with_multiple_outer_loops_raises():
    """A face with more than one outer loop is an error, not a silent guess."""
    data = _box_with_hole().__data__
    face = next(f for f in data["faces"] if len(f["loops"]) > 1)
    for loop in face["loops"]:
        loop["type"] = "outer"

    with pytest.raises(BrepError):
        Brep.__from_data__(data)


def test_v6_unknown_loop_role_raises():
    """A role the format does not define is an error rather than an assumed default."""
    data = _box_with_hole().__data__
    data["faces"][0]["loops"][0]["type"] = "slit"

    with pytest.raises(BrepError):
        Brep.__from_data__(data)


def test_roundtrip_box_with_hole():
    """A box with a through-hole round-trips with the hole intact."""
    original = _box_with_hole()
    data = original.__data__

    restored = Brep.__from_data__(json.loads(json.dumps(data)))
    assert len(restored.faces) == len(original.faces)
    assert TOL.is_close(restored.volume, original.volume)


def test_deserialize_v5_document():
    """A v5 document still deserializes: loops[0] is read as the outer loop."""
    original = _box_with_hole()
    legacy = _downgrade_document(original.__data__, 5)

    restored = Brep.__from_data__(json.loads(json.dumps(legacy)))
    assert len(restored.faces) == len(original.faces)
    assert TOL.is_close(restored.volume, original.volume)


def test_deserialize_v4_document():
    """A v4-version-tagged document (plane + sphere faces) still deserializes correctly."""
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    sph = Brep.from_sphere(Sphere(0.3))
    result = box - sph

    # The codec handles all surface types regardless of version number; this
    # verifies the reader doesn't gate on it.
    data = _downgrade_document(result.__data__, 4)
    json_str = json.dumps(data)
    restored = Brep.__from_data__(json.loads(json_str))

    assert len(restored.faces) == len(result.faces)
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "plane" in surface_types
    assert "sphere" in surface_types


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
