from __future__ import annotations

from compas.geometry import Line, Point

from compas_brep.vertex import BrepVertex


class BrepEdge:
    """Pure Python implementation of a Brep edge."""

    def __init__(self, start: BrepVertex, end: BrepVertex):
        self._start = start
        self._end = end
        self._line = Line(start.point, end.point)

    @property
    def curve(self):
        return self._line

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
        return True

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
        return False

    @property
    def is_other(self) -> bool:
        return False

    @property
    def is_valid(self) -> bool:
        return True

    @property
    def length(self) -> float:
        return self._line.length

    @property
    def native_edge(self):
        return self

    def to_line(self) -> Line:
        return Line(
            Point(*self._start.point),
            Point(*self._end.point),
        )

    def __repr__(self):
        return f"BrepEdge({self._start.point} -> {self._end.point})"
