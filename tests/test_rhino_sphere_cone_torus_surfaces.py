"""Sphere, cone, and torus faces on the Rhino backend: extract, write, read, rebuild (slice 05).

Slice 04 laid the rail with the cylinder: an analytic tag is only meaningful if the
face's pcurves are carried into the document's parameter space, which Rhino does not
share. This slice finishes the analytic set. The three surfaces do not share a
parameterization -- a sphere's v is a latitude, a torus's v runs around the pipe, a
cone's v runs along the generating line -- so each is measured against the document's
own evaluator rather than assumed.

Rhino-marked, so CI does not run them and `-m 'not rhino'` skips them by default. The
half of this slice that runs on CI is in test_exchange_fixtures.py (committed
Rhino-authored documents, read by OCC) and test_exchange_parameterization.py (the
document's parameter space, pinned against OCC).
"""

from __future__ import annotations

import math

import pytest
from compas.geometry import Box
from compas.geometry import Cone
from compas.geometry import ConicalSurface
from compas.geometry import Sphere
from compas.geometry import SphericalSurface
from compas.geometry import ToroidalSurface
from compas.geometry import Torus
from compas.tolerance import TOL
from exchange_fixtures import load_occ_fixture

from compas_brep import Brep

pytestmark = pytest.mark.rhino


# =============================================================================
# Geometry under test, and how to read it back
# =============================================================================

# (builder, COMPAS surface type, predicate name, tag, native Rhino TryGet* name)
CASES = {
    "sphere": (lambda: Brep.from_sphere(Sphere(1.3)), SphericalSurface, "is_sphere", "sphere", "TryGetSphere"),
    "cone": (lambda: Brep.from_cone(Cone(0.6, 1.5)), ConicalSurface, "is_cone", "cone", "TryGetCone"),
    "torus": (lambda: Brep.from_torus(Torus(2.0, 0.4)), ToroidalSurface, "is_torus", "torus", "TryGetTorus"),
}

CASE_NAMES = sorted(CASES)


def _analytic_face(brep, predicate):
    return next(f for f in brep.faces if getattr(f, predicate))


def _surface_tags(data: dict) -> set:
    return {face["surface"]["type"] for face in data["faces"]}


# =============================================================================
# 1. Extraction returns the analytic type
# =============================================================================


@pytest.mark.parametrize("name", CASE_NAMES)
def test_extraction_returns_the_analytic_surface_type(name):
    build, surface_type, predicate, tag, _ = CASES[name]
    face = _analytic_face(build(), predicate)

    assert isinstance(face.surface, surface_type)
    assert face.surface_type == tag
    assert getattr(face, predicate)
    assert not face.is_planar
    assert not face.is_nurbs


def test_extraction_sphere_radius_and_centre():
    face = _analytic_face(Brep.from_sphere(Sphere(1.3)), "is_sphere")
    assert TOL.is_close(face.surface.radius, 1.3)
    assert TOL.is_allclose(list(face.surface.frame.point), [0.0, 0.0, 0.0])


def test_extraction_torus_radii():
    face = _analytic_face(Brep.from_torus(Torus(2.0, 0.4)), "is_torus")
    assert TOL.is_close(face.surface.radius_axis, 2.0)
    assert TOL.is_close(face.surface.radius_pipe, 0.4)


def test_extraction_cone_uses_the_compas_radius_height_convention():
    # The convention the document stores is (radius, height, frame): radius the base
    # radius, the apex at +height along the frame's z-axis. Rhino's own cone is the
    # other way up (origin at the apex), so this is the mapping the issue asked to be
    # confirmed rather than assumed.
    face = _analytic_face(Brep.from_cone(Cone(0.6, 1.5)), "is_cone")
    assert TOL.is_close(face.surface.radius, 0.6)
    assert TOL.is_close(face.surface.height, 1.5)
    # The base sits at the frame origin; the apex is height away along +z.
    apex = face.surface.frame.point + face.surface.frame.zaxis * face.surface.height
    assert TOL.is_allclose(list(apex), [0.0, 0.0, 1.5])


# =============================================================================
# 2. Rhino writes the tag and reads it back
# =============================================================================


@pytest.mark.parametrize("name", CASE_NAMES)
def test_writer_emits_the_analytic_tag(name):
    build, _, _, tag, _ = CASES[name]
    assert tag in _surface_tags(build().__data__)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_roundtrip_preserves_the_tag_and_the_type(name):
    build, surface_type, predicate, tag, _ = CASES[name]
    original = build()
    restored = Brep.__from_data__(original.__data__)

    assert tag in _surface_tags(restored.__data__)
    assert isinstance(_analytic_face(restored, predicate).surface, surface_type)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_roundtrip_preserves_geometry(name):
    build, _, _, _, _ = CASES[name]
    original = build()
    restored = Brep.__from_data__(original.__data__)

    assert len(restored.faces) == len(original.faces)
    assert restored.is_valid
    assert TOL.is_close(restored.volume, original.volume)


