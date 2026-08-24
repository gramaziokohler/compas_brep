"""Analytic edge curve tags: `circle`, `arc`, `ellipse`.

An exact cylinder used to cross the wire carrying NURBS approximations of its own
seams. That mismatch is not cosmetic: OCC writes a circle as a degree-11 polynomial
approximation whose parameter is not its angle, while the wall's pcurves run
linearly in angle, so pcurve and edge curve traced the same circle at different
rates and the rebuilt wall came back slightly wrong.

The tests here hold the line at the *type* level wherever they can. A tolerance on
sampled points is not enough — a NURBS approximation of a circle passes that, which
is exactly how this defect survived several releases. Asking the kernel "is this
edge a circle?" is a question an approximation cannot answer yes to.
"""

from __future__ import annotations

import json
import math

import pytest
from compas.geometry import Box
from compas.geometry import Circle
from compas.geometry import Cylinder
from compas.geometry import Ellipse
from compas.geometry import Frame
from compas.geometry import Line
from compas.geometry import Point
from compas.geometry import Rotation
from compas.geometry import Sphere
from compas.geometry import Vector
from compas.tolerance import TOL

from compas_brep import Brep
from compas_brep.curves import NurbsCurve
from compas_brep.curves import edge_curve_from_data
from compas_brep.curves import edge_curve_to_data
from compas_brep.edge import BrepEdge
from compas_brep.errors import BrepError
from compas_brep.surfaces import NurbsSurface
from compas_brep.vertex import BrepVertex

TILTED = Frame(Point(1.0, -2.0, 0.5), Vector(0.6, 0.8, 0.0), Vector(-0.8, 0.6, 0.0))


def _edge_tags(data: dict) -> list[str]:
    return [edge["curve"]["type"] for edge in data["edges"]]


def _roundtrip(brep: Brep) -> Brep:
    return Brep.__from_data__(json.loads(json.dumps(brep.__data__)))


