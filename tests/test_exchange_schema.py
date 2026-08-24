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
from compas_brep.curves import EDGE_CURVE_TAGS
from compas_brep.surfaces import SURFACE_TAGS
from compas_brep.surfaces import NurbsSurface

# =============================================================================
# The format's tag set
# =============================================================================

# The tag sets come from the codecs rather than being restated here, so that a tag
# added to one is a test that fails for want of a source rather than a tag nobody
# checks. `test_every_tag_has_a_source` below is what enforces that.

# Surface tags the Rhino writer cannot produce yet — it emits `nurbs` instead.
# Empty: `cylinder` came out in slice 04, and `cone`/`sphere`/`torus` in slice 05,
# so the Rhino writer now emits every analytic surface tag in the format.
RHINO_UNWRITABLE_SURFACE_TAGS: set[str] = set()

# Edge curve tags a writer cannot produce yet.
#
# Empty on the OCC side: `circle`, `arc`, and `ellipse` join `line` and `nurbs`,
# which is what CONTEXT.md's v6 section has claimed all along.
#
# `ellipse` is a real, measured Rhino gap, found on the first licensed run (the set
# was empty until then, deliberately, so this would show up rather than hide):
# every elliptical edge compas_brep can currently construct in Rhino comes from a
# numeric op (`trimmed`, or a boolean like the one below) — there is no analytic
# construction path in the current API, the way `from_sphere`'s meridian gives a
# genuine `Rhino.Geometry.ArcCurve` for `arc`. A boolean/trim intersection curve is
# a generic `NurbsCurve`, and `TryGetEllipse` does not recognize it even at
# `TOL.absolute` — Rhino's own boolean/trim tolerance is looser than that. Writing
# `nurbs` instead is the writer's designed fallback, not a defect in it.
OCC_UNWRITABLE_EDGE_CURVE_TAGS: set[str] = set()
RHINO_UNWRITABLE_EDGE_CURVE_TAGS: set[str] = {"ellipse"}


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
    # A sphere's meridian: a circle with a bounded parameter range. NOT a fillet
    # corner, despite also being geometrically a quarter/half circle — measured on
    # Rhino, a fillet's blend edge is a rational NURBS whose native parameter is not
    # affine in angle (deviates up to 5e-3 from the assumed linear map at r=0.3), so
    # it correctly falls back to `nurbs` rather than mis-tagging. A sphere's
    # meridian is a genuine `Rhino.Geometry.ArcCurve` and passes the affine check.
    "arc": lambda: Brep.from_sphere(Sphere(1.0)),
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
@pytest.mark.parametrize("tag", sorted(SURFACE_TAGS))
def test_occ_roundtrips_surface_tag(tag):
    written, rewritten = _roundtrip(SURFACE_TAG_SOURCES[tag]())

    assert tag in _surface_tags(written), f"the OCC writer does not emit the {tag!r} surface tag"
    assert tag in _surface_tags(rewritten), f"the {tag!r} surface tag does not survive an OCC rebuild"


@pytest.mark.occ
@pytest.mark.parametrize("tag", sorted(EDGE_CURVE_TAGS))
def test_occ_roundtrips_edge_curve_tag(tag, request):
    _expect_xfail(request, OCC_UNWRITABLE_EDGE_CURVE_TAGS, tag, f"the OCC writer emits 'nurbs' for a {tag!r} edge")

    written, rewritten = _roundtrip(EDGE_CURVE_TAG_SOURCES[tag]())

    assert tag in _edge_curve_tags(written), f"the OCC writer does not emit the {tag!r} edge curve tag"
    assert tag in _edge_curve_tags(rewritten), f"the {tag!r} edge curve tag does not survive an OCC rebuild"


# =============================================================================
# 2. Rhino writes and reads every tag
# =============================================================================


@pytest.mark.rhino
@pytest.mark.parametrize("tag", sorted(SURFACE_TAGS))
def test_rhino_roundtrips_surface_tag(tag, request):
    _expect_xfail(request, RHINO_UNWRITABLE_SURFACE_TAGS, tag, f"the Rhino writer emits 'nurbs' for a {tag!r} face; slices 04 and 05 close this")

    written, rewritten = _roundtrip(SURFACE_TAG_SOURCES[tag]())

    assert tag in _surface_tags(written), f"the Rhino writer does not emit the {tag!r} surface tag"
    assert tag in _surface_tags(rewritten), f"the {tag!r} surface tag does not survive a Rhino rebuild"


@pytest.mark.rhino
@pytest.mark.parametrize("tag", sorted(EDGE_CURVE_TAGS))
def test_rhino_roundtrips_edge_curve_tag(tag, request):
    _expect_xfail(request, RHINO_UNWRITABLE_EDGE_CURVE_TAGS, tag, f"the Rhino writer emits 'nurbs' for a {tag!r} edge")

    written, rewritten = _roundtrip(EDGE_CURVE_TAG_SOURCES[tag]())

    assert tag in _edge_curve_tags(written), f"the Rhino writer does not emit the {tag!r} edge curve tag"
    assert tag in _edge_curve_tags(rewritten), f"the {tag!r} edge curve tag does not survive a Rhino rebuild"


# =============================================================================
# 3. Every tag the codecs define is exercised above
# =============================================================================


def test_every_tag_has_a_source():
    # The parametrized tests iterate the codecs' own tag sets, so a tag with no
    # geometry to produce it would be a KeyError at collection. This says so plainly.
    assert set(SURFACE_TAG_SOURCES) == set(SURFACE_TAGS)
    assert set(EDGE_CURVE_TAG_SOURCES) == set(EDGE_CURVE_TAGS)


# =============================================================================
# 4. The readers reject a tag that is not in the set
# =============================================================================


@pytest.mark.occ
def test_occ_reader_rejects_an_unknown_surface_tag():
    data = Brep.from_box(Box(1.0, 1.0, 1.0)).__data__
    data["faces"][0]["surface"]["type"] = "hyperboloid"

    with pytest.raises(ValueError):
        Brep.__from_data__(data)
