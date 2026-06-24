"""This is an attempt at Pure-Python rational NURBS surface built on scipy.interpolate.BSpline which seems more doable than a pure-Python Brep.

This is a replacement for the compas.geometry.NurbsSurface pluggable but need to be evaluated for completness.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import numpy as np
from compas.data import Data
from compas.geometry import Frame
from compas.geometry import Point
from compas.geometry import Vector
from scipy.interpolate import BSpline

from compas_brep.curves import NurbsCurve

if TYPE_CHECKING:
    from compas.geometry import Transformation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_knotvector(n_points: int, degree: int) -> tuple[list[float], list[int]]:
    """Return (knots, mults) for a clamped uniform knot vector.

    Parameters
    ----------
    n_points
        Number of control points.
    degree
        Polynomial degree (will be clamped to ``n_points - 1``).
    """
    degree = min(degree, n_points - 1)
    n_internal = n_points - degree - 1
    if n_internal < 0:
        n_internal = 0
    knots: list[float] = [0.0]
    mults: list[int] = [degree + 1]
    for i in range(1, n_internal + 1):
        knots.append(float(i) / (n_internal + 1))
        mults.append(1)
    knots.append(1.0)
    mults.append(degree + 1)
    return knots, mults


def _expand_knotvector(knots: list[float], mults: list[int]) -> list[float]:
    """Expand unique knots + multiplicities into a full knot vector."""
    kv: list[float] = []
    for k, m in zip(knots, mults):
        kv.extend([k] * m)
    return kv


# ---------------------------------------------------------------------------
# NurbsSurface
# ---------------------------------------------------------------------------


class ControlPointGrid:
    """A 2-D grid wrapper that supports both ``grid[i][j]`` and ``grid[i, j]`` indexing.

    Modifications through ``grid[i, j] = point`` invalidate the parent surface's caches.
    """

    def __init__(self, data: list[list[Point]], surface: NurbsSurface | None = None) -> None:
        self._data = data
        self._surface = surface

    def __getitem__(self, key):
        if isinstance(key, tuple):
            i, j = key
            return self._data[i][j]
        return self._data[key]

    def __setitem__(self, key, value):
        if isinstance(key, tuple):
            i, j = key
            self._data[i][j] = Point(value.x, value.y, value.z) if not isinstance(value, Point) else value
        else:
            self._data[key] = value
        if self._surface is not None:
            self._surface._invalidate_cache()

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __repr__(self) -> str:
        return repr(self._data)


class NurbsSurface(Data):
    """A rational NURBS surface (tensor-product).

    Parameters
    ----------
    name
        The name of the surface.
    """

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name=name)
        self._points: list[list[Point]] = []
        self._weights: list[list[float]] = []
        self._knots_u: list[float] = []
        self._knots_v: list[float] = []
        self._mults_u: list[int] = []
        self._mults_v: list[int] = []
        self._degree_u: int = 0
        self._degree_v: int = 0
        # caches
        self._basis_u: dict[int, BSpline] | None = None
        self._basis_v: dict[int, BSpline] | None = None
        self._homo_cpts: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def points(self) -> ControlPointGrid:
        """2-D grid of control points (nu x nv).

        Supports both ``surface.points[i][j]`` and ``surface.points[i, j]`` indexing.
        """
        return ControlPointGrid(self._points, self)

    @property
    def weights(self) -> list[list[float]]:
        """2-D grid of weights."""
        return self._weights

    @property
    def knots_u(self) -> list[float]:
        """Unique knot values in U direction."""
        return self._knots_u

    @property
    def knots_v(self) -> list[float]:
        """Unique knot values in V direction."""
        return self._knots_v

    @property
    def mults_u(self) -> list[int]:
        """Knot multiplicities in U direction."""
        return self._mults_u

    @property
    def mults_v(self) -> list[int]:
        """Knot multiplicities in V direction."""
        return self._mults_v

    @property
    def knotvector_u(self) -> list[float]:
        """Full knot vector in U direction."""
        return _expand_knotvector(self._knots_u, self._mults_u)

    @property
    def knotvector_v(self) -> list[float]:
        """Full knot vector in V direction."""
        return _expand_knotvector(self._knots_v, self._mults_v)

    @property
    def degree_u(self) -> int:
        """Polynomial degree in U direction."""
        return self._degree_u

    @property
    def degree_v(self) -> int:
        """Polynomial degree in V direction."""
        return self._degree_v

    @property
    def domain_u(self) -> tuple[float, float]:
        """Parameter domain in U."""
        kv = self.knotvector_u
        return (kv[self._degree_u], kv[-(self._degree_u + 1)])

    @property
    def domain_v(self) -> tuple[float, float]:
        """Parameter domain in V."""
        kv = self.knotvector_v
        return (kv[self._degree_v], kv[-(self._degree_v + 1)])

    @property
    def is_periodic_u(self) -> bool:
        return False

    @property
    def is_periodic_v(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _invalidate_cache(self) -> None:
        self._basis_u = None
        self._basis_v = None
        self._homo_cpts = None

    def _get_homo_cpts(self) -> np.ndarray:
        """Return homogeneous control point array of shape (nu, nv, 4)."""
        if self._homo_cpts is not None:
            return self._homo_cpts
        nu = len(self._points)
        nv = len(self._points[0])
        cpts = np.zeros((nu, nv, 4))
        for i in range(nu):
            for j in range(nv):
                p = self._points[i][j]
                w = self._weights[i][j]
                cpts[i, j] = [p.x * w, p.y * w, p.z * w, w]
        self._homo_cpts = cpts
        return cpts

    def _get_basis_u(self) -> dict[int, BSpline]:
        """Cached dictionary of U-direction basis BSplines."""
        if self._basis_u is not None:
            return self._basis_u
        kv = np.array(self.knotvector_u, dtype=float)
        nu = len(self._points)
        self._basis_u = {}
        for i in range(nu):
            c = np.zeros(nu)
            c[i] = 1.0
            self._basis_u[i] = BSpline(kv, c, self._degree_u, extrapolate=False)
        return self._basis_u

    def _get_basis_v(self) -> dict[int, BSpline]:
        """Cached dictionary of V-direction basis BSplines."""
        if self._basis_v is not None:
            return self._basis_v
        kv = np.array(self.knotvector_v, dtype=float)
        nv = len(self._points[0])
        self._basis_v = {}
        for j in range(nv):
            c = np.zeros(nv)
            c[j] = 1.0
            self._basis_v[j] = BSpline(kv, c, self._degree_v, extrapolate=False)
        return self._basis_v

    def _eval_basis_u(self, u: float) -> np.ndarray:
        """Evaluate all U basis functions at *u*, return shape (nu,)."""
        basis = self._get_basis_u()
        nu = len(self._points)
        vals = np.zeros(nu)
        for i in range(nu):
            vals[i] = float(basis[i](u))
        return vals

    def _eval_basis_v(self, v: float) -> np.ndarray:
        """Evaluate all V basis functions at *v*, return shape (nv,)."""
        basis = self._get_basis_v()
        nv = len(self._points[0])
        vals = np.zeros(nv)
        for j in range(nv):
            vals[j] = float(basis[j](v))
        return vals

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_parameters(
        cls,
        points: list[list[Point]],
        weights: list[list[float]],
        knots_u: list[float],
        knots_v: list[float],
        mults_u: list[int],
        mults_v: list[int],
        degree_u: int,
        degree_v: int,
    ) -> NurbsSurface:
        """Create a NurbsSurface from explicit parameters.

        Parameters
        ----------
        points
            2-D grid of control points (nu x nv).
        weights
            2-D grid of weights.
        knots_u
            Unique knot values in U direction.
        knots_v
            Unique knot values in V direction.
        mults_u
            Multiplicities in U direction.
        mults_v
            Multiplicities in V direction.
        degree_u
            Degree in U direction.
        degree_v
            Degree in V direction.
        """
        surface = cls()
        surface._points = [[Point(p.x, p.y, p.z) for p in row] for row in points]
        surface._weights = [list(row) for row in weights]
        surface._knots_u = list(knots_u)
        surface._knots_v = list(knots_v)
        surface._mults_u = list(mults_u)
        surface._mults_v = list(mults_v)
        surface._degree_u = degree_u
        surface._degree_v = degree_v
        return surface

    @classmethod
    def from_points(cls, points: list[list[Point]], degree_u: int = 3, degree_v: int = 3) -> NurbsSurface:
        """Create a NurbsSurface from a 2-D grid of control points.

        Generates clamped uniform knot vectors. Degree is clamped to
        ``min(degree, n_points - 1)`` in each direction.

        Parameters
        ----------
        points
            2-D grid (nu x nv) of control points.
        degree_u
            Desired degree in U direction.
        degree_v
            Desired degree in V direction.
        """
        nu = len(points)
        nv = len(points[0])
        degree_u = min(degree_u, nu - 1)
        degree_v = min(degree_v, nv - 1)
        knots_u, mults_u = _generate_knotvector(nu, degree_u)
        knots_v, mults_v = _generate_knotvector(nv, degree_v)
        weights = [[1.0] * nv for _ in range(nu)]
        return cls.from_parameters(points, weights, knots_u, knots_v, mults_u, mults_v, degree_u, degree_v)

    @classmethod
    def from_meshgrid(cls, nu: int = 4, nv: int = 4) -> NurbsSurface:
        """Create a flat rectangular surface on the XY plane.

        Control points lie on a regular grid from (0, 0, 0) to (nu-1, nv-1, 0).

        Parameters
        ----------
        nu
            Number of control points in U.
        nv
            Number of control points in V.
        """
        points = [[Point(float(i), float(j), 0.0) for j in range(nv)] for i in range(nu)]
        degree_u = min(3, nu - 1)
        degree_v = min(3, nv - 1)
        return cls.from_points(points, degree_u=degree_u, degree_v=degree_v)

    @classmethod
    def from_extrusion(cls, curve: NurbsCurve, vector: Vector) -> NurbsSurface:
        """Create a surface by extruding a curve along a vector.

        U direction follows the curve, V direction is the extrusion.

        Parameters
        ----------
        curve
            The profile curve.
        vector
            The extrusion direction.
        """
        # Two rows of control points: original and offset
        pts_u0 = curve.points
        pts_u1 = [Point(p.x + vector.x, p.y + vector.y, p.z + vector.z) for p in pts_u0]
        weights_row = curve.weights
        knots_u = list(curve.knots)
        mults_u = list(curve.mults)
        degree_u = curve.degree
        # V direction: linear (degree 1), two control points
        knots_v = [0.0, 1.0]
        mults_v = [2, 2]
        degree_v = 1
        # Note: points layout is [v_row][u_col] but we want [u_row][v_col].
        # curve direction = U, extrusion = V.
        # So points[i_u][i_v]: i_u indexes along curve, i_v indexes along extrusion.
        nu = len(pts_u0)
        pts_grid: list[list[Point]] = []
        w_grid: list[list[float]] = []
        for i in range(nu):
            p0 = pts_u0[i]
            p1 = pts_u1[i]
            w0 = weights_row[i]
            pts_grid.append([Point(p0.x, p0.y, p0.z), Point(p1.x, p1.y, p1.z)])
            w_grid.append([w0, w0])
        return cls.from_parameters(pts_grid, w_grid, knots_u, knots_v, mults_u, mults_v, degree_u, degree_v)

    @classmethod
    def from_fill(
        cls,
        curve1: NurbsCurve,
        curve2: NurbsCurve,
        curve3: NurbsCurve | None = None,
        curve4: NurbsCurve | None = None,
        style: str = "stretch",
    ) -> NurbsSurface:
        """Create a surface filling between boundary curves.

        For 2 curves a ruled surface (linear interpolation) is created.
        For 4 curves a simplified bilinear Coons patch is created.

        Parameters
        ----------
        curve1
            First boundary curve.
        curve2
            Second boundary curve (opposite to curve1).
        curve3
            Third boundary curve.
        curve4
            Fourth boundary curve.
        style
            Fill style (currently only "stretch" is supported).
        """
        n_samples = 20

        def _sample_curve(crv: NurbsCurve, n: int) -> list[Point]:
            a, b = crv.domain
            return [crv.point_at(a + (b - a) * i / n) for i in range(n + 1)]

        pts1 = _sample_curve(curve1, n_samples)
        pts2 = _sample_curve(curve2, n_samples)

        if curve3 is None or curve4 is None:
            # Ruled surface between curve1 and curve2
            nv = len(pts1)
            points: list[list[Point]] = [
                [Point(p.x, p.y, p.z) for p in pts1],
                [Point(p.x, p.y, p.z) for p in pts2],
            ]
            degree_u = 1
            degree_v = min(3, nv - 1)
            return cls.from_points(points, degree_u=degree_u, degree_v=degree_v)

        # 4-curve Coons patch (bilinear blend)
        pts3 = _sample_curve(curve3, n_samples)
        pts4 = _sample_curve(curve4, n_samples)
        n = n_samples
        grid: list[list[Point]] = []
        # Corners: c1(0)=c3(0), c1(1)=c4(0), c2(0)=c3(1), c2(1)=c4(1)
        p00 = pts1[0]
        p10 = pts1[-1]
        p01 = pts2[0]
        p11 = pts2[-1]
        for i in range(n + 1):
            u = i / n
            row: list[Point] = []
            for j in range(n + 1):
                v = j / n
                # Bilinear Coons
                lc = _lerp(pts1[i], pts2[i], v)  # ruled c1-c2 at u, interpolated in v
                lr = _lerp(pts3[j], pts4[j], u)  # ruled c3-c4 at v, interpolated in u
                bil = _bilerp(p00, p10, p01, p11, u, v)
                x = lc.x + lr.x - bil.x
                y = lc.y + lr.y - bil.y
                z = lc.z + lr.z - bil.z
                row.append(Point(x, y, z))
            grid.append(row)
        degree_u = min(3, n)
        degree_v = min(3, n)
        return cls.from_points(grid, degree_u=degree_u, degree_v=degree_v)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def point_at(self, u: float, v: float) -> Point:
        """Evaluate the surface at parameters (u, v).

        Parameters
        ----------
        u
            Parameter in U direction.
        v
            Parameter in V direction.
        """
        kv_u = np.array(self.knotvector_u, dtype=float)
        kv_v = np.array(self.knotvector_v, dtype=float)
        nu = len(self._points)
        nv = len(self._points[0])

        # Clamp to domain
        u = float(np.clip(u, kv_u[self._degree_u], kv_u[nu]))
        v = float(np.clip(v, kv_v[self._degree_v], kv_v[nv]))

        cpts = self._get_homo_cpts()
        u_basis = self._eval_basis_u(u)
        v_basis = self._eval_basis_v(v)

        result = np.einsum("i,j,ijk->k", u_basis, v_basis, cpts)
        w = result[3]
        if abs(w) < 1e-30:
            return Point(0.0, 0.0, 0.0)
        return Point(float(result[0] / w), float(result[1] / w), float(result[2] / w))

    def normal_at(self, u: float, v: float) -> Vector:
        """Surface normal at (u, v) via finite differences.

        Parameters
        ----------
        u
            Parameter in U direction.
        v
            Parameter in V direction.
        """
        eps = 1e-7
        du_lo, du_hi = self.domain_u
        dv_lo, dv_hi = self.domain_v

        u0 = max(du_lo, u - eps)
        u1 = min(du_hi, u + eps)
        v0 = max(dv_lo, v - eps)
        v1 = min(dv_hi, v + eps)

        pu0 = self.point_at(u0, v)
        pu1 = self.point_at(u1, v)
        pv0 = self.point_at(u, v0)
        pv1 = self.point_at(u, v1)

        du = Vector(pu1.x - pu0.x, pu1.y - pu0.y, pu1.z - pu0.z)
        dv = Vector(pv1.x - pv0.x, pv1.y - pv0.y, pv1.z - pv0.z)

        normal = du.cross(dv)
        length = (normal.x**2 + normal.y**2 + normal.z**2) ** 0.5
        if length < 1e-14:
            return Vector(0.0, 0.0, 1.0)
        return Vector(normal.x / length, normal.y / length, normal.z / length)

    def frame_at(self, u: float, v: float) -> Frame:
        """Local frame at (u, v).

        Parameters
        ----------
        u
            Parameter in U direction.
        v
            Parameter in V direction.
        """
        eps = 1e-7
        du_lo, du_hi = self.domain_u
        dv_lo, dv_hi = self.domain_v

        pt = self.point_at(u, v)

        u0 = max(du_lo, u - eps)
        u1 = min(du_hi, u + eps)
        pu0 = self.point_at(u0, v)
        pu1 = self.point_at(u1, v)
        du = Vector(pu1.x - pu0.x, pu1.y - pu0.y, pu1.z - pu0.z)
        du_len = (du.x**2 + du.y**2 + du.z**2) ** 0.5

        v0 = max(dv_lo, v - eps)
        v1 = min(dv_hi, v + eps)
        pv0 = self.point_at(u, v0)
        pv1 = self.point_at(u, v1)
        dv = Vector(pv1.x - pv0.x, pv1.y - pv0.y, pv1.z - pv0.z)
        dv_len = (dv.x**2 + dv.y**2 + dv.z**2) ** 0.5

        if du_len < 1e-14:
            xaxis = Vector(1.0, 0.0, 0.0)
        else:
            xaxis = Vector(du.x / du_len, du.y / du_len, du.z / du_len)

        if dv_len < 1e-14:
            yaxis = Vector(0.0, 1.0, 0.0)
        else:
            yaxis = Vector(dv.x / dv_len, dv.y / dv_len, dv.z / dv_len)

        return Frame(pt, xaxis, yaxis)

    def isocurve_u(self, u: float) -> NurbsCurve:
        """Extract a V-direction iso-curve at fixed *u*.

        Parameters
        ----------
        u
            Fixed U parameter.
        """
        kv_u = np.array(self.knotvector_u, dtype=float)
        nu = len(self._points)
        nv = len(self._points[0])
        u = float(np.clip(u, kv_u[self._degree_u], kv_u[nu]))

        u_basis = self._eval_basis_u(u)
        cpts = self._get_homo_cpts()

        # Weighted sum along U for each V index -> (nv, 4)
        v_cpts_h = np.einsum("i,ijk->jk", u_basis, cpts)

        points: list[Point] = []
        weights: list[float] = []
        for j in range(nv):
            w = v_cpts_h[j, 3]
            if abs(w) < 1e-30:
                points.append(Point(0, 0, 0))
                weights.append(0.0)
            else:
                points.append(Point(float(v_cpts_h[j, 0] / w), float(v_cpts_h[j, 1] / w), float(v_cpts_h[j, 2] / w)))
                weights.append(float(w))

        return NurbsCurve.from_parameters(points, weights, list(self._knots_v), list(self._mults_v), self._degree_v)

    def isocurve_v(self, v: float) -> NurbsCurve:
        """Extract a U-direction iso-curve at fixed *v*.

        Parameters
        ----------
        v
            Fixed V parameter.
        """
        kv_v = np.array(self.knotvector_v, dtype=float)
        nu = len(self._points)
        nv = len(self._points[0])
        v = float(np.clip(v, kv_v[self._degree_v], kv_v[nv]))

        v_basis = self._eval_basis_v(v)
        cpts = self._get_homo_cpts()

        # Weighted sum along V for each U index -> (nu, 4)
        u_cpts_h = np.einsum("j,ijk->ik", v_basis, cpts)

        points: list[Point] = []
        weights: list[float] = []
        for i in range(nu):
            w = u_cpts_h[i, 3]
            if abs(w) < 1e-30:
                points.append(Point(0, 0, 0))
                weights.append(0.0)
            else:
                points.append(Point(float(u_cpts_h[i, 0] / w), float(u_cpts_h[i, 1] / w), float(u_cpts_h[i, 2] / w)))
                weights.append(float(w))

        return NurbsCurve.from_parameters(points, weights, list(self._knots_u), list(self._mults_u), self._degree_u)

    def space_u(self, n: int = 10) -> list[float]:
        """Return n+1 uniformly spaced parameters in U domain.

        Parameters
        ----------
        n
            Number of intervals.
        """
        a, b = self.domain_u
        return [a + (b - a) * i / n for i in range(n + 1)]

    def space_v(self, n: int = 10) -> list[float]:
        """Return n+1 uniformly spaced parameters in V domain.

        Parameters
        ----------
        n
            Number of intervals.
        """
        a, b = self.domain_v
        return [a + (b - a) * i / n for i in range(n + 1)]

    # ------------------------------------------------------------------
    # Transforms
    # ------------------------------------------------------------------

    def transform(self, transformation: Transformation) -> None:
        """Transform all control points in-place.

        Parameters
        ----------
        transformation
            The transformation to apply.
        """
        for row in self._points:
            for pt in row:
                pt.transform(transformation)
        self._invalidate_cache()

    def transformed(self, transformation: Transformation) -> NurbsSurface:
        """Return a transformed copy.

        Parameters
        ----------
        transformation
            The transformation to apply.
        """
        s = self.copy()
        s.transform(transformation)
        return s

    def copy(self) -> NurbsSurface:
        """Return a deep copy."""
        return NurbsSurface.from_parameters(
            deepcopy(self._points),
            deepcopy(self._weights),
            list(self._knots_u),
            list(self._knots_v),
            list(self._mults_u),
            list(self._mults_v),
            self._degree_u,
            self._degree_v,
        )

    # ------------------------------------------------------------------
    # Data serialization
    # ------------------------------------------------------------------

    @property
    def __data__(self) -> dict:
        return {
            "points": [[[p.x, p.y, p.z] for p in row] for row in self._points],
            "weights": [list(row) for row in self._weights],
            "knots_u": list(self._knots_u),
            "knots_v": list(self._knots_v),
            "mults_u": list(self._mults_u),
            "mults_v": list(self._mults_v),
            "degree_u": self._degree_u,
            "degree_v": self._degree_v,
        }

    @__data__.setter
    def __data__(self, data: dict) -> None:
        self._points = [[Point(*xyz) for xyz in row] for row in data["points"]]
        self._weights = [list(row) for row in data["weights"]]
        self._knots_u = list(data["knots_u"])
        self._knots_v = list(data["knots_v"])
        self._mults_u = list(data["mults_u"])
        self._mults_v = list(data["mults_v"])
        self._degree_u = data["degree_u"]
        self._degree_v = data["degree_v"]
        self._invalidate_cache()

    @classmethod
    def __from_data__(cls, data: dict) -> NurbsSurface:
        return cls.from_parameters(
            points=[[Point(*xyz) for xyz in row] for row in data["points"]],
            weights=data["weights"],
            knots_u=data["knots_u"],
            knots_v=data["knots_v"],
            mults_u=data["mults_u"],
            mults_v=data["mults_v"],
            degree_u=data["degree_u"],
            degree_v=data["degree_v"],
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _lerp(p0: Point, p1: Point, t: float) -> Point:
    """Linear interpolation between two points."""
    return Point(
        p0.x + (p1.x - p0.x) * t,
        p0.y + (p1.y - p0.y) * t,
        p0.z + (p1.z - p0.z) * t,
    )


def _bilerp(p00: Point, p10: Point, p01: Point, p11: Point, u: float, v: float) -> Point:
    """Bilinear interpolation of four corner points."""
    x = (1 - u) * (1 - v) * p00.x + u * (1 - v) * p10.x + (1 - u) * v * p01.x + u * v * p11.x
    y = (1 - u) * (1 - v) * p00.y + u * (1 - v) * p10.y + (1 - u) * v * p01.y + u * v * p11.y
    z = (1 - u) * (1 - v) * p00.z + u * (1 - v) * p10.z + (1 - u) * v * p01.z + u * v * p11.z
    return Point(x, y, z)