def _native_curve_types(brep: Brep) -> list[str]:
    """What OCC says each edge of a native shape *is*, by adaptor type."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle
    from OCP.GeomAbs import GeomAbs_Ellipse
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    names = {GeomAbs_Line: "line", GeomAbs_Circle: "circle", GeomAbs_Ellipse: "ellipse"}

    types = []
    seen = []
    explorer = TopExp_Explorer(brep._native_brep, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        if not any(edge.IsSame(other) for other in seen):
            seen.append(edge)
            types.append(names.get(BRepAdaptor_Curve(edge).GetType(), "other"))
        explorer.Next()
    return types


# =============================================================================
# 1. The codec
# =============================================================================


def test_codec_roundtrips_a_circle_with_its_domain():
    circle = Circle(0.7, frame=TILTED)
    data = edge_curve_to_data(circle, (0.0, 2 * math.pi))

    assert data["type"] == "circle"
    curve, domain = edge_curve_from_data(data)

    assert isinstance(curve, Circle)
    assert TOL.is_close(curve.radius, 0.7)
    assert TOL.is_allclose(curve.frame.point, circle.frame.point)
    assert TOL.is_allclose(domain, (0.0, 2 * math.pi))


def test_codec_tags_a_partial_circle_as_an_arc():
    data = edge_curve_to_data(Circle(0.7, frame=TILTED), (0.0, math.pi / 2))

    assert data["type"] == "arc"
    curve, domain = edge_curve_from_data(data)

    # An arc is a circle plus an interval -- the interval is what makes it partial.
    assert isinstance(curve, Circle)
    assert TOL.is_allclose(domain, (0.0, math.pi / 2))


def test_codec_carries_an_interval_that_compas_arc_could_not_hold():
    # The interval OCC actually hands out for a sphere's meridian. COMPAS `Arc`
    # requires 0 <= angle <= 2*pi and would reject this, which is why the format
    # carries the domain beside the conic rather than inside it.
    domain = (1.5 * math.pi, 2.5 * math.pi)
    _, decoded = edge_curve_from_data(edge_curve_to_data(Circle(1.0, frame=TILTED), domain))

    assert TOL.is_allclose(decoded, domain)


def test_codec_roundtrips_an_ellipse():
    data = edge_curve_to_data(Ellipse(2.0, 1.1, frame=TILTED), (0.0, 2 * math.pi))

    assert data["type"] == "ellipse"
    curve, _ = edge_curve_from_data(data)

    assert isinstance(curve, Ellipse)
    assert TOL.is_close(curve.major, 2.0)
    assert TOL.is_close(curve.minor, 1.1)


def test_codec_still_reads_the_line_payloads_both_writers_have_used():
    as_list, _ = edge_curve_from_data({"type": "line", "data": [[0, 0, 0], [1, 2, 3]]})
    as_mapping, _ = edge_curve_from_data({"type": "line", "data": {"start": [0, 0, 0], "end": [1, 2, 3]}})

    assert isinstance(as_list, Line)
    assert TOL.is_allclose(as_list.end, [1, 2, 3])
    assert TOL.is_allclose(as_mapping.end, [1, 2, 3])


def test_codec_rejects_an_unknown_tag():
    with pytest.raises(ValueError):
        edge_curve_from_data({"type": "hyperbola", "data": {}})


# =============================================================================
# 2. The loss policy
# =============================================================================


def test_an_analytic_curve_without_its_domain_raises():
    # Not a nicety: a conic with no interval is a closed curve, which is not what
    # the edge runs along. Writing one would be the silent degradation ADR-0001
    # forbids, so it raises instead of defaulting to a full turn.
    with pytest.raises(BrepError):
        edge_curve_to_data(Circle(1.0, frame=TILTED))


def test_an_unrepresentable_edge_curve_raises():
    class Hyperbola:
        pass

    with pytest.raises(BrepError):
        edge_curve_to_data(Hyperbola(), (0.0, 1.0))


# =============================================================================
# 3. BrepEdge reports what it is
# =============================================================================


def _edge(curve, domain=None):
    return BrepEdge(BrepVertex(Point(0, 0, 0)), BrepVertex(Point(1, 0, 0)), curve=curve, domain=domain)


def test_edge_predicates_separate_a_circle_from_an_arc():
    full = _edge(Circle(1.0, frame=TILTED), (0.0, 2 * math.pi))
    partial = _edge(Circle(1.0, frame=TILTED), (0.0, math.pi / 2))

    assert full.is_circle and not full.is_arc
    assert partial.is_arc and not partial.is_circle
    assert full.curve_type == "circle"
    assert partial.curve_type == "arc"


def test_edge_predicates_hold_for_an_ellipse_and_a_line():
    assert _edge(Ellipse(2.0, 1.0, frame=TILTED), (0.0, 2 * math.pi)).is_ellipse
    assert _edge(Line(Point(0, 0, 0), Point(1, 0, 0))).is_line


def test_edge_length_is_the_arc_it_covers_not_the_whole_conic():
    quarter = _edge(Circle(2.0, frame=TILTED), (0.0, math.pi / 2))

    assert TOL.is_close(quarter.length, 2.0 * math.pi / 2)


def test_edge_length_of_an_ellipse_is_not_proportional_to_its_parameter_span():
    # An ellipse's arc length is an elliptic integral, and treating it as
    # proportional to the parameter span is the plausible wrong answer.
    #
    # The span has to be asymmetric to show it: [0, pi/2] is exactly one quadrant,
    # and by symmetry that IS a quarter of the perimeter, so the obvious test
    # passes against the wrong implementation. [0, pi/4] is not a fixed fraction of
    # anything -- it runs along the flat end of the ellipse, where the curve covers
    # more distance per radian than average.
    ellipse = Ellipse(3.0, 1.0, frame=Frame.worldXY())
    eighth = _edge(ellipse, (0.0, math.pi / 4))
    full = _edge(ellipse, (0.0, 2 * math.pi))

    assert not TOL.is_close(eighth.length, full.length / 8, atol=1e-3)


# =============================================================================
# 4. OCC writes the tags, and reads them back as native conics
# =============================================================================


@pytest.mark.occ
def test_occ_writes_a_cylinders_seams_as_circles():
    data = Brep.from_cylinder(Cylinder(0.5, 2.0)).__data__

    assert sorted(set(_edge_tags(data))) == ["circle", "line"]
    assert _edge_tags(data).count("circle") == 2


@pytest.mark.occ
def test_occ_writes_a_spheres_meridian_as_an_arc():
    # A sphere's seam is a half turn, so it is an arc rather than a circle -- and
    # its interval is one COMPAS `Arc` could not hold. See the codec test above.
    data = Brep.from_sphere(Sphere(1.0)).__data__

    assert "arc" in _edge_tags(data)


@pytest.mark.occ
def test_occ_writes_a_tilted_cut_as_an_ellipse():
    cutter = Brep.from_box(Box(3.0, 3.0, 3.0))
    cutter.transform(Rotation.from_axis_and_angle([1, 0, 0], 0.6))
    cutter.translate([0, 0, -2.0])

    data = (Brep.from_cylinder(Cylinder(0.5, 3.0)) - cutter).__data__

    assert "ellipse" in _edge_tags(data)


@pytest.mark.occ
def test_occ_leaves_a_freeform_edge_as_nurbs():
    # The tags are not applied indiscriminately -- a curve that is not a conic must
    # stay `nurbs`.
    #
    # A filleted box is NOT the shape to check this with, though it looks like it:
    # measured, every one of its blend edges is a circular arc or a line, and it
    # contains no `nurbs` edge at all. A freeform patch's boundary is the honest
    # source of one.
    points = [
        [Point(0, 0, 0), Point(1, 0, 0.4), Point(2, 0, 0)],
        [Point(0, 1, 0.3), Point(1, 1, 1.0), Point(2, 1, 0.2)],
        [Point(0, 2, 0), Point(1, 2, 0.5), Point(2, 2, 0)],
    ]
    data = Brep.from_surface(NurbsSurface.from_points(points)).__data__

    assert "nurbs" in _edge_tags(data)


@pytest.mark.occ
def test_a_filleted_boxs_blend_edges_are_arcs_not_freeform():
    # Recorded because it is counterintuitive and it drove the choice above: the
    # `arc` tag's best source in this suite is a fillet.
    data = Brep.from_box(Box(2.0, 2.0, 2.0)).filleted(0.3).__data__

    assert set(_edge_tags(data)) == {"line", "arc"}


@pytest.mark.occ
def test_a_cylinders_seams_arrive_as_native_circles_not_approximations():
    # THE criterion of this slice. Asking OCC's adaptor for the edge type is a
    # question a NURBS approximation cannot pass, unlike a tolerance on sampled
    # points -- which is how the approximated seams went unnoticed for so long.
    restored = _roundtrip(Brep.from_cylinder(Cylinder(0.5, 2.0)))

    assert sorted(_native_curve_types(restored)) == ["circle", "circle", "line"]


@pytest.mark.occ
def test_a_rebuilt_circular_seam_matches_the_analytic_circle_exactly():
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    restored = _roundtrip(Brep.from_cylinder(Cylinder(0.5, 2.0)))

    radii = []
    explorer = TopExp_Explorer(restored._native_brep, TopAbs_EDGE)
    while explorer.More():
        adaptor = BRepAdaptor_Curve(TopoDS.Edge_s(explorer.Current()))
        if adaptor.GetType() == GeomAbs_Circle:
            circle = adaptor.Circle()
            radii.append(circle.Radius())
            # The interval is the conic's own, not a refit's: a full turn.
            assert TOL.is_close(adaptor.LastParameter() - adaptor.FirstParameter(), 2 * math.pi)
        explorer.Next()

    assert radii, "the rebuilt cylinder has no circular edge at all"
    for radius in radii:
        assert TOL.is_close(radius, 0.5)


@pytest.mark.occ
def test_an_ellipse_survives_the_rebuild_as_a_native_ellipse():
    cutter = Brep.from_box(Box(3.0, 3.0, 3.0))
    cutter.transform(Rotation.from_axis_and_angle([1, 0, 0], 0.6))
    cutter.translate([0, 0, -2.0])

    restored = _roundtrip(Brep.from_cylinder(Cylinder(0.5, 3.0)) - cutter)

    assert "ellipse" in _native_curve_types(restored)


# =============================================================================
# 5. What the exactness buys
# =============================================================================


@pytest.mark.occ
@pytest.mark.parametrize(
    "name,brep,volume",
    [
        ("cylinder", lambda: Brep.from_cylinder(Cylinder(0.5, 2.0)), math.pi * 0.25 * 2.0),
        ("sphere", lambda: Brep.from_sphere(Sphere(1.0)), 4 / 3 * math.pi),
    ],
)
def test_an_analytic_round_trip_preserves_volume_to_tolerance(name, brep, volume):
    # Before analytic edge tags the cylinder came back 1.2e-07 out, because its
    # NURBS seams and its exact wall disagreed. It is now exact to TOL.
    assert TOL.is_close(_roundtrip(brep()).volume, volume)


@pytest.mark.occ
def test_a_circle_costs_a_fraction_of_the_json_a_nurbs_circle_did():
    # Not a performance test -- a check that the writer really stopped emitting the
    # degree-11 approximation. A NURBS circle carries 12 control points and knots.
    data = Brep.from_cylinder(Cylinder(0.5, 2.0)).__data__
    circles = [edge["curve"] for edge in data["edges"] if edge["curve"]["type"] == "circle"]

    assert circles
    for circle in circles:
        assert set(circle["data"]) == {"curve", "domain"}
        assert set(circle["data"]["curve"]) == {"radius", "frame"}


# =============================================================================
# 6. The nurbs path still works
# =============================================================================


@pytest.mark.occ
def test_a_nurbs_edge_still_roundtrips():
    restored = _roundtrip(Brep.from_box(Box(2.0, 2.0, 2.0)).filleted(0.3))

    assert len(restored.faces) == 26


def test_codec_roundtrips_a_nurbs_curve():
    curve = NurbsCurve.from_parameters(
        points=[Point(0, 0, 0), Point(1, 1, 0), Point(2, 0, 0)],
        weights=[1.0, 1.0, 1.0],
        knots=[0.0, 1.0],
        mults=[3, 3],
        degree=2,
    )
    decoded, domain = edge_curve_from_data(edge_curve_to_data(curve))

    assert isinstance(decoded, NurbsCurve)
    assert domain is None
