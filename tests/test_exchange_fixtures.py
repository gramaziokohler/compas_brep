"""The committed Rhino-authored exchange documents, read back by OCC.

This is the half of the contract harness that runs on CI. Every test here that
rebuilds a fixture is a Rhino -> OCC exchange executed without a Rhino license:
the Rhino half already happened, on a dev machine, and was committed.

See tests/exchange_fixtures.py for the source geometry and the refresh path.
"""

from __future__ import annotations

import pytest
from compas.data import json_load
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
from exchange_fixtures import read_fixture_document
from exchange_fixtures import write_fixture
from exchange_fixtures import write_occ_fixture

from compas_brep import Brep
from compas_brep.exchange import EXCHANGE_VERSION
from compas_brep.exchange import SINGULAR_TRIM_EDGE

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
# ``volume_atol`` is the bar the OCC rebuild is held to. A planar box is exact.
# ``filleted_box`` carries approximation error at the scale of its NURBS fillet
# faces' own discretization, so it stays at 1e-3. The other curved fixtures were
# refreshed after slice 06 and now carry exact analytic seams (see below), so
# they're held to 1e-6 -- not `TOL.absolute` (1e-9) itself, because the `volume`
# values above are hand-typed to 6 decimals and the residual against the full-
# precision Rhino volume is on the order of 1e-7, from that rounding rather than
# from any imprecision in the rebuild.
#
# ``rebuild_invalid`` marks a fixture whose OCC rebuild still reports invalid -- see
# the xfail below. Not a property of the fixture: the same shape authored by OCC
# itself fails the same way.
EXPECTED = {
    "box": {
        "faces": 6,
        "surface_tags": {"plane"},
        "loop_roles": {"outer"},
        "volume": 1.0,
        "volume_atol": 1e-6,
        "rebuild_invalid": False,
    },
    "filleted_box": {
        "faces": 26,
        "surface_tags": {"plane", "nurbs"},
        "loop_roles": {"outer"},
        "volume": 7.563414,
        "volume_atol": 1e-3,
        "rebuild_invalid": True,
    },
    "sphere": {
        "faces": 1,
        "surface_tags": {"sphere"},
        "loop_roles": {"outer"},
        "volume": 4.18879,
        "volume_atol": 1e-6,
        "rebuild_invalid": False,
    },
    "box_with_hole": {
        "faces": 7,
        "surface_tags": {"plane", "cylinder"},
        "loop_roles": {"outer", "inner"},
        "volume": 7.434513,
        "volume_atol": 1e-6,
        "rebuild_invalid": False,
    },
    # The wall's surface is analytic and exact. Its seam / cap edges are now exact
    # circles too, refreshed from live Rhino via the LAMCP bridge (the reason this
    # was still 1e-3 was that slice 06 landed with no bridge and no license, so
    # these fixtures could not be regenerated — see git history for the pre-refresh
    # comment). The OCC-authored mirror fixtures carry the same exact seams — see
    # `test_occ_fixture_carries_exact_analytic_seams`.
    "cylinder": {
        "faces": 3,
        "surface_tags": {"plane", "cylinder"},
        "loop_roles": {"outer"},
        "volume": 1.570796,
        "volume_atol": 1e-6,
        "rebuild_invalid": False,
    },
    # The cone and torus join the cylinder with exact analytic seams, refreshed the
    # same way. A cone's caps make it a solid with a planar base (like the
    # cylinder); a torus has neither cap nor seam vertex.
    "cone": {
        "faces": 2,
        "surface_tags": {"plane", "cone"},
        "loop_roles": {"outer"},
        "volume": 0.261799,
        "volume_atol": 1e-6,
        "rebuild_invalid": False,
    },
    "torus": {
        "faces": 1,
        "surface_tags": {"torus"},
        "loop_roles": {"outer"},
        "volume": 1.776529,
        "volume_atol": 1e-6,
        "rebuild_invalid": False,
    },
}

FIXTURE_NAMES = sorted(EXPECTED)


def _surface_tags(data: dict) -> set:
    return {face["surface"]["type"] for face in data["faces"]}


def _loop_roles(data: dict) -> set:
    return {loop["type"] for face in data["faces"] for loop in face["loops"]}


def _trims(data: dict) -> list:
    return [trim for face in data["faces"] for loop in face["loops"] for trim in loop["trims"]]


def _rebuilt_once(brep: Brep) -> dict:
    """One backend rebuild pass, matching the rebuild load_fixture/load_occ_fixture

    already applied to the committed side (json_load decodes a fixture's dtype-tagged
    Brep through __from_data__). Without this, a drift check comparing a once-rebuilt
    committed document against a never-rebuilt fresh one would flag every rebuild-only
    quirk as if it were writer drift.
    """
    return Brep.__from_data__(brep.__data__).__data__


