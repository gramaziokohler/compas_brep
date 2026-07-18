"""The committed Rhino-authored exchange documents, read back by OCC.

This is the half of the contract harness that runs on CI. Every test here that
rebuilds a fixture is a Rhino -> OCC exchange executed without a Rhino license:
the Rhino half already happened, on a dev machine, and was committed.

See tests/exchange_fixtures.py for the source geometry and the refresh path.
"""

from __future__ import annotations

import json

import pytest
from compas.geometry import ConicalSurface
from compas.geometry import CylindricalSurface
from compas.geometry import SphericalSurface
from compas.geometry import ToroidalSurface
from compas.tolerance import TOL
from exchange_fixtures import FIXTURE_DIR
from exchange_fixtures import OCC_SOURCES
from exchange_fixtures import SOURCES
from exchange_fixtures import documents_differ
from exchange_fixtures import load_fixture
from exchange_fixtures import load_occ_fixture
from exchange_fixtures import write_fixture
from exchange_fixtures import write_occ_fixture

from compas_brep import Brep
from compas_brep.exchange import EXCHANGE_VERSION

# What each Rhino-authored fixture is expected to say.
#
# The surface tags are Rhino's as it stands. Slice 04 was the first to collect: a
# cylinder wall arrives tagged "cylinder", here and on the holed box. Slice 05
# finished the analytic set -- the sphere, cone, and torus fixtures now carry their
# own analytic tags instead of "nurbs", and the sphere fixture's OCC rebuild volume
# came within the 1e-3 bar as a result (it was a strict xfail as a NURBS blob).
#
# The filleted box's 20 curved faces stay "nurbs" even though 12 of them are exactly
# cylinders to Rhino, and OCC tags those 12 "cylinder". Rhino stores a fillet as a
# rational NURBS whose angle is not linear in either parameter, so its pcurves cannot
# be carried into the document's (angle, height) space exactly -- see
# `_cylinder_and_param_map`. Tagging them would mean writing trims that land at the
# wrong angle, which is worse than the "nurbs" tag, and "nurbs" reproduces those
# faces exactly. This is a real remaining divergence between the backends, not a
# rounding difference.
#
# ``volume_atol`` is the bar the OCC rebuild is held to. A planar box is exact; a
# document whose curved faces are NURBS carries approximation error at the scale of
# the wall's own discretization, so the holed box is held to 1e-3 rather than TOL.
#
# ``rebuild_broken`` marks a fixture whose OCC rebuild is wrong today -- see the
# xfails below. It is not a property of the fixture: the same shape authored by OCC
# itself fails the same way.
EXPECTED = {
    "box": {
        "faces": 6,
        "surface_tags": {"plane"},
        "loop_roles": {"outer"},
        "volume": 1.0,
        "volume_atol": 1e-6,
        "rebuild_broken": False,
    },
    "filleted_box": {
        "faces": 26,
        "surface_tags": {"plane", "nurbs"},
        "loop_roles": {"outer"},
        "volume": 7.563414,
        "volume_atol": 1e-3,
        "rebuild_broken": True,
    },
    "sphere": {
        "faces": 1,
        "surface_tags": {"sphere"},
        "loop_roles": {"outer"},
        "volume": 4.18879,
        "volume_atol": 1e-3,
        "rebuild_broken": False,
    },
    "box_with_hole": {
        "faces": 7,
        "surface_tags": {"plane", "cylinder"},
        "loop_roles": {"outer", "inner"},
        "volume": 7.434513,
        "volume_atol": 1e-3,
        "rebuild_broken": False,
    },
    # The wall's surface is now analytic and exact, but its cap edges are still
    # written as NURBS circles, and a NURBS circle's parameter is not its angle.
    # The wall's pcurves run linearly in angle, so pcurve and edge curve trace the
    # same circle at different rates and OCC's rebuilt wall is slightly off. Slice 06
    # (analytic edge curve tags) is what makes a seam an exact circle; this atol
    # should tighten to TOL when it lands.
    "cylinder": {
        "faces": 3,
        "surface_tags": {"plane", "cylinder"},
        "loop_roles": {"outer"},
        "volume": 1.570796,
        "volume_atol": 1e-3,
        "rebuild_broken": False,
    },
    # The cone and torus join the cylinder as analytic surfaces whose seam / cap
    # edges are still written as NURBS circles, so the same 1e-3 residual applies
    # and the same slice 06 tightens it. A cone's caps make it a solid with a
    # planar base (like the cylinder); a torus has neither cap nor seam vertex.
    "cone": {
        "faces": 2,
        "surface_tags": {"plane", "cone"},
        "loop_roles": {"outer"},
        "volume": 0.261799,
        "volume_atol": 1e-3,
        "rebuild_broken": False,
    },
    "torus": {
        "faces": 1,
        "surface_tags": {"torus"},
        "loop_roles": {"outer"},
        "volume": 1.776529,
        "volume_atol": 1e-3,
        "rebuild_broken": False,
    },
}

