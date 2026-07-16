"""Cylindrical faces on the Rhino backend: extract, write, read, rebuild (slice 04).

Rhino used to emit `plane` or `nurbs` and nothing else, and understood nothing else on
rebuild, so every analytic tag OCC wrote was unreadable here and the faces were dropped
without error. These tests pin the tracer that ends that: a cylinder.

Rhino-marked, so CI does not run them and `-m 'not rhino'` skips them by default -- the
half of this slice that runs on CI is in test_exchange_fixtures.py, reading committed
Rhino-authored documents.
"""

from __future__ import annotations

import math

import pytest
from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import CylindricalSurface
from compas.geometry import Frame
from compas.tolerance import TOL
from exchange_fixtures import load_occ_fixture

from compas_brep import Brep

pytestmark = pytest.mark.rhino

RADIUS = 0.5
HEIGHT = 2.0


@pytest.fixture
def cylinder_brep():
    return Brep.from_cylinder(Cylinder(RADIUS, HEIGHT))


@pytest.fixture
def wall(cylinder_brep):
    return next(f for f in cylinder_brep.faces if f.is_cylinder)


def _surface_tags(data: dict) -> set:
    return {face["surface"]["type"] for face in data["faces"]}


# =============================================================================
# 1. Extraction
# =============================================================================


def test_extraction_wall_is_a_cylindrical_surface(wall):
    assert isinstance(wall.surface, CylindricalSurface)


def test_extraction_wall_radius_matches_the_native_surface(wall):
    assert TOL.is_close(wall.surface.radius, RADIUS)


def test_extraction_wall_frame_matches_the_native_surface(wall):
    assert isinstance(wall.surface.frame, Frame)
    # A cylinder of height 2 centred on the origin has its base at z = -1.
    assert TOL.is_allclose(list(wall.surface.frame.point), [0.0, 0.0, -1.0])
    assert TOL.is_allclose(list(wall.surface.frame.zaxis), [0.0, 0.0, 1.0])


def test_extraction_wall_reports_the_cylinder_surface_type(wall):
    assert wall.surface_type == "cylinder"
    assert wall.is_cylinder
    assert not wall.is_planar
    assert not wall.is_nurbs


def test_extraction_a_planar_face_is_not_mistaken_for_a_cylinder(cylinder_brep):
    caps = [f for f in cylinder_brep.faces if f.is_planar]
    assert len(caps) == 2
    assert not any(f.is_cylinder for f in caps)


def test_extraction_a_fillet_face_is_not_tagged_cylinder():
    # A box fillet is exactly a cylinder to Rhino's TryGetCylinder, but Rhino stores
    # it as a rational NURBS whose angle is not linear in either parameter, so its
    # pcurves cannot be carried into the document's (angle, height) space. Tagging it
    # would write trims that land at the wrong angle. `nurbs` reproduces the face
    # exactly, so this is a conservative choice rather than a lossy one.
    filleted = Brep.from_box(Box(2.0, 2.0, 2.0)).filleted(0.3)
    assert not any(f.is_cylinder for f in filleted.faces)


# =============================================================================
# 2. Rhino writes the tag, and reads it back
# =============================================================================


def test_writer_emits_the_cylinder_tag(cylinder_brep):
    assert "cylinder" in _surface_tags(cylinder_brep.__data__)


def test_writer_emits_pcurves_in_angle_and_height():
    # The document's cylinder is a COMPAS CylindricalSurface, whose parameters are
    # (angle, height) -- the space OCC already writes. Rhino's native wall is
    # parameterized by arc length, so a wall of radius 0.5 would run its u to pi
    # rather than 2*pi if the conversion were skipped. This is the assertion that
    # fails if `_canonical_pcurve` stops being applied.
    wall_data = next(f for f in Brep.from_cylinder(Cylinder(RADIUS, HEIGHT)).__data__["faces"] if f["surface"]["type"] == "cylinder")
    angles = [point[0] for loop in wall_data["loops"] for trim in loop["trims"] for point in trim["curve_2d"]["points"]]

    assert TOL.is_close(min(angles), 0.0)
    assert TOL.is_close(max(angles), 2 * math.pi)


def test_roundtrip_preserves_the_cylinder_tag(cylinder_brep):
    restored = Brep.__from_data__(cylinder_brep.__data__)
    assert "cylinder" in _surface_tags(restored.__data__)


def test_roundtrip_rebuilds_a_native_cylindrical_face(cylinder_brep):
    restored = Brep.__from_data__(cylinder_brep.__data__)
    wall = next(f for f in restored.faces if f.is_cylinder)

    assert isinstance(wall.surface, CylindricalSurface)
    assert TOL.is_close(wall.surface.radius, RADIUS)


def test_roundtrip_preserves_geometry(cylinder_brep):
    restored = Brep.__from_data__(cylinder_brep.__data__)

    assert len(restored.faces) == len(cylinder_brep.faces)
    assert restored.is_valid
    assert TOL.is_close(restored.volume, cylinder_brep.volume)


def test_roundtrip_of_a_trimmed_wall_keeps_its_hole():
    # A boolean-cut wall, where the face is genuinely trimmed and carries an inner
    # loop -- the case a rectangular parametric crop could not represent.
    holed = Brep.from_box(Box(2.0, 2.0, 2.0)) - Brep.from_cylinder(Cylinder(0.3, 4.0))
    restored = Brep.__from_data__(holed.__data__)

    assert len(restored.faces) == len(holed.faces)
    assert any(f.is_cylinder for f in restored.faces)
    assert TOL.is_close(restored.volume, holed.volume)


# =============================================================================
# 3. Rhino reads what OCC wrote
# =============================================================================


def test_occ_authored_cylinder_rebuilds_as_a_native_rhino_cylinder():
    # The direction the whole slice exists for: OCC tags a wall `cylinder`, and Rhino
    # must rebuild a real cylindrical face from it instead of dropping it silently.
    # Read from a committed OCC-authored document because OCC is never importable in
    # the same process as Rhino.
    restored = Brep.__from_data__(load_occ_fixture("cylinder"))

    assert len(restored.faces) == 3

    walls = [f for f in restored._native_brep.Faces if not f.UnderlyingSurface().IsPlanar()]
    assert len(walls) == 1

    # Ask Rhino itself, not our own extraction: a NURBS approximation of a cylinder
    # would satisfy every COMPAS-level assertion and fail this one.
    success, cylinder = walls[0].UnderlyingSurface().TryGetCylinder(TOL.absolute)
    assert success
    assert TOL.is_close(cylinder.Radius, RADIUS)


def test_occ_authored_cylinder_survives_a_rhino_reserialization():
    restored = Brep.__from_data__(load_occ_fixture("cylinder"))
    assert "cylinder" in _surface_tags(restored.__data__)


# =============================================================================
# 4. The rebuilt surface is the same surface, at the same parameters
# =============================================================================


def test_rebuilt_surface_samples_match_the_original(cylinder_brep):
    # Representational fidelity is not a volume match -- a NURBS approximation would
    # pass that. The rebuilt face must be the same cylinder, parameterized the same
    # way, so that a pcurve written against one lands in the same place on the other.
    original = next(f for f in cylinder_brep.faces if f.is_cylinder).surface
    rebuilt = next(f for f in Brep.__from_data__(cylinder_brep.__data__).faces if f.is_cylinder).surface

    for i in range(9):
        for j in range(5):
            u = 2 * math.pi * i / 8.0
            v = HEIGHT * j / 4.0
            assert TOL.is_allclose(list(original.point_at(u, v)), list(rebuilt.point_at(u, v)), atol=1e-6)