# =============================================================================
# 1. The committed files are well-formed v6 documents
# =============================================================================

# These read the file and never rebuild it. Written against
# `load_fixture(name).__data__` instead, they tested the reader's re-serialization:
# measured, a fixture regressed to v5 positional loops passed every one of them.
# Section 2 exercises the rebuild; this section exercises the wire format.
#
# Unmarked, because reading JSON needs no kernel.


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_file_is_current_version(name):
    assert read_fixture_document(name)["version"] == EXCHANGE_VERSION


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_file_every_face_has_exactly_one_outer_loop(name):
    for face in read_fixture_document(name)["faces"]:
        roles = [loop["type"] for loop in face["loops"]]
        assert set(roles) <= {"outer", "inner"}
        assert roles.count("outer") == 1


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_file_has_no_trim_with_a_null_pcurve(name):
    trims = _trims(read_fixture_document(name))
    assert len(trims) > 0
    assert all(trim["curve_2d"] is not None for trim in trims)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_file_every_singular_trim_carries_its_vertex(name):
    # With no edge, the vertex index is the only thing placing the trim in 3D.
    data = read_fixture_document(name)
    singular = [trim for trim in _trims(data) if trim["edge"] == SINGULAR_TRIM_EDGE]

    for trim in singular:
        assert "vertex" in trim
        assert 0 <= trim["vertex"] < len(data["vertices"])


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_file_says_what_it_is_expected_to_say(name):
    data = read_fixture_document(name)
    expected = EXPECTED[name]

    assert len(data["faces"]) == expected["faces"]
    assert _surface_tags(data) == expected["surface_tags"]
    assert _loop_roles(data) == expected["loop_roles"]


def test_fixture_file_box_with_hole_actually_has_an_inner_loop():
    # Guards the harness: without this, "inner loops survive" could pass on a
    # document that has none.
    data = read_fixture_document("box_with_hole")
    holed = [f for f in data["faces"] if any(loop["type"] == "inner" for loop in f["loops"])]
    assert len(holed) == 2


def test_fixture_file_sphere_spells_its_poles_as_singular_trims():
    # Guards the harness: the singular-trim read path below tests nothing if the
    # committed document stops using Rhino's spelling.
    trims = _trims(read_fixture_document("sphere"))
    assert len([t for t in trims if t["edge"] == SINGULAR_TRIM_EDGE]) == 2


# =============================================================================
# 2. OCC reads what Rhino wrote
# =============================================================================


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuilds_fixture_with_face_count_intact(name):
    restored = load_fixture(name)
    assert len(restored.faces) == EXPECTED[name]["faces"]


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuilds_fixture_with_volume_intact(name):
    # Was a strict xfail for the filleted box, blamed on face orientation. The cause
    # was the reader dropping Rhino's singular trims, leaving eight corner patches
    # unclosed and the volume 0.5 low.
    restored = load_fixture(name)
    assert TOL.is_close(restored.volume, EXPECTED[name]["volume"], atol=EXPECTED[name]["volume_atol"])


# The filleted box's eight corner patches come back BRepCheck_UnorientableShape: the
# volume integrates correctly over them, but OCC cannot settle which side each bounds.
# Not a cross-backend problem -- an OCC-authored filleted box round-trips the same way.
_REBUILD_INVALID_XFAIL = "OCC cannot orient the rebuilt corner patches; see the note above."


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuilds_fixture_as_a_valid_shape(name, request):
    # A sphere with its poles dropped still reported the right volume and area --
    # integration over the open patch converges -- and passed every other test here.
    # strict=True, so whoever fixes the corner patches is told to un-xfail it.
    if EXPECTED[name]["rebuild_invalid"]:
        request.node.add_marker(pytest.mark.xfail(strict=True, reason=_REBUILD_INVALID_XFAIL))

    assert load_fixture(name).is_valid


@pytest.mark.occ
@pytest.mark.parametrize("name", ["sphere", "cone"])
def test_occ_reads_rhinos_singular_trims_as_degenerate_edges(name):
    # Asserts the translation happened, not just that the result is valid: skipping
    # a singular trim leaves the wire open, which only `is_valid` above notices.
    committed = read_fixture_document(name)
    singular = [t for t in _trims(committed) if t["edge"] == SINGULAR_TRIM_EDGE]
    assert len(singular) > 0

    restored = load_fixture(name)
    collapsed = [e for e in restored.edges if e.length < 1e-9]
    assert len(collapsed) == len(singular)


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuild_preserves_surface_tags(name):
    # Re-serialize through OCC: a tag Rhino wrote that OCC cannot read would be
    # dropped or downgraded here rather than surviving the round-trip.
    reserialized = load_fixture(name).__data__
    assert _surface_tags(reserialized) == EXPECTED[name]["surface_tags"]