FIXTURE_NAMES = sorted(EXPECTED)


def _surface_tags(data: dict) -> set:
    return {face["surface"]["type"] for face in data["faces"]}


def _loop_roles(data: dict) -> set:
    return {loop["type"] for face in data["faces"] for loop in face["loops"]}


def _trims(data: dict) -> list:
    return [trim for face in data["faces"] for loop in face["loops"] for trim in loop["trims"]]


# =============================================================================
# 1. The fixtures are well-formed v6 documents
# =============================================================================


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_is_current_version(name):
    assert load_fixture(name)["version"] == EXCHANGE_VERSION


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_every_face_has_exactly_one_outer_loop(name):
    for face in load_fixture(name)["faces"]:
        roles = [loop["type"] for loop in face["loops"]]
        assert set(roles) <= {"outer", "inner"}
        assert roles.count("outer") == 1


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_no_trim_has_a_null_pcurve(name):
    trims = _trims(load_fixture(name))
    assert len(trims) > 0
    assert all(trim["curve_2d"] is not None for trim in trims)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_says_what_it_is_expected_to_say(name):
    data = load_fixture(name)
    expected = EXPECTED[name]

    assert len(data["faces"]) == expected["faces"]
    assert _surface_tags(data) == expected["surface_tags"]
    assert _loop_roles(data) == expected["loop_roles"]


def test_fixture_box_with_hole_actually_has_an_inner_loop():
    # Guards the harness: without this, "inner loops survive" could pass on a
    # document that has none.
    data = load_fixture("box_with_hole")
    holed = [f for f in data["faces"] if any(loop["type"] == "inner" for loop in f["loops"])]
    assert len(holed) == 2


def test_fixture_sphere_carries_its_pole_trims():
    trims = _trims(load_fixture("sphere"))
    assert len([t for t in trims if t["edge"] == -1]) == 2


# =============================================================================
# 2. OCC reads what Rhino wrote
# =============================================================================


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuilds_fixture_with_face_count_intact(name):
    restored = Brep.__from_data__(load_fixture(name))
    assert len(restored.faces) == EXPECTED[name]["faces"]


# Why the volume of a curved fixture is wrong today: OCC's rebuild flips the
# orientation of some curved faces, so they contribute negative area and the volume
# comes out low. It is pre-existing and it is not a cross-backend problem -- an
# OCC-authored filleted box round-trips through OCC the same way.
_REBUILD_XFAIL = "OCC's rebuild flips the orientation of curved faces; see the note above."


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuilds_fixture_with_volume_intact(name, request):
    # xfail, not deleted: this assertion is what found the rebuild defect recorded
    # in .agents/issues/brep-exchange/progress.txt. strict=True, so whoever fixes
    # the rebuild is told to un-xfail it rather than left to discover it.
    if EXPECTED[name]["rebuild_broken"]:
        request.node.add_marker(pytest.mark.xfail(strict=True, reason=_REBUILD_XFAIL))

    restored = Brep.__from_data__(load_fixture(name))
    assert TOL.is_close(restored.volume, EXPECTED[name]["volume"], atol=EXPECTED[name]["volume_atol"])


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuild_preserves_surface_tags(name):
    # Re-serialize through OCC: a tag Rhino wrote that OCC cannot read would be
    # dropped or downgraded here rather than surviving the round-trip.
    reserialized = Brep.__from_data__(load_fixture(name)).__data__
    assert _surface_tags(reserialized) == EXPECTED[name]["surface_tags"]


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuild_preserves_loop_roles(name):
    reserialized = Brep.__from_data__(load_fixture(name)).__data__
    assert _loop_roles(reserialized) == EXPECTED[name]["loop_roles"]


