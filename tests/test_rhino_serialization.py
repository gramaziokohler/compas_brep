"""Rhino backend serialization round-trip tests (issue 06).

Mirrors the OCC serialization tests in test_serialization.py.
Requires rhinoinside to be installed; all tests are marked @pytest.mark.rhino
and are skipped automatically in non-Rhino environments.

To run: pytest -m rhino tests/test_rhino_serialization.py
"""

import json
import math
from pathlib import Path

import pytest
from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import Sphere
from compas.tolerance import TOL

from compas_brep import Brep
from compas_brep.errors import BrepError

pytestmark = pytest.mark.rhino


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def unit_box_brep():
    return Brep.from_box(Box(1.0, 1.0, 1.0))


@pytest.fixture
def boolean_diff_brep():
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    cyl = Brep.from_cylinder(Cylinder(0.3, 4.0))
    return box - cyl


# =============================================================================
# 1. Serialization format
# =============================================================================


def test_serialization_format_box_data_version(unit_box_brep):
    data = unit_box_brep.__data__
    assert data["version"] == 6


def test_serialization_format_box_data_keys(unit_box_brep):
    data = unit_box_brep.__data__
    assert "vertices" in data
    assert "edges" in data
    assert "faces" in data


def test_serialization_format_box_entity_counts(unit_box_brep):
    data = unit_box_brep.__data__
    assert len(data["vertices"]) == 8
    assert len(data["edges"]) == 12
    assert len(data["faces"]) == 6


def test_serialization_format_json_serializable(unit_box_brep):
    data = unit_box_brep.__data__
    json_str = json.dumps(data)
    assert len(json_str) > 0


# =============================================================================
# 2. Round-trip: unit box
# =============================================================================


def test_round_trip_box_face_count_preserved(unit_box_brep):
    data = unit_box_brep.__data__
    restored = Brep.__from_data__(data)
    assert len(restored.faces) == 6


def test_round_trip_box_vertex_count_preserved(unit_box_brep):
    data = unit_box_brep.__data__
    restored = Brep.__from_data__(data)
    assert len(restored.vertices) == 8


def test_round_trip_box_edge_count_preserved(unit_box_brep):
    data = unit_box_brep.__data__
    restored = Brep.__from_data__(data)
    assert len(restored.edges) == 12


def test_round_trip_box_volume_matches(unit_box_brep):
    data = unit_box_brep.__data__
    restored = Brep.__from_data__(data)
    assert abs(restored.volume - unit_box_brep.volume) < 0.01


def test_round_trip_box_json_roundtrip(unit_box_brep):
    data = unit_box_brep.__data__
    json_str = json.dumps(data)
    data_back = json.loads(json_str)
    restored = Brep.__from_data__(data_back)
    assert len(restored.faces) == 6
    assert abs(restored.volume - 1.0) < 0.01


# =============================================================================
# 3. Round-trip: boolean-subtracted shape
# =============================================================================


def test_round_trip_boolean_diff_volume_matches(boolean_diff_brep):
    expected_volume = boolean_diff_brep.volume
    data = boolean_diff_brep.__data__
    restored = Brep.__from_data__(data)
    # 5% relative tolerance for NURBS approximation error
    assert abs(restored.volume - expected_volume) / expected_volume < 0.05


def test_round_trip_boolean_diff_mixed_surface_types_in_data(boolean_diff_brep):
    data = boolean_diff_brep.__data__
    surface_types = [f["surface"]["type"] for f in data["faces"]]
    assert "plane" in surface_types
    assert "nurbs" in surface_types


# =============================================================================
# 4. Cross-backend: OCC → Rhino deserialization
# =============================================================================


# Verify that a JSON payload from the OCC backend is accepted by the Rhino backend.
# These tests run in a Rhino environment where OCC is typically NOT installed,
# so the OCC payload is supplied as a static dict rather than generated live.

# The v4 unit-box document lives in tests/fixtures/legacy_v4_box.json — one copy,
# read by OCC on CI as well as by Rhino here. See tests/test_exchange_fixtures.py.


def _unit_box_occ_data():
    with open(Path(__file__).parent / "fixtures" / "legacy_v4_box.json") as f:
        return json.load(f)


def test_cross_backend_deserialization_occ_payload_deserializes():
    restored = Brep.__from_data__(_unit_box_occ_data())
    assert len(restored.faces) == 6


def test_cross_backend_deserialization_occ_payload_volume():
    restored = Brep.__from_data__(_unit_box_occ_data())
    assert abs(restored.volume - 1.0) < 0.05


def test_cross_backend_deserialization_cylinder_from_rhino_roundtrip():
    cyl = Brep.from_cylinder(Cylinder(0.5, 2.0))
    data = cyl.__data__
    restored = Brep.__from_data__(data)
    expected = math.pi * 0.5**2 * 2.0
    assert abs(restored.volume - expected) < 0.1


# =============================================================================
# 6. Rebuild through the low-level Brep builder (ADR-0002)
# =============================================================================


def test_builder_filleted_box_face_count_preserved():
    # The rectangular-crop path rebuilt each fillet as a rectangular sheet and
    # lost 8 of the 26 faces. This is the case that motivated the builder.
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    filleted = box.filleted(0.3)
    restored = Brep.__from_data__(filleted.__data__)
    assert len(restored.faces) == len(filleted.faces)


