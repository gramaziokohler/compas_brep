"""Faces a boolean leaves REVERSED, and the seams that run through them.

Both bugs here were invisible to volume and area, and to every fixture in the
suite, because the suite's shapes are built by primitives and unions -- neither
of which leaves a *pcurve-built* face carrying ``is_reversed``. It takes a
subtraction: the tool's wall survives into the result inside-out, and it is
rebuilt from its pcurves rather than from 3D wires the way a plane is.

1. **Orientation applied twice.** The OCC writer explored each face's wires
   through the face itself, so a REVERSED face composed its flag into every trim
   it recorded -- and the reader applied ``is_reversed`` again when it reversed
   the rebuilt face. The wire came back running backwards: a blind hole
   round-tripped into a *bump* (1000 - 18.1 became 1000 + 18.1), which volume
   alone reports as a perfectly plausible number.

2. **A line's pcurve left behind.** A ``line`` edge carries only its endpoints,
   so the reader rebuilds it over ``[0, length]`` -- while OCC hands a boolean's
   cylinder seam back on, say, ``[5, 15]``, and the writer wrote the pcurve over
   that. The seam's pcurve then sat ``t0`` away from its own edge, breaking the
   wire of every full-turn cylindrical face that survived a boolean.

Both are caught only by ``is_valid``, which is why it is asserted here alongside
the volume -- see the same warning in CONTEXT.md about collapsed boundaries.
"""

from __future__ import annotations

import math

import compas
import pytest
from compas.geometry import Box
from compas.geometry import Circle
from compas.geometry import Cone
from compas.geometry import Cylinder
from compas.geometry import Ellipse
from compas.geometry import Frame
from compas.geometry import Point
from compas.geometry import Rotation
from compas.geometry import Sphere
from compas.geometry import Vector

from compas_brep import Brep
from compas_brep.errors import BrepInvalidError
from compas_brep.exchange import analytic_curve_point
from compas_brep.exchange import canonical_conic_interval
from compas_brep.exchange import conic_parameter_shift


def _cylinder(x: float, height: float = 20.0, radius: float = 1.2) -> Brep:
    """A cylinder lying along +y, centred at ``x``."""
    frame = Frame(Point(x, 0.0, 0.0), Vector(0.0, 0.0, 1.0), Vector(1.0, 0.0, 0.0))
    return Brep.from_cylinder(Cylinder(radius, height, frame=frame))


def _block() -> Brep:
    return Brep.from_box(Box(10.0))


def _round_trip(brep: Brep) -> Brep:
    return compas.json_loads(compas.json_dumps(brep))


# The three ways a cutter can meet the block, because they leave different faces
# behind: a bite leaves a partial wall, a channel leaves a full-turn wall with a
# seam, and a blind hole leaves a full-turn wall plus two caps.
SUBTRACTIONS = {
    "bite": lambda: _block() - _cylinder(-5.2),
    "channel": lambda: _block() - _cylinder(0.0),
    "blind_hole": lambda: _block() - _cylinder(0.0, height=4.0),
    "sphere": lambda: _block() - Brep.from_sphere(Sphere(2.0)),
    "cone": lambda: _block() - Brep.from_cone(Cone(2.0, 6.0)),
}


@pytest.mark.occ
@pytest.mark.parametrize("name", sorted(SUBTRACTIONS))
def test_subtracted_shape_survives_the_round_trip(name):
    brep = SUBTRACTIONS[name]()
    assert brep.is_valid, "the fixture itself must be sound before it proves anything"

    result = _round_trip(brep)

    # Volume first and signed: an orientation flip is not a small error, it is the
    # complement of the right answer, and `abs` would hide exactly that.
    assert result.volume == pytest.approx(brep.volume, rel=1e-9)
    assert result.is_valid
    assert len(result.faces) == len(brep.faces)


@pytest.mark.occ
def test_blind_hole_does_not_round_trip_into_a_bump():
    """The orientation bug's signature, pinned as its own case.

    A hole removes material, so the result must stay under the solid block's
    1000. Reversing the hole's wall added the same volume instead of subtracting
    it -- a result that passes any tolerance check against 'about 1000'.
    """
    brep = _block() - _cylinder(0.0, height=4.0)
    assert brep.volume < 1000.0

    assert _round_trip(brep).volume < 1000.0


