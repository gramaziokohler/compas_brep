from __future__ import annotations

import math

from compas.geometry import Circle
from compas.geometry import Ellipse
from compas.geometry import Line
from compas.geometry import Point

from compas_brep.curves import NurbsCurve
from compas_brep.curves import edge_curve_from_data
from compas_brep.curves import edge_curve_to_data
from compas_brep.vertex import BrepVertex


class BrepEdge:
    """A Brep edge defined by start/end vertices and a 3D curve.

    The curve is a ``Line``, a ``Circle``, an ``Ellipse``, or a ``NurbsCurve``.

    An analytic curve (``Circle`` / ``Ellipse``) is an unbounded closed conic, so
    the edge also carries ``domain`` -- the parameter interval it actually runs
    over, in the parameter space :func:`compas_brep.exchange.analytic_curve_point`
    defines. A quarter-circle fillet edge and a full circular seam are the same
    ``Circle`` with different domains. ``Line`` and ``NurbsCurve`` carry their own
    extent, so their domain is ``None``.
    """

    def __init__(
        self,
        start: BrepVertex,
        end: BrepVertex,
        curve: Line | Circle | Ellipse | NurbsCurve | None = None,
        domain: tuple[float, float] | None = None,
    ) -> None:
        self._start = start
        self._end = end
        self._curve: Line | Circle | Ellipse | NurbsCurve = curve or Line(start.point, end.point)
        self._domain = domain

    @property
    def curve(self) -> Line | Circle | Ellipse | NurbsCurve:
        return self._curve

    @curve.setter
    def curve(self, value: Line | Circle | Ellipse | NurbsCurve) -> None:
        self._curve = value

    @property
    def domain(self) -> tuple[float, float] | None:
        """The parameter interval this edge runs over, for an analytic curve."""
        return self._domain

    @domain.setter
    def domain(self, value: tuple[float, float] | None) -> None:
        self._domain = value

    @property
    def first_vertex(self) -> BrepVertex:
        return self._start

    @property
    def last_vertex(self) -> BrepVertex:
        return self._end

    @property
    def vertices(self) -> list[BrepVertex]:
        return [self._start, self._end]

    @property
    def is_line(self) -> bool:
        return isinstance(self.curve, Line)

    @property
    def is_circle(self) -> bool:
        """True for a full circular edge. A partial one is an arc -- see :attr:`is_arc`."""
        from compas_brep.exchange import analytic_curve_is_full_turn

        return isinstance(self._curve, Circle) and (self._domain is None or analytic_curve_is_full_turn(self._domain))

    @property
    def is_arc(self) -> bool:
        """True for an edge running along part of a circle, not the whole of it."""
        return isinstance(self._curve, Circle) and not self.is_circle

    @property
    def is_ellipse(self) -> bool:
        return isinstance(self._curve, Ellipse)

    @property
    def is_hyperbola(self) -> bool:
        return False

    @property
    def is_parabola(self) -> bool:
        return False

    @property
    def is_bezier(self) -> bool:
        return False

    @property
    def is_bspline(self) -> bool:
        return isinstance(self.curve, NurbsCurve)

    @property
    def is_other(self) -> bool:
        return not self.is_line and not self.is_bspline and not self.is_circle and not self.is_arc and not self.is_ellipse

    @property
    def is_valid(self) -> bool:
        return True

    @property
    def length(self) -> float:
        curve = self.curve
        if isinstance(curve, NurbsCurve):
            return curve.length()
        if isinstance(curve, (Circle, Ellipse)):
            return self._analytic_length(curve)
        return curve.length

    def _analytic_length(self, curve: Circle | Ellipse) -> float:
        """Arc length over this edge's domain, not the whole conic.

        Exact for a circle. An ellipse's arc length is an elliptic integral with no
        closed form -- and, unlike a circle's, it is *not* proportional to the
        parameter span -- so it is integrated numerically.
        """
        from compas_brep.exchange import analytic_curve_point

        t0, t1 = self._domain if self._domain is not None else (0.0, 2.0 * math.pi)

        if isinstance(curve, Circle):
            return curve.radius * abs(t1 - t0)

        n = 256
        step = (t1 - t0) / n
        total = 0.0
        previous = analytic_curve_point(curve, t0)
        for i in range(1, n + 1):
            current = analytic_curve_point(curve, t0 + i * step)
            total += previous.distance_to_point(current)
            previous = current
        return total

    @property
    def native_edge(self) -> BrepEdge:
        return self

    def to_line(self) -> Line:
        if self.is_line:
            return Line(Point(*self._start.point), Point(*self._end.point))
        return Line(Point(*self._start.point), Point(*self._end.point))

    # =========================================================================
    # Serialization
    # =========================================================================

    @property
    def __data__(self) -> dict:
        """Serialize this edge to a dict."""
        sp = self._start.point
        ep = self._end.point
        start_xyz = [sp.x, sp.y, sp.z]
        end_xyz = [ep.x, ep.y, ep.z]
        return {
            "start": start_xyz,
            "end": end_xyz,
            "curve": edge_curve_to_data(self.curve, self._domain),
        }

    @classmethod
    def __from_data__(cls, data: dict, start: BrepVertex, end: BrepVertex) -> BrepEdge:
        """Deserialize an edge from a dict.

        Parameters
        ----------
        data
            Serialized edge data.
        start
            The start vertex (from shared vertex pool).
        end
            The end vertex (from shared vertex pool).
        """
        curve, domain = edge_curve_from_data(data["curve"])
        return cls(start, end, curve=curve, domain=domain)

    # =========================================================================
    # Sampling
    # =========================================================================

    def sample_points(self, n: int = 64) -> list[Point]:
        """Sample points along this edge for visualization.

        For NurbsCurve edges, samples at n+1 parameter values (n segments).
        For Line edges, returns just the two endpoints.

        Parameters
        ----------
        n
            Number of segments for curved edges. Defaults to 64.
        """
        curve = self.curve
        if isinstance(curve, NurbsCurve):
            t_start, t_end = curve.domain
            points = []
            for i in range(n + 1):
                t = t_start + (t_end - t_start) * i / n
                points.append(curve.point_at(t))
            return points

        if isinstance(curve, (Circle, Ellipse)):
            from compas_brep.exchange import analytic_curve_point

            t_start, t_end = self._domain if self._domain is not None else (0.0, 2.0 * math.pi)
            return [analytic_curve_point(curve, t_start + (t_end - t_start) * i / n) for i in range(n + 1)]

        sp = self._start.point
        ep = self._end.point
        if (abs(sp.x - ep.x) + abs(sp.y - ep.y) + abs(sp.z - ep.z)) > 1e-9:
            return [sp, ep]
        return []

    def __repr__(self) -> str:
        return f"BrepEdge({self._start.point} -> {self._end.point}, {self.curve_type})"

    @property
    def curve_type(self) -> str:
        """This edge's tag in the exchange format's edge curve tag set."""
        if self.is_line:
            return "line"
        if self.is_circle:
            return "circle"
        if self.is_arc:
            return "arc"
        if self.is_ellipse:
            return "ellipse"
        return "nurbs"