def test_builder_filleted_box_volume_preserved():
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    filleted = box.filleted(0.3)
    restored = Brep.__from_data__(filleted.__data__)
    assert TOL.is_close(restored.volume, filleted.volume)


def test_builder_filleted_box_is_valid():
    box = Brep.from_box(Box(2.0, 2.0, 2.0))
    filleted = box.filleted(0.3)
    restored = Brep.__from_data__(filleted.__data__)
    assert restored.is_valid


def test_builder_boolean_cut_cylinder_face_count_preserved(boolean_diff_brep):
    restored = Brep.__from_data__(boolean_diff_brep.__data__)
    assert len(restored.faces) == len(boolean_diff_brep.faces)


def test_builder_boolean_cut_cylinder_volume_preserved(boolean_diff_brep):
    restored = Brep.__from_data__(boolean_diff_brep.__data__)
    assert TOL.is_close(restored.volume, boolean_diff_brep.volume)


def test_builder_boolean_cut_cylinder_is_valid(boolean_diff_brep):
    restored = Brep.__from_data__(boolean_diff_brep.__data__)
    assert restored.is_valid


def test_builder_sphere_serializes_pole_trims():
    # A sphere's poles are singular trims — no edge, collapsed to a vertex.
    # The pre-builder writer dropped them silently.
    sphere = Brep.from_sphere(Sphere(1.0))
    data = sphere.__data__
    singular = [t for f in data["faces"] for loop in f["loops"] for t in loop["trims"] if t["edge"] == -1]
    assert len(singular) == 2
    assert all(t["curve_2d"] is not None for t in singular)


def test_builder_sphere_is_valid():
    sphere = Brep.from_sphere(Sphere(1.0))
    restored = Brep.__from_data__(sphere.__data__)
    assert restored.is_valid


def test_builder_sphere_volume_preserved():
    sphere = Brep.from_sphere(Sphere(1.0))
    restored = Brep.__from_data__(sphere.__data__)
    assert TOL.is_close(restored.volume, sphere.volume)


def test_builder_rectangular_crop_helper_is_gone():
    from compas_brep.backend.rhino import conversion

    assert not hasattr(conversion, "_trim_nurbs_surface_from_2d")


# =============================================================================
# 6. v6 format: explicit loop roles, non-nullable pcurves
# =============================================================================


def test_v6_loops_are_tagged_with_a_role(boolean_diff_brep):
    """Every loop the Rhino writer emits carries a role; every face has one outer loop."""
    data = boolean_diff_brep.__data__

    assert data["version"] == 6
    for face in data["faces"]:
        roles = [loop["type"] for loop in face["loops"]]
        assert set(roles) <= {"outer", "inner"}
        assert roles.count("outer") == 1

    # The cut goes clean through, so at least one face is holed and the tag matters.
    assert any("inner" in [loop["type"] for loop in face["loops"]] for face in data["faces"])


def test_v6_pcurve_is_never_null(boolean_diff_brep):
    """curve_2d is non-nullable in v6: the Rhino writer emits a pcurve for every trim."""
    data = boolean_diff_brep.__data__

    trims = [t for f in data["faces"] for loop in f["loops"] for t in loop["trims"]]
    assert len(trims) > 0
    assert all(t["curve_2d"] is not None for t in trims)


def test_v6_loop_order_does_not_change_the_rebuilt_shape(boolean_diff_brep):
    """Reordering the loops array is a no-op: role comes from the tag, not the position."""
    data = boolean_diff_brep.__data__

    shuffled = json.loads(json.dumps(data))
    for face in shuffled["faces"]:
        face["loops"].reverse()

    # Guard the test itself: reversing must actually move an outer loop off index 0,
    # otherwise this would pass against a positional reader too.
    assert any(face["loops"][0]["type"] == "inner" for face in shuffled["faces"])

    restored = Brep.__from_data__(shuffled)
    assert len(restored.faces) == len(boolean_diff_brep.faces)
    assert TOL.is_close(restored.volume, boolean_diff_brep.volume)


def test_v6_face_with_no_outer_loop_raises(boolean_diff_brep):
    """A face whose loops are all tagged inner is an error, not a silent guess."""
    data = boolean_diff_brep.__data__
    for loop in data["faces"][0]["loops"]:
        loop["type"] = "inner"

    with pytest.raises(BrepError):
        Brep.__from_data__(data)


def test_v6_null_pcurve_raises(boolean_diff_brep):
    """A v6 document with a null pcurve is rejected rather than rebuilt approximately."""
    data = boolean_diff_brep.__data__
    data["faces"][0]["loops"][0]["trims"][0]["curve_2d"] = None

    with pytest.raises(BrepError):
        Brep.__from_data__(data)


def test_roundtrip_box_with_hole(boolean_diff_brep):
    """A box with a through-hole round-trips with the hole intact."""
    restored = Brep.__from_data__(json.loads(json.dumps(boolean_diff_brep.__data__)))

    assert len(restored.faces) == len(boolean_diff_brep.faces)
    assert TOL.is_close(restored.volume, boolean_diff_brep.volume)