@pytest.mark.occ
def test_accumulated_subtractions_match_the_in_process_reference():
    """Round-tripping between booleans must not change the answer.

    The cross-backend demo carves a block one cut at a time, sending it out and
    reading it back between cuts. That is the loop the bugs above corrupted:
    each round trip fed a slightly-wrong solid into the next boolean, so the
    error compounded rather than staying put.
    """
    positions = [-5.2, -4.2, -3.2, -2.2, -1.2, -0.2, 0.8, 1.8, 2.8]

    reference = _block()
    exchanged = _block()
    for x in positions:
        reference = reference - _cylinder(x)
        exchanged = _round_trip(_round_trip(exchanged) - _round_trip(_cylinder(x)))

        assert exchanged.is_valid
        assert exchanged.volume == pytest.approx(reference.volume, rel=1e-9)


# =============================================================================
# The pcurve and its edge must stay on one parameterization
# =============================================================================
#
# The format writes a trim's pcurve over its edge curve's parameter interval. That
# only holds if the interval survives the rebuild -- and two rebuilds quietly move
# it, each in its own way:
#
#   * a `line` carries only its endpoints, so it returns on [0, length];
#   * a *periodic* conic is normalized into [0, 2*pi) by `BRepBuilderAPI_MakeEdge`,
#     which discards whole turns.
#
# The second is not a near miss. An ellipse handed over on [6.96, 11.00] comes back
# on [0.67, 4.71], and its pcurve -- left on the old interval -- is then evaluated
# by extrapolation, more than a radius from the curve it is meant to trace.


@pytest.mark.occ
def test_a_conic_edge_beyond_one_turn_survives_the_round_trip():
    """A boolean leaves conic edges on whatever interval it likes, including past 2*pi."""
    cutter = Brep.from_box(Box(3.0, 3.0, 3.0))
    cutter.transform(Rotation.from_axis_and_angle([1, 0, 0], 0.6))
    cutter.translate([0, 0, -2.0])
    brep = Brep.from_cylinder(Cylinder(0.5, 3.0)) - cutter
    assert brep.is_valid

    result = _round_trip(brep)

    assert result.is_valid
    assert result.volume == pytest.approx(brep.volume, rel=1e-9)


@pytest.mark.occ
def test_every_analytic_edge_domain_is_written_within_one_turn():
    """The document records the interval the reader will rebuild, not OCC's raw one.

    Checked on the document rather than through a round trip, so the contract is
    pinned where it is stated instead of only where it happens to bite.
    """
    cutter = Brep.from_box(Box(3.0, 3.0, 3.0))
    cutter.transform(Rotation.from_axis_and_angle([1, 0, 0], 0.6))
    cutter.translate([0, 0, -2.0])
    data = (Brep.from_cylinder(Cylinder(0.5, 3.0)) - cutter).__data__

    for edge in data["edges"]:
        if edge["curve"]["type"] in ("circle", "arc", "ellipse"):
            start, end = edge["curve"]["data"]["domain"]
            assert 0.0 <= start < 2.0 * math.pi + 1e-9, f"domain starts outside one turn: {start}"
            assert end > start


# =============================================================================
# A mirrored parameter space is a reversed one
# =============================================================================


@pytest.mark.occ
def test_a_fillet_rebuilds_as_a_valid_solid():
    """OCC gives a fillet's patches left-handed placements.

    Straightening one mirrors the face's u, and mirroring is orientation-reversing:
    the same wire, re-expressed, winds the other way. The writer flips the face's
    `is_reversed` to absorb the surface normal turning over, but the wire has to be
    walked back the other way too. Without that, every corner patch of a filleted
    box rebuilt inside out -- reported as a negative face area and
    `BRepCheck_BadOrientationOfSubshape`, while the volume still integrated
    correctly, which is how it survived as a known xfail instead of a bug.
    """
    brep = Brep.from_box(Box(2.0)).filleted(0.3)
    assert brep.is_valid

    result = _round_trip(brep)

    assert result.is_valid
    assert len(result.faces) == len(brep.faces)
    assert result.volume == pytest.approx(brep.volume, rel=1e-6)