# =============================================================================
# 3. The rebuilt native face is the analytic surface, not a NURBS look-alike
# =============================================================================


@pytest.mark.parametrize("name", CASE_NAMES)
def test_roundtrip_rebuilds_a_native_analytic_face(name):
    # Ask Rhino itself, not our extraction: a NURBS approximation would satisfy every
    # COMPAS-level assertion and fail this one. This is the representational-fidelity
    # bar ADR-0001 sets.
    build, _, _, _, trygetter = CASES[name]
    restored = Brep.__from_data__(build().__data__)

    hits = [f for f in restored._native_brep.Faces if getattr(f.UnderlyingSurface(), trygetter)(TOL.absolute)[0]]
    assert len(hits) == 1


def _hausdorff(points_a, points_b):
    return max(min(math.dist(list(a), list(b)) for b in points_b) for a in points_a)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_rebuilt_surface_is_the_same_surface(name):
    # Representational fidelity of the surface: the rebuilt surface must trace the
    # same point set as the original, densely sampled. A set comparison rather than
    # a pointwise (u, v) one because a sphere has no preferred pole -- Rhino's
    # TryGetSphere picks an equatorial-plane orientation arbitrarily, so a rebuilt
    # sphere can re-extract with its v flipped while being the identical surface.
    # That the pcurves still land in that parameter space is a separate claim, and
    # `test_roundtrip_preserves_geometry` (valid + solid + exact volume) is what
    # verifies it -- an invalid or wrong-volume solid is what a mislanded pcurve
    # produces.
    build, _, predicate, _, _ = CASES[name]
    original = build()
    restored = Brep.__from_data__(original.__data__)
    a = _analytic_face(original, predicate).surface
    b = _analytic_face(restored, predicate).surface

    grid = [(i / 10.0, j / 10.0) for i in range(11) for j in range(11)]
    points_a = [a.point_at(u, v) for u, v in grid]
    points_b = [b.point_at(u, v) for u, v in grid]
    assert _hausdorff(points_a, points_b) < 1e-6
    assert _hausdorff(points_b, points_a) < 1e-6


# =============================================================================
# 4. Rhino reads what OCC wrote
# =============================================================================


@pytest.mark.parametrize("name", CASE_NAMES)
def test_occ_authored_document_rebuilds_as_a_native_analytic_face(name):
    # The direction the whole slice exists for. OCC spells a pole or apex as a
    # zero-length edge where Rhino spells it as a singular trim, so this also
    # exercises the degenerate-edge bridge. Read from a committed OCC-authored
    # document because OCC is never importable in the same process as Rhino.
    build, _, _, tag, trygetter = CASES[name]
    restored = Brep.__from_data__(load_occ_fixture(name))

    hits = [f for f in restored._native_brep.Faces if getattr(f.UnderlyingSurface(), trygetter)(TOL.absolute)[0]]
    assert len(hits) == 1
    assert tag in _surface_tags(restored.__data__)


def test_occ_authored_cone_survives_a_round_trip_with_radius_and_height():
    # A cone crossing OCC -> Rhino -> OCC must keep the (radius, height) the document
    # stores. This is the convention the two kernels disagree on, so it is the one to
    # pin explicitly rather than trust a volume for.
    restored = Brep.__from_data__(load_occ_fixture("cone"))
    cone = _analytic_face(restored, "is_cone").surface

    assert TOL.is_close(cone.radius, 0.5)
    assert TOL.is_close(cone.height, 1.0)


# =============================================================================
# 5. Loss policy: an unrepresentable surface raises rather than degrading
# =============================================================================


def test_rebuild_raises_on_a_surface_type_it_cannot_represent():
    # The loss policy (ADR-0001): a surface the Rhino backend cannot represent raises
    # BrepError rather than being approximated or skipped. Reaching it needs a COMPAS
    # surface outside the format's set, since every native Rhino surface converts to
    # NURBS -- so this drives the rebuild seam directly.
    from compas.geometry import Frame

    from compas_brep.backend.rhino.conversion import _surface_to_rhino
    from compas_brep.errors import BrepError

    class _UnknownSurface:
        frame = Frame.worldXY()

    with pytest.raises(BrepError):
        _surface_to_rhino(_UnknownSurface(), face=None)


def test_a_fillet_face_stays_nurbs_rather_than_a_wrongly_parameterized_cone():
    # A box fillet is exactly a cylinder to Rhino, and slice 04 already keeps it
    # `nurbs` because its angle is not linear in either parameter. The same guard must
    # hold now that three more analytic probes run: the fillet must not be mistaken
    # for any of them either.
    filleted = Brep.from_box(Box(2.0, 2.0, 2.0)).filleted(0.3)
    for face in filleted.faces:
        assert not face.is_sphere
        assert not face.is_cone
        assert not face.is_torus
