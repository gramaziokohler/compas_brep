"""Tests for translate/scale/rotate, inherited from compas.geometry.Geometry, on NurbsCurve and NurbsSurface."""

import math

from compas.geometry import Point
from compas.geometry import Vector

from compas_brep.curves.nurbs import NurbsCurve
from compas_brep.surfaces.nurbs import NurbsSurface

# =============================================================================
# Helpers
# =============================================================================


def _curve():
    return NurbsCurve.from_points([Point(0, 0, 0), Point(1, 0, 0), Point(2, 1, 0), Point(3, 1, 1)])


def _surface():
    # Flat grid on the XY plane: points[i][j] == Point(i, j, 0).
    return NurbsSurface.from_meshgrid(4, 4)


# =============================================================================
# NurbsCurve
# =============================================================================


class TestNurbsCurveTransforms:
    def test_translate_moves_all_points(self):
        curve = _curve()
        curve.translate(Vector(1, 2, 3))
        assert curve.points[0] == Point(1, 2, 3)
        assert curve.points[1] == Point(2, 2, 3)

    def test_translated_returns_new_curve_and_leaves_original(self):
        curve = _curve()
        new_curve = curve.translated(Vector(1, 0, 0))
        assert isinstance(new_curve, NurbsCurve)
        assert curve.points[0] == Point(0, 0, 0)
        assert new_curve.points[0] == Point(1, 0, 0)

    def test_scale_uniform(self):
        curve = _curve()
        curve.scale(2)
        assert curve.points[2] == Point(4, 2, 0)

    def test_scale_nonuniform(self):
        curve = _curve()
        curve.scale(2, 3, 4)
        assert curve.points[2] == Point(4, 3, 0)
        assert curve.points[3] == Point(6, 3, 4)

    def test_scaled_returns_new_curve_and_leaves_original(self):
        curve = _curve()
        new_curve = curve.scaled(2)
        assert isinstance(new_curve, NurbsCurve)
        assert curve.points[1] == Point(1, 0, 0)
        assert new_curve.points[1] == Point(2, 0, 0)

    def test_rotate_default_axis_and_point(self):
        # Default axis is Z, default point is the origin.
        curve = _curve()
        curve.rotate(math.pi / 2)
        p = curve.points[1]
        assert abs(p.x - 0.0) < 1e-6
        assert abs(p.y - 1.0) < 1e-6

    def test_rotated_returns_new_curve_and_leaves_original(self):
        curve = _curve()
        new_curve = curve.rotated(math.pi / 2)
        assert isinstance(new_curve, NurbsCurve)
        assert curve.points[1] == Point(1, 0, 0)
        p = new_curve.points[1]
        assert abs(p.x - 0.0) < 1e-6
        assert abs(p.y - 1.0) < 1e-6


# =============================================================================
# NurbsSurface
# =============================================================================


class TestNurbsSurfaceTransforms:
    def test_translate_moves_all_points(self):
        surface = _surface()
        surface.translate(Vector(1, 1, 1))
        assert surface.points[0][0] == Point(1, 1, 1)
        assert surface.points[2][1] == Point(3, 2, 1)

    def test_translated_returns_new_surface_and_leaves_original(self):
        surface = _surface()
        new_surface = surface.translated(Vector(1, 0, 0))
        assert isinstance(new_surface, NurbsSurface)
        assert surface.points[1][1] == Point(1, 1, 0)
        assert new_surface.points[1][1] == Point(2, 1, 0)

    def test_scale_nonuniform(self):
        surface = _surface()
        surface.scale(2, 3, 4)
        assert surface.points[1][1] == Point(2, 3, 0)
        assert surface.points[2][3] == Point(4, 9, 0)

    def test_scaled_returns_new_surface_and_leaves_original(self):
        surface = _surface()
        new_surface = surface.scaled(2)
        assert isinstance(new_surface, NurbsSurface)
        assert surface.points[1][1] == Point(1, 1, 0)
        assert new_surface.points[1][1] == Point(2, 2, 0)

    def test_rotate_default_axis_and_point(self):
        # Default axis is Z, default point is the origin.
        surface = _surface()
        surface.rotate(math.pi / 2)
        p = surface.points[1][0]
        assert abs(p.x - 0.0) < 1e-6
        assert abs(p.y - 1.0) < 1e-6

    def test_rotated_returns_new_surface_and_leaves_original(self):
        surface = _surface()
        new_surface = surface.rotated(math.pi / 2)
        assert isinstance(new_surface, NurbsSurface)
        assert surface.points[1][0] == Point(1, 0, 0)
        p = new_surface.points[1][0]
        assert abs(p.x - 0.0) < 1e-6
        assert abs(p.y - 1.0) < 1e-6
