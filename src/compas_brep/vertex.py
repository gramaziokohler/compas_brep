from __future__ import annotations

from compas.geometry import Point


class BrepVertex:
    """Pure Python implementation of a Brep vertex."""

    def __init__(self, point: Point):
        self._point = Point(*point)

    @property
    def point(self) -> Point:
        return self._point

    @property
    def native_vertex(self):
        return self

    def __repr__(self):
        return f"BrepVertex({self._point})"
