"""The document's analytic parameter space, pinned against the real kernel.

``exchange.analytic_surface_point`` states how a reader must measure ``(u, v)``
on an analytic face. Every pcurve in the format is written against it, so if it
drifts from what OCC actually does, every analytic tag silently means something
else -- and nothing else in the suite would notice, because both OCC's writer and
its reader would drift together.

These tests are what let the Rhino backend verify its parameter maps against the
format rather than against a belief about the format. They need OCC only: the
claim under test is "the document's parameter space is OCC's", and Rhino's
obligation to map onto it is tested on the Rhino side.
"""

from __future__ import annotations

import math

import pytest
from compas.geometry import ConicalSurface
from compas.geometry import CylindricalSurface
from compas.geometry import Frame
from compas.geometry import Point
from compas.geometry import SphericalSurface
from compas.geometry import ToroidalSurface
from compas.geometry import Vector
from compas.tolerance import TOL

from compas_brep.exchange import analytic_surface_params
from compas_brep.exchange import analytic_surface_point
from compas_brep.exchange import analytic_surface_v_is_periodic

# A frame that is not the world frame: an axis-aligned one at the origin would hide
# a swapped axis, a flipped handedness, and every frame-relative sign error.
TILTED = Frame(Point(1.0, -2.0, 0.5), Vector(0.6, 0.8, 0.0), Vector(-0.8, 0.6, 0.0))

SURFACES = {
    "cylinder": CylindricalSurface(0.7, frame=TILTED),
    "sphere": SphericalSurface(1.3, frame=TILTED),
    "torus": ToroidalSurface(2.0, 0.4, frame=TILTED),
    "cone": ConicalSurface(0.6, 1.5, frame=TILTED),
}

# The v range each tag is sampled over: its natural extent, not an arbitrary one.
V_RANGES = {
    "cylinder": (-1.0, 1.0),
    "sphere": (-math.pi / 2, math.pi / 2),
    "torus": (0.0, 2 * math.pi),
    "cone": (0.0, 1.0),
}


def _samples(tag):
    v_min, v_max = V_RANGES[tag]
    for i in range(7):
        for j in range(7):
            yield (2 * math.pi * i / 6.0, v_min + (v_max - v_min) * j / 6.0)


# =============================================================================
# 1. The document's evaluator is OCC's
# =============================================================================


@pytest.mark.occ
@pytest.mark.parametrize("tag", sorted(SURFACES))
def test_document_evaluator_matches_the_occ_surface(tag):
    from compas_brep.backend.occ.conversion import _analytic_surface_to_occ

    surface = SURFACES[tag]
    occ_surface = _analytic_surface_to_occ(surface)

    for u, v in _samples(tag):
        occ_point = occ_surface.Value(u, v)
        expected = analytic_surface_point(surface, u, v)
        assert TOL.is_allclose([occ_point.X(), occ_point.Y(), occ_point.Z()], expected), (
            f"the document's {tag!r} parameter space disagrees with OCC's at (u={u}, v={v})"
        )


# =============================================================================
# 2. The inverse inverts
# =============================================================================


@pytest.mark.parametrize("tag", sorted(SURFACES))
def test_params_invert_the_evaluator(tag):
    surface = SURFACES[tag]

    for u, v in _samples(tag):
        point = analytic_surface_point(surface, u, v)
        u_back, v_back = analytic_surface_params(surface, point)

        # u comes back folded into (-pi, pi], and a periodic v likewise: the point
        # is what round-trips, not the raw number.
        assert TOL.is_allclose(analytic_surface_point(surface, u_back, v_back), point)


@pytest.mark.parametrize("tag", sorted(SURFACES))
def test_params_are_exact_on_the_principal_branch(tag):
    surface = SURFACES[tag]
    v_min, v_max = V_RANGES[tag]
    v = (v_min + v_max) / 2 if not analytic_surface_v_is_periodic(surface) else 0.5

    for u in (-2.0, -0.5, 0.0, 0.5, 2.0):
        u_back, v_back = analytic_surface_params(surface, analytic_surface_point(surface, u, v))
        assert TOL.is_close(u_back, u)
        assert TOL.is_close(v_back, v)


# =============================================================================
# 3. Only the torus wraps in v
# =============================================================================


def test_only_the_torus_has_a_periodic_v():
    assert analytic_surface_v_is_periodic(SURFACES["torus"])
    assert not analytic_surface_v_is_periodic(SURFACES["sphere"])
    assert not analytic_surface_v_is_periodic(SURFACES["cylinder"])
    assert not analytic_surface_v_is_periodic(SURFACES["cone"])
