"""Pure-Python rational NURBS curve built on scipy.interpolate.BSpline."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from compas.data import Data
from compas.geometry import Frame, Line, Point, Polyline, Vector
from scipy.interpolate import BSpline, make_interp_spline
from scipy.optimize import minimize_scalar

if TYPE_CHECKING:
    from compas.geometry import Circle, Ellipse, Transformation


def _knotvector_from_knots_mults(knots: list[float], mults: list[int]) -> list[float]:
    """Expand unique knots + multiplicities into a full knot vector."""
    kv: list[float] = []
    for k, m in zip(knots, mults):
        kv.extend([k] * m)
    return kv


def _knots_mults_from_knotvector(knotvector: list[float]) -> tuple[list[float], list[int]]:
    """Compress a full knot vector into unique knots + multiplicities."""
    if not knotvector:
        return [], []
    knots: list[float] = [knotvector[0]]
    mults: list[int] = [1]
    for v in knotvector[1:]:
        if abs(v - knots[-1]) < 1e-14:
            mults[-1] += 1
        else:
            knots.append(v)
            mults.append(1)
    return knots, mults


class NurbsCurve(Data):
    """A rational NURBS curve.

    Parameters
    ----------
    name : str, optional
        The name of the curve.
    """

    def __init__(self, name: str | None = None):
        super().__init__(name=name)
        self._points: list[Point] = []
        self._weights: list[float] = []
        self._knots: list[float] = []
        self._mults: list[int] = []
        self._degree: int = 0
        self._bspline: BSpline | None = None

    # --------------------------------------------------------------------------
    # Properties
    # --------------------------------------------------------------------------

    @property
    def points(self) -> list[Point]:
        """Control points."""
        return self._points

    @property
    def weights(self) -> list[float]:
        """Weights."""
        return self._weights

    @property
    def knots(self) -> list[float]:
        """Unique knot values."""
        return self._knots

    @property
    def mults(self) -> list[int]:
        """Knot multiplicities."""
        return self._mults

    @property
    def knotvector(self) -> list[float]:
        """Full knot vector (knots repeated by multiplicities)."""
        return _knotvector_from_knots_mults(self._knots, self._mults)

    @property
    def degree(self) -> int:
        """Degree of the curve."""
        return self._degree

    @property
    def domain(self) -> tuple[float, float]:
        """Parameter domain of the curve."""
        kv = self.knotvector
        d = self._degree
        return (kv[d], kv[-(d + 1)])

    @property
    def is_closed(self) -> bool:
        """True if the first and last control points coincide."""
        if len(self._points) < 2:
            return False
        p0, p1 = self._points[0], self._points[-1]
        return math.sqrt((p0.x - p1.x) ** 2 + (p0.y - p1.y) ** 2 + (p0.z - p1.z) ** 2) < 1e-10

    @property
    def is_periodic(self) -> bool:
        """Always False (simplified)."""
        return False

    def length(self) -> float:
        """Approximate arc length by dense sampling."""
        n = 1000
        a, b = self.domain
        ts = np.linspace(a, b, n + 1)
        pts = self._evaluate_many(ts)
        diffs = np.diff(pts, axis=0)
        return float(np.sum(np.sqrt(np.sum(diffs**2, axis=1))))

    # --------------------------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------------------------

    def _invalidate_cache(self) -> None:
        self._bspline = None

    def _build_bspline(self) -> BSpline:
        """Build a scipy BSpline in homogeneous coordinates (4D)."""
        if self._bspline is not None:
            return self._bspline
        kv = np.array(self.knotvector, dtype=float)
        n = len(self._points)
        cw = np.empty((n, 4), dtype=float)
        for i, (pt, w) in enumerate(zip(self._points, self._weights)):
            cw[i] = [pt.x * w, pt.y * w, pt.z * w, w]
        self._bspline = BSpline(kv, cw, self._degree, extrapolate=False)
        return self._bspline

    def _evaluate_one(self, t: float) -> np.ndarray:
        """Evaluate at a single parameter, return (x, y, z) array."""
        spl = self._build_bspline()
        # Clamp t to domain to avoid NaN from extrapolate=False
        a, b = self.domain
        t = float(np.clip(t, a, b))
        hw = spl(t)
        w = hw[3]
        return hw[:3] / w

    def _evaluate_many(self, ts: np.ndarray) -> np.ndarray:
        """Evaluate at an array of parameters, return (N, 3) array."""
        spl = self._build_bspline()
        a, b = self.domain
        ts = np.clip(ts, a, b)
        hw = spl(ts)  # (N, 4)
        w = hw[:, 3:]
        return hw[:, :3] / w

    # --------------------------------------------------------------------------
    # Constructors
    # --------------------------------------------------------------------------

    @classmethod
    def from_parameters(
        cls,
        points: list[Point],
        weights: list[float],
        knots: list[float],
        mults: list[int] | None = None,
        degree: int = 3,
        multiplicities: list[int] | None = None,
    ) -> NurbsCurve:
        """Create a NURBS curve from explicit parameters.

        Parameters
        ----------
        points : list[Point]
            Control points.
        weights : list[float]
            Weights per control point.
        knots : list[float]
            Unique knot values.
        mults : list[int]
            Multiplicities per knot.
        degree : int
            Curve degree.

        Returns
        -------
        NurbsCurve

        """
        if mults is None:
            mults = multiplicities
        if mults is None:
            raise ValueError("Either 'mults' or 'multiplicities' must be provided.")
        curve = cls()
        curve._points = [Point(p.x, p.y, p.z) for p in points]
        curve._weights = list(weights)
        curve._knots = list(knots)
        curve._mults = list(mults)
        curve._degree = degree
        return curve

    @classmethod
    def from_points(cls, points: list[Point], degree: int = 3) -> NurbsCurve:
        """Create a NURBS curve with given control points and clamped uniform knot vector.

        Parameters
        ----------
        points : list[Point]
            Control points.
        degree : int
            Curve degree.

        Returns
        -------
        NurbsCurve

        """
        n = len(points)
        if n <= degree:
            raise ValueError(f"Need at least {degree + 1} control points for degree {degree}, got {n}.")
        # Clamped uniform knot vector: (degree+1) zeros, uniform interior, (degree+1) ones
        num_interior = n - degree - 1
        kv: list[float] = [0.0] * (degree + 1)
        for i in range(1, num_interior + 1):
            kv.append(i / (num_interior + 1))
        kv.extend([1.0] * (degree + 1))
        knots, mults = _knots_mults_from_knotvector(kv)
        weights = [1.0] * n
        return cls.from_parameters(points, weights, knots, mults, degree)

    @classmethod
    def from_interpolation(cls, points: list[Point], degree: int = 3) -> NurbsCurve:
        """Create a NURBS curve that interpolates through given points.

        Uses chord-length parameterization and scipy's make_interp_spline.

        Parameters
        ----------
        points : list[Point]
            Points to interpolate.
        degree : int
            Curve degree.

        Returns
        -------
        NurbsCurve

        """
        pts = np.array([[p.x, p.y, p.z] for p in points], dtype=float)
        n = len(points)
        # Clamp degree to number of points - 1
        degree = min(degree, n - 1)
        # Chord-length parameterization
        dists = np.sqrt(np.sum(np.diff(pts, axis=0) ** 2, axis=1))
        total = np.sum(dists)
        if total < 1e-14:
            raise ValueError("All points coincide.")
        t = np.zeros(n)
        t[1:] = np.cumsum(dists) / total

        spl = make_interp_spline(t, pts, k=degree)
        ctrl = [Point(float(c[0]), float(c[1]), float(c[2])) for c in spl.c]
        kv = spl.t.tolist()
        knots, mults = _knots_mults_from_knotvector(kv)
        weights = [1.0] * len(ctrl)
        return cls.from_parameters(ctrl, weights, knots, mults, degree)

    @classmethod
    def from_line(cls, line: Line) -> NurbsCurve:
        """Create a degree-1 NURBS curve from a line.

        Parameters
        ----------
        line : Line
            The line.

        Returns
        -------
        NurbsCurve

        """
        pts = [Point(line.start.x, line.start.y, line.start.z), Point(line.end.x, line.end.y, line.end.z)]
        return cls.from_parameters(pts, [1.0, 1.0], [0.0, 1.0], [2, 2], degree=1)

    @classmethod
    def from_circle(cls, circle: Circle) -> NurbsCurve:
        """Create a rational NURBS circle (degree 2, 9 control points).

        Parameters
        ----------
        circle : Circle
            The circle.

        Returns
        -------
        NurbsCurve

        """
        return cls._conic_from_radii(circle.radius, circle.radius, circle.frame)

    @classmethod
    def from_ellipse(cls, ellipse: Ellipse) -> NurbsCurve:
        """Create a rational NURBS ellipse (degree 2, 9 control points).

        Parameters
        ----------
        ellipse : Ellipse
            The ellipse.

        Returns
        -------
        NurbsCurve

        """
        return cls._conic_from_radii(ellipse.major, ellipse.minor, ellipse.frame)

    @classmethod
    def _conic_from_radii(cls, rx: float, ry: float, frame: Frame) -> NurbsCurve:
        """Build a degree-2 rational NURBS closed curve (circle or ellipse)."""
        w = math.sqrt(2.0) / 2.0
        # 9 control points in local XY plane (unit conic scaled by rx, ry)
        local_pts = [
            (rx, 0.0),
            (rx, ry),
            (0.0, ry),
            (-rx, ry),
            (-rx, 0.0),
            (-rx, -ry),
            (0.0, -ry),
            (rx, -ry),
            (rx, 0.0),
        ]
        weights = [1.0, w, 1.0, w, 1.0, w, 1.0, w, 1.0]
        # Transform to world via frame
        ox = np.array([frame.point.x, frame.point.y, frame.point.z])
        ex = np.array([frame.xaxis.x, frame.xaxis.y, frame.xaxis.z])
        ey = np.array([frame.yaxis.x, frame.yaxis.y, frame.yaxis.z])
        pts: list[Point] = []
        for lx, ly in local_pts:
            p = ox + lx * ex + ly * ey
            pts.append(Point(float(p[0]), float(p[1]), float(p[2])))
        knots = [0.0, 0.25, 0.5, 0.75, 1.0]
        mults = [3, 2, 2, 2, 3]
        return cls.from_parameters(pts, weights, knots, mults, degree=2)

    # --------------------------------------------------------------------------
    # Evaluation
    # --------------------------------------------------------------------------

    def point_at(self, t: float) -> Point:
        """Evaluate the curve at parameter *t*.

        Parameters
        ----------
        t : float
            Parameter value.

        Returns
        -------
        Point

        """
        xyz = self._evaluate_one(t)
        return Point(float(xyz[0]), float(xyz[1]), float(xyz[2]))

    def tangent_at(self, t: float) -> Vector:
        """Tangent vector at parameter *t* (unnormalized).

        Uses finite differences on the rational curve.

        Parameters
        ----------
        t : float
            Parameter value.

        Returns
        -------
        Vector

        """
        a, b = self.domain
        h = (b - a) * 1e-7
        t0 = max(a, t - h)
        t1 = min(b, t + h)
        p0 = self._evaluate_one(t0)
        p1 = self._evaluate_one(t1)
        d = (p1 - p0) / (t1 - t0)
        return Vector(float(d[0]), float(d[1]), float(d[2]))

    def frame_at(self, t: float) -> Frame:
        """Frame at parameter *t*.

        Parameters
        ----------
        t : float
            Parameter value.

        Returns
        -------
        Frame

        """
        pt = self.point_at(t)
        tan = self.tangent_at(t)
        tlen = tan.length
        if tlen < 1e-14:
            return Frame(pt, Vector(1, 0, 0), Vector(0, 1, 0))
        xaxis = tan.scaled(1.0 / tlen)
        # Construct a reasonable yaxis
        up = Vector(0, 0, 1) if abs(xaxis.dot(Vector(0, 0, 1))) < 0.99 else Vector(1, 0, 0)
        yaxis = xaxis.cross(up)
        ylen = yaxis.length
        if ylen < 1e-14:
            return Frame(pt, xaxis, Vector(0, 1, 0))
        yaxis = yaxis.scaled(1.0 / ylen)
        return Frame(pt, xaxis, yaxis)

    def to_polyline(self, n: int = 100) -> Polyline:
        """Sample the curve into a polyline.

        Parameters
        ----------
        n : int
            Number of segments.

        Returns
        -------
        Polyline

        """
        a, b = self.domain
        ts = np.linspace(a, b, n + 1)
        pts = self._evaluate_many(ts)
        return Polyline([Point(float(p[0]), float(p[1]), float(p[2])) for p in pts])

    def to_linesegments(self, n: int = 100) -> list[Line]:
        """Sample the curve into line segments.

        Parameters
        ----------
        n : int
            Number of segments.

        Returns
        -------
        list[Line]

        """
        poly = self.to_polyline(n)
        lines: list[Line] = []
        pts = poly.points
        for i in range(len(pts) - 1):
            lines.append(Line(pts[i], pts[i + 1]))
        return lines

    def closest_point(self, point: Point, return_parameter: bool = False) -> Point | tuple[Point, float]:
        """Find the closest point on the curve to *point*.

        Parameters
        ----------
        point : Point
            The query point.
        return_parameter : bool
            If True, also return the parameter.

        Returns
        -------
        Point or tuple[Point, float]

        """
        a, b = self.domain
        # Coarse sampling
        n_samples = 200
        ts = np.linspace(a, b, n_samples)
        pts = self._evaluate_many(ts)
        target = np.array([point.x, point.y, point.z])
        dists = np.sum((pts - target) ** 2, axis=1)
        best_idx = int(np.argmin(dists))
        # Refine around best
        t_lo = ts[max(0, best_idx - 1)]
        t_hi = ts[min(n_samples - 1, best_idx + 1)]

        def dist_sq(t: float) -> float:
            p = self._evaluate_one(t)
            return float(np.sum((p - target) ** 2))

        result = minimize_scalar(dist_sq, bounds=(t_lo, t_hi), method="bounded")
        t_best = float(result.x)
        pt = self.point_at(t_best)
        if return_parameter:
            return pt, t_best
        return pt

    def closest_parameters_curve(
        self, other: NurbsCurve, return_distance: bool = False
    ) -> tuple[float, float] | tuple[tuple[float, float], float]:
        """Find the parameters on this and another curve at closest approach.

        Parameters
        ----------
        other : NurbsCurve
            The other curve.
        return_distance : bool
            If True, also return the distance.

        Returns
        -------
        tuple[float, float] or tuple[tuple[float, float], float]

        """
        from scipy.optimize import minimize

        a1, b1 = self.domain
        a2, b2 = other.domain

        # Coarse grid search
        n_samples = 50
        ts1 = np.linspace(a1, b1, n_samples)
        ts2 = np.linspace(a2, b2, n_samples)
        pts1 = self._evaluate_many(ts1)
        pts2 = other._evaluate_many(ts2)
        # Pairwise distances
        best_d = float("inf")
        best_i, best_j = 0, 0
        for i in range(n_samples):
            diffs = pts2 - pts1[i]
            dists = np.sum(diffs**2, axis=1)
            j = int(np.argmin(dists))
            if dists[j] < best_d:
                best_d = dists[j]
                best_i, best_j = i, j

        def dist_sq(params: np.ndarray) -> float:
            t1 = float(np.clip(params[0], a1, b1))
            t2 = float(np.clip(params[1], a2, b2))
            p1 = self._evaluate_one(t1)
            p2 = other._evaluate_one(t2)
            return float(np.sum((p1 - p2) ** 2))

        result = minimize(dist_sq, [ts1[best_i], ts2[best_j]], method="Nelder-Mead")
        t1_best = float(np.clip(result.x[0], a1, b1))
        t2_best = float(np.clip(result.x[1], a2, b2))
        params = (t1_best, t2_best)
        if return_distance:
            d = math.sqrt(dist_sq(np.array([t1_best, t2_best])))
            return params, d
        return params

    def closest_points_curve(
        self, other: NurbsCurve, return_distance: bool = False
    ) -> tuple[Point, Point] | tuple[tuple[Point, Point], float]:
        """Find the closest points between this and another curve.

        Parameters
        ----------
        other : NurbsCurve
            The other curve.
        return_distance : bool
            If True, also return the distance.

        Returns
        -------
        tuple[Point, Point] or tuple[tuple[Point, Point], float]

        """
        result = self.closest_parameters_curve(other, return_distance=True)
        (t1, t2), d = result
        p1 = self.point_at(t1)
        p2 = other.point_at(t2)
        if return_distance:
            return (p1, p2), d
        return (p1, p2)

    def divide(self, n: int, return_points: bool = False) -> list[float] | tuple[list[float], list[Point]]:
        """Divide the curve into *n* equal-parameter segments.

        Parameters
        ----------
        n : int
            Number of segments.
        return_points : bool
            If True, also return the points.

        Returns
        -------
        list[float] or tuple[list[float], list[Point]]

        """
        a, b = self.domain
        ts = [a + i * (b - a) / n for i in range(n + 1)]
        if return_points:
            pts = [self.point_at(t) for t in ts]
            return ts, pts
        return ts

    def segment(self, u: float, v: float) -> None:
        """Trim this curve in-place to the sub-curve between *u* and *v*.

        Parameters
        ----------
        u : float
            Start parameter.
        v : float
            End parameter.

        """
        sub = self.segmented(u, v)
        self._points = sub._points
        self._weights = sub._weights
        self._knots = sub._knots
        self._mults = sub._mults
        self._degree = sub._degree
        self._invalidate_cache()

    def segmented(self, u: float, v: float) -> NurbsCurve:
        """Extract a sub-curve between parameters *u* and *v*.

        Uses dense re-interpolation.

        Parameters
        ----------
        u : float
            Start parameter.
        v : float
            End parameter.

        Returns
        -------
        NurbsCurve

        """
        n = max(50, self._degree * 20)
        ts = np.linspace(u, v, n + 1)
        pts = self._evaluate_many(ts)
        points = [Point(float(p[0]), float(p[1]), float(p[2])) for p in pts]
        return NurbsCurve.from_interpolation(points, degree=self._degree)

    def joined(self, other: NurbsCurve) -> NurbsCurve:
        """Join this curve with *other* end-to-end via re-interpolation.

        Parameters
        ----------
        other : NurbsCurve
            The curve to join.

        Returns
        -------
        NurbsCurve

        """
        n = 50
        pts1 = self.to_polyline(n).points
        pts2 = other.to_polyline(n).points
        # Skip first point of second curve to avoid duplicate at join
        all_pts = list(pts1) + list(pts2[1:])
        degree = min(self._degree, other._degree)
        return NurbsCurve.from_interpolation(all_pts, degree=degree)

    # --------------------------------------------------------------------------
    # Transformations
    # --------------------------------------------------------------------------

    def transform(self, transformation: Transformation) -> None:
        """Transform all control points in-place.

        Parameters
        ----------
        transformation : Transformation
            The transformation to apply.

        """
        for pt in self._points:
            pt.transform(transformation)
        self._invalidate_cache()

    def transformed(self, transformation: Transformation) -> NurbsCurve:
        """Return a transformed copy.

        Parameters
        ----------
        transformation : Transformation
            The transformation to apply.

        Returns
        -------
        NurbsCurve

        """
        c = self.copy()
        c.transform(transformation)
        return c

    def copy(self) -> NurbsCurve:
        """Return a deep copy.

        Returns
        -------
        NurbsCurve

        """
        curve = NurbsCurve()
        curve._points = [Point(p.x, p.y, p.z) for p in self._points]
        curve._weights = list(self._weights)
        curve._knots = list(self._knots)
        curve._mults = list(self._mults)
        curve._degree = self._degree
        return curve

    # --------------------------------------------------------------------------
    # Data serialization
    # --------------------------------------------------------------------------

    @property
    def __data__(self) -> dict:
        return {
            "points": [[p.x, p.y, p.z] for p in self._points],
            "weights": list(self._weights),
            "knots": list(self._knots),
            "mults": list(self._mults),
            "degree": self._degree,
        }

    @__data__.setter
    def __data__(self, data: dict) -> None:
        self._points = [Point(*xyz) for xyz in data["points"]]
        self._weights = list(data["weights"])
        self._knots = list(data["knots"])
        self._mults = list(data["mults"])
        self._degree = data["degree"]
        self._invalidate_cache()

    @classmethod
    def __from_data__(cls, data: dict) -> NurbsCurve:
        return cls.from_parameters(
            points=[Point(*xyz) for xyz in data["points"]],
            weights=data["weights"],
            knots=data["knots"],
            mults=data["mults"],
            degree=data["degree"],
        )
