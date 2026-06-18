from __future__ import annotations

from compas.geometry import Line
from compas.geometry import Point

from compas_brep.curves import NurbsCurve
from compas_brep.vertex import BrepVertex


class BrepEdge:
    """A Brep edge defined by start/end vertices and a 3D curve.

    The curve can be a Line (straight edge) or a NurbsCurve (curved edge).
    """

    def __init__(self, start: BrepVertex, end: BrepVertex, curve: Line | NurbsCurve | None = None) -> None:
        self._start = start
        self._end = end
        self._curve: Line | NurbsCurve = curve or Line(start.point, end.point)

    @property
    def curve(self) -> Line | NurbsCurve:
        return self._curve

    @curve.setter
    def curve(self, value: Line | NurbsCurve) -> None:
        self._curve = value

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
        return False

    @property
    def is_ellipse(self) -> bool:
        return False

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
        return not self.is_line and not self.is_bspline

    @property
    def is_valid(self) -> bool:
        return True

    @property
    def length(self) -> float:
        curve = self.curve
        if isinstance(curve, NurbsCurve):
            return curve.length()
        return curve.length

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
        curve = self.curve
        if isinstance(curve, NurbsCurve):
            curve_data = {"type": "nurbs", "data": curve.__data__}
        else:
            curve_data = {"type": "line", "data": {"start": start_xyz, "end": end_xyz}}
        return {"start": start_xyz, "end": end_xyz, "curve": curve_data}

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
        curve_info = data["curve"]
        if curve_info["type"] == "nurbs":
            curve = NurbsCurve.__from_data__(curve_info["data"])
        else:
            curve = Line(start.point, end.point)
        return cls(start, end, curve=curve)

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

        sp = self._start.point
        ep = self._end.point
        if (abs(sp.x - ep.x) + abs(sp.y - ep.y) + abs(sp.z - ep.z)) > 1e-9:
            return [sp, ep]
        return []

    def __repr__(self) -> str:
        curve_type = "line" if self.is_line else "nurbs"
        return f"BrepEdge({self._start.point} -> {self._end.point}, {curve_type})"
