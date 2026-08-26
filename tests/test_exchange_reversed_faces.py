"""Regressions in the exchange document that only ``is_valid`` catches.

Every bug guarded here left volume and area correct, so nothing else in the suite
noticed. They need a *subtraction*: primitives and unions never leave a
pcurve-built face carrying ``is_reversed``.

See ``docs/cross-backend-gaps.md`` for what each one was.
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
    "bite": lambda: (_block() - _cylinder(-5.2))[0],
    "channel": lambda: (_block() - _cylinder(0.0))[0],
    "blind_hole": lambda: (_block() - _cylinder(0.0, height=4.0))[0],
    "sphere": lambda: (_block() - Brep.from_sphere(Sphere(2.0)))[0],
    "cone": lambda: (_block() - Brep.from_cone(Cone(2.0, 6.0)))[0],
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
    """A hole removes material, so a reversed wall reads as 1000 + V rather than 1000 - V."""
    brep = (_block() - _cylinder(0.0, height=4.0))[0]
    assert brep.volume < 1000.0

    assert _round_trip(brep).volume < 1000.0


@pytest.mark.occ
def test_accumulated_subtractions_match_the_in_process_reference():
    """A round trip between booleans must not change the answer, or the error compounds."""
    positions = [-5.2, -4.2, -3.2, -2.2, -1.2, -0.2, 0.8, 1.8, 2.8]

    reference = _block()
    exchanged = _block()
    for x in positions:
        reference = (reference - _cylinder(x))[0]
        exchanged = _round_trip((_round_trip(exchanged) - _round_trip(_cylinder(x)))[0])

        assert exchanged.is_valid
        assert exchanged.volume == pytest.approx(reference.volume, rel=1e-9)


# =============================================================================
# The pcurve and its edge must stay on one parameterization
# =============================================================================
#
# A pcurve is written over its edge curve's interval, so a rebuild that moves that
# interval has to move the pcurves with it.


@pytest.mark.occ
def test_a_conic_edge_beyond_one_turn_survives_the_round_trip():
    """A boolean leaves conic edges on whatever interval it likes, including past 2*pi."""
    cutter = Brep.from_box(Box(3.0, 3.0, 3.0))
    cutter.transform(Rotation.from_axis_and_angle([1, 0, 0], 0.6))
    cutter.translate([0, 0, -2.0])
    brep = (Brep.from_cylinder(Cylinder(0.5, 3.0)) - cutter)[0]
    assert brep.is_valid

    result = _round_trip(brep)

    assert result.is_valid
    assert result.volume == pytest.approx(brep.volume, rel=1e-9)


@pytest.mark.occ
def test_every_analytic_edge_domain_is_written_within_one_turn():
    """Checked on the document, so the contract is pinned where it is stated."""
    cutter = Brep.from_box(Box(3.0, 3.0, 3.0))
    cutter.transform(Rotation.from_axis_and_angle([1, 0, 0], 0.6))
    cutter.translate([0, 0, -2.0])
    data = (Brep.from_cylinder(Cylinder(0.5, 3.0)) - cutter)[0].__data__

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
    """Fillet patches get left-handed placements; mirroring u reverses winding too.

    Volume stays correct when they rebuild inside out, which is how this survived
    as a known xfail rather than a bug.
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
    """A rebuild the kernel calls invalid must raise there, not downstream."""
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
        # OCC hands over full circles starting at a negative denormal, which floors
        # a whole turn early and rebuilds the arc degenerate.
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
    """A clockwise conic still gets a forwards interval, without moving the edge.

    A decreasing interval yields a decreasing knot vector, which is unbuildable
    rather than merely backwards.
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
