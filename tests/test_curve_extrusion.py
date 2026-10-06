"""Extruding curves as curves, and measuring what that makes.

Two failures, both silent: a NurbsCurve handed to ``from_extrusion`` extruded its
control polygon, and the volume of a prism swept from a B-spline came out percent
wrong, because ``BRepGProp`` mis-integrates surfaces of linear extrusion over one.
"""

import math

import pytest
from compas.geometry import Circle
from compas.geometry import Frame
from compas.geometry import Line
from compas.geometry import Point
from compas.geometry import Vector

from compas_brep import Brep
from compas_brep.curves import NurbsCurve

pytestmark = [pytest.mark.occ, pytest.mark.filterwarnings("ignore:cap_ends")]

DEPTH = 40.0


def _circle(radius=100.0):
    return NurbsCurve.from_circle(Circle(radius, Frame(Point(150, 150, 0), Vector(1, 0, 0), Vector(0, 1, 0))))


def _blob():
    """A closed, C1, non-rational cubic: one Bezier span per pair of eight points round a lumpy ellipse."""
    points = [(200 + 120 * math.cos(a) * (1 + 0.15 * math.sin(3 * a)), 150 + 80 * math.sin(a)) for a in (2 * math.pi * i / 8 for i in range(8))]
    n, control = len(points), []
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        m1 = ((p2[0] - p0[0]) / 2, (p2[1] - p0[1]) / 2)
        m2 = ((p3[0] - p1[0]) / 2, (p3[1] - p1[1]) / 2)
        control += [p1, (p1[0] + m1[0] / 3, p1[1] + m1[1] / 3), (p2[0] - m2[0] / 3, p2[1] - m2[1] / 3)]
    control.append(control[0])
    curve = NurbsCurve.from_parameters([Point(x, y, 0) for x, y in control], [1.0] * len(control), [float(k) for k in range(n + 1)], [4] + [3] * (n - 1) + [4], 3)
    return curve, control


def _bezier_area(control):
    """The area a closed chain of cubic Bezier spans encloses, sampled densely enough to be good to ~1e-8."""
    points = []
    for i in range(0, len(control) - 1, 3):
        b = control[i : i + 4]
        for k in range(4000):
            t = k / 4000
            w = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t**3)
            points.append((sum(wi * p[0] for wi, p in zip(w, b)), sum(wi * p[1] for wi, p in zip(w, b))))
    return abs(sum(points[i - 1][0] * points[i][1] - points[i][0] * points[i - 1][1] for i in range(len(points)))) / 2


def test_a_closed_rational_curve_extrudes_as_the_curve():
    prism = Brep.from_extrusion(_circle(), Vector(0, 0, -DEPTH))
    # the control polygon of this circle is a square: 4e4 * 40, not pi * 1e4 * 40
    assert prism.volume == pytest.approx(math.pi * 100.0**2 * DEPTH, rel=1e-7)
    assert prism.area == pytest.approx(2 * math.pi * 100.0**2 + 2 * math.pi * 100.0 * DEPTH, rel=1e-7)


def test_a_prism_of_a_cubic_measures_its_true_volume():
    curve, control = _blob()
    prism = Brep.from_extrusion(curve, Vector(0, 0, -DEPTH))
    assert prism.volume == pytest.approx(_bezier_area(control) * DEPTH, rel=1e-6)


def test_a_chain_of_curves_and_lines_extrudes_as_one_profile():
    # a half disc: two rational quarter arcs as one curve, closed by its diameter
    s = 2**-0.5
    arc = NurbsCurve.from_parameters(
        [Point(250, 150, 0), Point(250, 250, 0), Point(150, 250, 0), Point(50, 250, 0), Point(50, 150, 0)], [1, s, 1, s, 1], [0.0, 0.5, 1.0], [3, 2, 3], 2
    )
    prism = Brep.from_extrusion([arc, Line(Point(50, 150, 0), Point(250, 150, 0))], Vector(0, 0, -DEPTH))
    assert prism.volume == pytest.approx(math.pi * 100.0**2 / 2 * DEPTH, rel=1e-7)
    assert prism.centroid.z == pytest.approx(-DEPTH / 2)


def test_curves_that_do_not_join_are_refused():
    with pytest.raises(Exception):
        Brep.from_extrusion([Line(Point(0, 0, 0), Point(1, 0, 0)), Line(Point(2, 0, 0), Point(2, 1, 0))], Vector(0, 0, -1))


def test_the_bounding_box_is_the_curve_s_not_its_control_net_s():
    # a circle's control points form the square around it, padded by tolerances besides
    box = Brep.from_extrusion(_circle(), Vector(0, 0, -DEPTH)).aabb
    assert (box.xmin, box.ymin, box.zmin) == pytest.approx((50.0, 50.0, -DEPTH), abs=1e-6)
    assert (box.xmax, box.ymax, box.zmax) == pytest.approx((250.0, 250.0, 0.0), abs=1e-6)


def test_a_loft_through_many_differing_sections_can_cap_its_degree():
    # Eight crowned sections whose radius changes along the loft, like a compound fretboard radius.
    # At OCC's default degree the boolean below comes back empty; capped at three it does not.
    from compas.geometry import Box

    sections = []
    for i in range(8):
        x, radius, w = 60.0 * i, 254.0 + 20.0 * i, 31.0
        half = math.asin(w / radius)
        edge = -(radius - math.sqrt(radius * radius - w * w))
        apex = -radius + radius / math.cos(half)
        points = [(x, w, edge), (x, 0, apex), (x, -w, edge), (x, -w, -4.0), (x, -w, -8.0), (x, 0, -8.0), (x, w, -8.0), (x, w, -4.0), (x, w, edge)]
        weights = [1, math.cos(half), 1, 1, 1, 1, 1, 1, 1]
        sections.append(NurbsCurve.from_parameters([Point(*p) for p in points], weights, [0.0, 1.0, 2.0, 3.0, 4.0], [3, 2, 2, 2, 3], 2))
    zone = Brep.from_box(Box.from_corner_corner_height(Point(0, -w, -7.5), Point(420, w, -7.5), 8.5))
    loft = Brep.from_loft(sections, max_degree=3)
    inside = sum(piece.volume for piece in Brep.from_boolean_intersection(zone, loft))
    outside = sum(piece.volume for piece in Brep.from_boolean_difference(zone, loft))
    assert inside > 0.5 * zone.volume
    assert inside + outside == pytest.approx(zone.volume, rel=1e-6)