@pytest.mark.occ
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_occ_rebuild_preserves_loop_roles(name):
    reserialized = load_fixture(name).__data__
    assert _loop_roles(reserialized) == EXPECTED[name]["loop_roles"]


@pytest.mark.occ
def test_occ_rebuild_keeps_the_hole_a_hole():
    # The hole subtracts its area rather than adding it — the defect slice 02 found,
    # here crossing from Rhino rather than round-tripping within OCC.
    restored = load_fixture("box_with_hole")
    assert TOL.is_close(restored.volume, EXPECTED["box_with_hole"]["volume"], atol=1e-3)


@pytest.mark.occ
def test_occ_rebuild_of_the_hole_is_valid():
    # Was a strict xfail from slice 02 through 06: a rebuilt cylinder wall lost its
    # seam edge and reported invalid. Fixed by issue 08's shared vertex/edge table
    # in brep_to_occ -- the seam is now one shared TopoDS_Edge with both its pcurve
    # representations attached, not two independently built edges left for
    # BRepBuilderAPI_Sewing to merge by tolerance.
    assert load_fixture("box_with_hole").is_valid


@pytest.mark.occ
@pytest.mark.parametrize("name", ["cylinder", "box_with_hole"])
def test_occ_reads_a_rhino_authored_cylinder_as_an_analytic_cylinder(name):
    # The slice-04 tracer, running on CI without a Rhino license: Rhino authored a
    # cylinder wall and tagged it analytically, and OCC must rebuild it as a real
    # CylindricalSurface rather than a NURBS approximation of one. Asserting the
    # rebuilt type -- not a volume -- is the representational-fidelity bar.
    restored = load_fixture(name)

    walls = [face for face in restored.faces if face.is_cylinder]
    assert len(walls) == 1
    assert isinstance(walls[0].surface, CylindricalSurface)
    assert walls[0].surface_type == "cylinder"


@pytest.mark.occ
def test_occ_reads_the_rhino_cylinder_radius_and_axis():
    # Guards the tag against being right in name only: a CylindricalSurface with the
    # wrong radius or axis would still satisfy the type assertion above.
    wall = next(f for f in load_fixture("cylinder").faces if f.is_cylinder)

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
    restored = load_fixture(name)

    faces = [f for f in restored.faces if getattr(f, predicate)]
    assert len(faces) == 1
    assert isinstance(faces[0].surface, surface_type)


@pytest.mark.occ
def test_occ_reads_the_rhino_cone_radius_and_height():
    # The convention the two kernels disagree on, pinned by value rather than volume.
    cone = next(f for f in load_fixture("cone").faces if f.is_cone)

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
    return json_load(FIXTURE_DIR / "legacy_v4_box.json")


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
    regenerated = SOURCES[name]()

    if request.config.getoption("--refresh-fixtures"):
        write_fixture(name, regenerated)
        pytest.skip(f"refreshed fixture {name!r} from live Rhino")

    difference = documents_differ(load_fixture(name).__data__, _rebuilt_once(regenerated))
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
    regenerated = OCC_SOURCES[name]()

    if request.config.getoption("--refresh-fixtures"):
        write_occ_fixture(name, regenerated)
        pytest.skip(f"refreshed OCC fixture {name!r}")

    difference = documents_differ(load_occ_fixture(name).__data__, _rebuilt_once(regenerated))
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
    data = load_occ_fixture(name).__data__

    assert data["version"] == EXCHANGE_VERSION
    assert _surface_tags(data) == _OCC_FIXTURE_TAGS[name]


# The analytic *edge* tag each mirror fixture must carry, as of slice 06. A cylinder
# and a cone carry full circular cap edges; a sphere's meridian is a half turn, so it
# is an arc. These are the committed documents with exact circular seams that the
# Rhino-marked reader consumes, and this is the CI-side guard on them: if OCC ever
# reverted to writing a seam as a NURBS approximation, the reader on the other side
# would quietly go back to testing nothing.
_OCC_FIXTURE_EDGE_TAGS = {
    "cylinder": {"line", "circle"},
    "sphere": {"line", "arc"},
    "cone": {"line", "circle"},
    "torus": {"circle"},
}


@pytest.mark.occ
@pytest.mark.parametrize("name", sorted(_OCC_FIXTURE_EDGE_TAGS))
def test_occ_fixture_carries_exact_analytic_seams(name):
    data = load_occ_fixture(name).__data__
    tags = {edge["curve"]["type"] for edge in data["edges"]}

    assert tags == _OCC_FIXTURE_EDGE_TAGS[name]
    assert "nurbs" not in tags, f"the {name!r} fixture still carries an approximated seam"