@pytest.mark.occ
def test_occ_rebuild_keeps_the_hole_a_hole():
    # The hole subtracts its area rather than adding it — the defect slice 02 found,
    # here crossing from Rhino rather than round-tripping within OCC.
    restored = Brep.__from_data__(load_fixture("box_with_hole"))
    assert TOL.is_close(restored.volume, EXPECTED["box_with_hole"]["volume"], atol=1e-3)


@pytest.mark.occ
@pytest.mark.xfail(
    strict=True,
    reason="A rebuilt cylinder wall loses its seam edge and reports invalid — the known defect carried from slice 02, owned by slice 06 (analytic edge tags).",
)
def test_occ_rebuild_of_the_hole_is_valid():
    assert Brep.__from_data__(load_fixture("box_with_hole")).is_valid


@pytest.mark.occ
@pytest.mark.parametrize("name", ["cylinder", "box_with_hole"])
def test_occ_reads_a_rhino_authored_cylinder_as_an_analytic_cylinder(name):
    # The slice-04 tracer, running on CI without a Rhino license: Rhino authored a
    # cylinder wall and tagged it analytically, and OCC must rebuild it as a real
    # CylindricalSurface rather than a NURBS approximation of one. Asserting the
    # rebuilt type -- not a volume -- is the representational-fidelity bar.
    restored = Brep.__from_data__(load_fixture(name))

    walls = [face for face in restored.faces if face.is_cylinder]
    assert len(walls) == 1
    assert isinstance(walls[0].surface, CylindricalSurface)
    assert walls[0].surface_type == "cylinder"


@pytest.mark.occ
def test_occ_reads_the_rhino_cylinder_radius_and_axis():
    # Guards the tag against being right in name only: a CylindricalSurface with the
    # wrong radius or axis would still satisfy the type assertion above.
    wall = next(f for f in Brep.__from_data__(load_fixture("cylinder")).faces if f.is_cylinder)

    assert TOL.is_close(wall.surface.radius, 0.5)
    assert TOL.is_allclose(list(wall.surface.frame.zaxis), [0.0, 0.0, 1.0])


# (fixture name, predicate, COMPAS surface type) -- slice 05's analytic surfaces,
# authored by Rhino and read here by OCC on CI.
_RHINO_ANALYTIC_FIXTURES = [
    ("sphere", "is_sphere", SphericalSurface),
    ("cone", "is_cone", ConicalSurface),
    ("torus", "is_torus", ToroidalSurface),
]


@pytest.mark.occ
@pytest.mark.parametrize("name, predicate, surface_type", _RHINO_ANALYTIC_FIXTURES)
def test_occ_reads_a_rhino_authored_analytic_surface(name, predicate, surface_type):
    # Slice 05 on CI without a Rhino license: Rhino authored a sphere / cone / torus
    # and tagged it analytically, and OCC must rebuild the matching analytic surface
    # rather than a NURBS approximation. The document also spells the pole / apex as
    # Rhino's singular trim, which OCC must read.
    restored = Brep.__from_data__(load_fixture(name))

    faces = [f for f in restored.faces if getattr(f, predicate)]
    assert len(faces) == 1
    assert isinstance(faces[0].surface, surface_type)


@pytest.mark.occ
def test_occ_reads_the_rhino_cone_radius_and_height():
    # The convention the two kernels disagree on, pinned by value rather than volume.
    cone = next(f for f in Brep.__from_data__(load_fixture("cone")).faces if f.is_cone)

    assert TOL.is_close(cone.surface.radius, 0.5)
    assert TOL.is_close(cone.surface.height, 1.0)


