"""The exchange format's tag set, and both backends' obligation to it.

The tag set here is the **format's**, not any one backend's. A tag a backend cannot
yet write is present and marked xfail rather than omitted: the gap belongs in the
test suite, where it is checked on every run, rather than in a document nobody runs.

This is the test that would have caught the dropped-cylinder bug on day one — Rhino
emitting `plane`/`nurbs` only, and understanding nothing else on rebuild, while OCC
wrote analytic tags it could not read back.
"""

from __future__ import annotations

import json

import pytest
from compas.geometry import Box
from compas.geometry import Cone
from compas.geometry import Cylinder
from compas.geometry import Point
from compas.geometry import Rotation
from compas.geometry import Sphere
from compas.geometry import Torus

from compas_brep import Brep
from compas_brep.surfaces import NurbsSurface

# =============================================================================
# The format's tag set
# =============================================================================

SURFACE_TAGS = ["plane", "nurbs", "cylinder", "cone", "sphere", "torus"]

EDGE_CURVE_TAGS = ["line", "nurbs", "circle", "arc", "ellipse"]

# Surface tags the Rhino writer cannot produce yet — it emits `nurbs` instead.
# Empty: `cylinder` came out in slice 04, and `cone`/`sphere`/`torus` in slice 05,
# so the Rhino writer now emits every analytic surface tag in the format.
RHINO_UNWRITABLE_SURFACE_TAGS: set[str] = set()

# Edge curve tags a writer cannot produce yet.
#
# Empty on both sides as of slice 06: `circle`, `arc`, and `ellipse` join `line` and
# `nurbs`, which is what CONTEXT.md's v6 section has claimed all along.
#
# The Rhino set is empty because the format requires those tags, NOT because a live
# Rhino was watched writing them — slice 06 was implemented with no bridge and no
# license available, so `pytest -m rhino` has never run against this code. An empty
# set here means a Rhino gap shows up as a failure on the first licensed run, which
# is the outcome this suite wants; a speculative xfail would hide it instead.
OCC_UNWRITABLE_EDGE_CURVE_TAGS: set[str] = set()
RHINO_UNWRITABLE_EDGE_CURVE_TAGS: set[str] = set()


# =============================================================================
# Geometry that contains each tag
# =============================================================================


def _nurbs_patch() -> Brep:
    points = [
        [Point(0, 0, 0), Point(1, 0, 0.4), Point(2, 0, 0)],
        [Point(0, 1, 0.3), Point(1, 1, 1.0), Point(2, 1, 0.2)],
        [Point(0, 2, 0), Point(1, 2, 0.5), Point(2, 2, 0)],
    ]
    return Brep.from_surface(NurbsSurface.from_points(points))


def _cylinder_cut_by_a_tilted_box() -> Brep:
    # A cylinder sliced at an angle: the cut edge is a true ellipse, verified
    # against the OCC adaptor (6 GeomAbs_Ellipse edges) rather than assumed.
    cutter = Brep.from_box(Box(3.0, 3.0, 3.0))
    cutter.transform(Rotation.from_axis_and_angle([1, 0, 0], 0.6))
    cutter.translate([0, 0, -2.0])
    return Brep.from_cylinder(Cylinder(0.5, 3.0)) - cutter


SURFACE_TAG_SOURCES = {
    "plane": lambda: Brep.from_box(Box(1.0, 1.0, 1.0)),
    "nurbs": _nurbs_patch,
    "cylinder": lambda: Brep.from_cylinder(Cylinder(0.5, 2.0)),
    "cone": lambda: Brep.from_cone(Cone(0.5, 1.0)),
    "sphere": lambda: Brep.from_sphere(Sphere(1.0)),
    "torus": lambda: Brep.from_torus(Torus(1.0, 0.3)),
}

EDGE_CURVE_TAG_SOURCES = {
    "line": lambda: Brep.from_box(Box(1.0, 1.0, 1.0)),
    "nurbs": _nurbs_patch,
    # A full circular seam / cap edge.
    "circle": lambda: Brep.from_cylinder(Cylinder(0.5, 2.0)),
    # A fillet corner is a quarter circle: a circle with a bounded parameter range.
    "arc": lambda: Brep.from_box(Box(2.0, 2.0, 2.0)).filleted(0.3),
    "ellipse": _cylinder_cut_by_a_tilted_box,
}