# =============================================================================
# The rebuild answers for itself
# =============================================================================


@pytest.mark.occ
def test_an_unbuildable_document_fails_at_the_rebuild():
    """A Brep that cannot be rebuilt must say so where it is built.

    compas_brep performs no geometry of its own -- it asks a kernel. So the moment a
    kernel hands back something it will not itself call valid is the moment to stop.
    Letting it through means the error surfaces at whatever later operation trips
    over it, and across a process boundary that is a boolean quietly consuming a
    broken operand and returning damage that only shows up in the *other* backend.
    """
    data = Brep.from_cylinder(Cylinder(1.0, 4.0)).__data__

    # Displace the wall's axis so the surface no longer passes through the circular
    # edges that bound it. Every index still resolves and the topology still parses --
    # it is the geometry that cannot close, which is exactly the class of damage a
    # document can carry across a process boundary undetected.
    for face in data["faces"]:
        if face["surface"]["type"] == "cylinder":
            face["surface"]["data"]["frame"]["point"] = [3.0, 0.0, 0.0]

    with pytest.raises(BrepInvalidError):
        Brep.__from_data__(data)


@pytest.mark.parametrize(
    "domain, expected_turns",
    [
        ((0.0, 2.0 * math.pi), 0),
        ((1.0, 2.0), 0),
        ((-0.5478, -1e-12), 1),  # Rhino writes arcs on intervals that start negative
        ((6.956, 10.996), -1),  # OCC writes ellipses past a full turn
        ((-2.0 * math.pi - 1.0, -2.0 * math.pi + 1.0), 2),
        # OCC hands over full circles starting at a negative denormal. `floor` sends
        # anything below zero a whole turn back, so this plainly-canonical interval
        # was moved 2*pi -- far enough that the arc rebuilt as a degenerate curve
        # (`Geom2d_TrimmedCurve::U1 == U2`) and the whole document was refused.
        ((-8.21730109605221e-32, 2.0 * math.pi), 0),
    ],
)
def test_conic_parameter_shift_lands_on_the_canonical_turn(domain, expected_turns):
    shift = conic_parameter_shift(domain)

    assert shift == pytest.approx(expected_turns * 2.0 * math.pi, abs=1e-9)
    start = domain[0] + shift
    assert -1e-9 <= start < 2.0 * math.pi + 1e-9


# =============================================================================
# An edge's interval runs forwards
# =============================================================================


@pytest.mark.parametrize("conic", [Circle(2.0), Ellipse(3.0, 1.5)])
def test_a_backwards_conic_interval_is_turned_around_without_moving_the_curve(conic):
    """A conic traversed clockwise about its own frame still gets a forwards interval.

    Rhino reports such an edge running from ``pi/2`` to ``-3*pi/2`` -- a scaled
    cylinder's elliptical rim is the ordinary way to get one. Written straight out,
    the pcurve that runs over that interval gets a *decreasing* knot vector, which is
    not a backwards curve but an unbuildable one: OCC rejects the whole document with
    ``BSpline curve: Knots interval values too close``.

    Turning it around must not move the edge: same points, same direction of travel,
    same end vertices -- only the frame and the interval are re-expressed.
    """
    domain = (math.pi / 2, -3 * math.pi / 2)

    turned, interval = canonical_conic_interval(conic, domain)

    assert interval[0] < interval[1]
    for i in range(41):
        fraction = i / 40.0
        before = analytic_curve_point(conic, domain[0] + (domain[1] - domain[0]) * fraction)
        after = analytic_curve_point(turned, interval[0] + (interval[1] - interval[0]) * fraction)
        assert (before - after).length == pytest.approx(0.0, abs=1e-12)


def test_a_forwards_conic_interval_is_left_alone():
    conic = Circle(2.0)

    turned, interval = canonical_conic_interval(conic, (0.0, 2.0 * math.pi))

    assert turned is conic
    assert interval == (0.0, 2.0 * math.pi)