# =============================================================================
# 3. The legacy v4 document still reads
# =============================================================================

# Slice 01 asked slice 03 to replace this hand-written document with a real
# backend-authored one. It cannot be: no backend has written v4 for two versions,
# so there is nothing to author it with, and regenerating it would just produce a
# v6 document under a v4 name. It stays hand-written on purpose.
#
# It moved out of test_rhino_serialization.py, where it was the only v4 document
# under test and was Rhino-marked — so the legacy read path was covered only on a
# machine that runs `-m rhino`, which is to say nowhere. Reading it from OCC puts
# v4 on CI.


def _legacy_v4_box() -> dict:
    with open(FIXTURE_DIR / "legacy_v4_box.json") as f:
        return json.load(f)


def test_legacy_v4_fixture_is_a_v4_document():
    data = _legacy_v4_box()
    assert data["version"] == 4
    # The two v4 concessions this fixture exists to keep exercised: untagged
    # positional loops, and null pcurves.
    assert all(isinstance(loop, list) for face in data["faces"] for loop in face["loops"])
    assert all(trim["curve_2d"] is None for face in data["faces"] for loop in face["loops"] for trim in loop)


@pytest.mark.occ
def test_occ_reads_the_legacy_v4_document():
    restored = Brep.__from_data__(_legacy_v4_box())
    assert len(restored.faces) == 6
    assert TOL.is_close(restored.volume, 1.0, atol=1e-6)


# =============================================================================
# 4. Regeneration: the fixtures still match live Rhino
# =============================================================================


@pytest.mark.rhino
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_rhino_regenerates_fixture_unchanged(name, request):
    """Rhino re-authors each fixture; drift from the committed file fails here.

    Pass --refresh-fixtures to rewrite them instead. See tests/exchange_fixtures.py.
    """
    regenerated = SOURCES[name]().__data__

    if request.config.getoption("--refresh-fixtures"):
        write_fixture(name, regenerated)
        pytest.skip(f"refreshed fixture {name!r} from live Rhino")

    difference = documents_differ(load_fixture(name), regenerated)
    assert difference is None, f"fixture {name!r} has drifted from live Rhino at {difference}"


# =============================================================================
# 5. The mirror: OCC-authored fixtures, read by Rhino
# =============================================================================

# The OCC -> Rhino direction needs a committed OCC-authored document for the same
# reason the other direction does: neither backend is importable in the same process
# as the other, so the Rhino-marked test that reads it cannot author it. This is the
# OCC-marked half -- it keeps that document honest on CI.


@pytest.mark.occ
@pytest.mark.parametrize("name", sorted(OCC_SOURCES))
def test_occ_regenerates_its_fixture_unchanged(name, request):
    regenerated = OCC_SOURCES[name]().__data__

    if request.config.getoption("--refresh-fixtures"):
        write_occ_fixture(name, regenerated)
        pytest.skip(f"refreshed OCC fixture {name!r}")

    difference = documents_differ(load_occ_fixture(name), regenerated)
    assert difference is None, f"OCC fixture {name!r} has drifted at {difference}"


# The analytic surface tag each OCC-authored mirror fixture must carry. If OCC ever
# stopped tagging one of these, the Rhino-marked reader that consumes it would be
# testing nothing -- and it runs nowhere CI can see it fail, so this OCC-marked guard
# is what keeps it honest.
_OCC_FIXTURE_TAGS = {
    "cylinder": {"plane", "cylinder"},
    "sphere": {"sphere"},
    "cone": {"plane", "cone"},
    "torus": {"torus"},
}


@pytest.mark.occ
@pytest.mark.parametrize("name", sorted(_OCC_FIXTURE_TAGS))
def test_occ_fixture_carries_its_analytic_tag(name):
    data = load_occ_fixture(name)

    assert data["version"] == EXCHANGE_VERSION
    assert _surface_tags(data) == _OCC_FIXTURE_TAGS[name]