def _surface_tags(data: dict) -> set:
    return {face["surface"]["type"] for face in data["faces"]}


def _edge_curve_tags(data: dict) -> set:
    return {edge["curve"]["type"] for edge in data["edges"]}


def _roundtrip(brep: Brep) -> tuple[dict, dict]:
    """Return ``(written, rewritten)`` — the document, and the document after a rebuild."""
    written = json.loads(json.dumps(brep.__data__))
    return written, Brep.__from_data__(written).__data__


def _expect_xfail(request, unwritable: set, tag: str, reason: str) -> None:
    if tag in unwritable:
        request.node.add_marker(pytest.mark.xfail(strict=True, reason=reason))


# =============================================================================
# 1. OCC writes and reads every tag
# =============================================================================


@pytest.mark.occ
@pytest.mark.parametrize("tag", SURFACE_TAGS)
def test_occ_roundtrips_surface_tag(tag):
    written, rewritten = _roundtrip(SURFACE_TAG_SOURCES[tag]())

    assert tag in _surface_tags(written), f"the OCC writer does not emit the {tag!r} surface tag"
    assert tag in _surface_tags(rewritten), f"the {tag!r} surface tag does not survive an OCC rebuild"


@pytest.mark.occ
@pytest.mark.parametrize("tag", EDGE_CURVE_TAGS)
def test_occ_roundtrips_edge_curve_tag(tag, request):
    _expect_xfail(request, OCC_UNWRITABLE_EDGE_CURVE_TAGS, tag, f"the OCC writer emits 'nurbs' for a {tag!r} edge")

    written, rewritten = _roundtrip(EDGE_CURVE_TAG_SOURCES[tag]())

    assert tag in _edge_curve_tags(written), f"the OCC writer does not emit the {tag!r} edge curve tag"
    assert tag in _edge_curve_tags(rewritten), f"the {tag!r} edge curve tag does not survive an OCC rebuild"


# =============================================================================
# 2. Rhino writes and reads every tag
# =============================================================================


@pytest.mark.rhino
@pytest.mark.parametrize("tag", SURFACE_TAGS)
def test_rhino_roundtrips_surface_tag(tag, request):
    _expect_xfail(request, RHINO_UNWRITABLE_SURFACE_TAGS, tag, f"the Rhino writer emits 'nurbs' for a {tag!r} face; slices 04 and 05 close this")

    written, rewritten = _roundtrip(SURFACE_TAG_SOURCES[tag]())

    assert tag in _surface_tags(written), f"the Rhino writer does not emit the {tag!r} surface tag"
    assert tag in _surface_tags(rewritten), f"the {tag!r} surface tag does not survive a Rhino rebuild"


@pytest.mark.rhino
@pytest.mark.parametrize("tag", EDGE_CURVE_TAGS)
def test_rhino_roundtrips_edge_curve_tag(tag, request):
    _expect_xfail(request, RHINO_UNWRITABLE_EDGE_CURVE_TAGS, tag, f"the Rhino writer emits 'nurbs' for a {tag!r} edge")

    written, rewritten = _roundtrip(EDGE_CURVE_TAG_SOURCES[tag]())

    assert tag in _edge_curve_tags(written), f"the Rhino writer does not emit the {tag!r} edge curve tag"
    assert tag in _edge_curve_tags(rewritten), f"the {tag!r} edge curve tag does not survive a Rhino rebuild"


# =============================================================================
# 3. The readers reject a tag that is not in the set
# =============================================================================


@pytest.mark.occ
def test_occ_reader_rejects_an_unknown_surface_tag():
    data = Brep.from_box(Box(1.0, 1.0, 1.0)).__data__
    data["faces"][0]["surface"]["type"] = "hyperboloid"

    with pytest.raises(ValueError):
        Brep.__from_data__(data)
