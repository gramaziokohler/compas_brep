from __future__ import annotations

from compas_brep.vertex import BrepVertex


class BrepTrim:
    """A Brep trim representing a portion of an edge on a face boundary.

    A trim has optional 2D and 3D curve representations:
    - curve_2d: parametric curve in the face's UV space
    - curve_3d: 3D curve in world space (Line or NurbsCurve)
    """

    def __init__(
        self,
        start_vertex: BrepVertex,
        end_vertex: BrepVertex,
        curve_2d=None,
        curve_3d=None,
        is_reversed: bool = False,
    ):
        self._start = start_vertex
        self._end = end_vertex
        self._curve_2d = curve_2d  # NurbsCurve in UV space, or None
        self._curve_3d = curve_3d  # Line | NurbsCurve in 3D, or None
        self._is_reversed = is_reversed

    @property
    def curve(self):
        """The 2D parametric curve in the face's UV space."""
        return self._curve_2d

    @curve.setter
    def curve(self, value):
        self._curve_2d = value

    @property
    def curve_3d(self):
        """The 3D curve in world space."""
        return self._curve_3d

    @curve_3d.setter
    def curve_3d(self, value):
        self._curve_3d = value

    @property
    def iso_status(self):
        return 0  # NONE

    @property
    def is_reversed(self) -> bool:
        return self._is_reversed

    @property
    def start_vertex(self) -> BrepVertex:
        return self._start

    @property
    def end_vertex(self) -> BrepVertex:
        return self._end

    @property
    def vertices(self) -> list[BrepVertex]:
        return [self._start, self._end]

    @property
    def native_trim(self):
        return self
