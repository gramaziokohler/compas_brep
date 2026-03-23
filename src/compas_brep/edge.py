from __future__ import annotations

from compas.geometry import Line, Point

from compas_brep.vertex import BrepVertex


class BrepEdge:
    """A Brep edge defined by start/end vertices and a 3D curve.

    The curve can be a Line (straight edge) or a NurbsCurve (curved edge).
    """

    def __init__(self, start: BrepVertex, end: BrepVertex, curve: Line | None = None):
        self._start = start
        self._end = end
        self._curve = curve or Line(start.point, end.point)

    @property
    def curve(self):
        return self._curve

    @curve.setter
    def curve(self, value):
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
        return isinstance(self._curve, Line)

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
        from compas_brep.curves.nurbs import NurbsCurve

        return isinstance(self._curve, NurbsCurve)

    @property
    def is_other(self) -> bool:
        return not self.is_line and not self.is_bspline

    @property
    def is_valid(self) -> bool:
        return True

    @property
    def length(self) -> float:
        return self._curve.length

    @property
    def native_edge(self):
        return self

    def to_line(self) -> Line:
        if self.is_line:
            return Line(Point(*self._start.point), Point(*self._end.point))
        return Line(Point(*self._start.point), Point(*self._end.point))

    def __repr__(self):
        curve_type = "line" if self.is_line else "nurbs"
        return f"BrepEdge({self._start.point} -> {self._end.point}, {curve_type})"
