from __future__ import annotations

from typing import TYPE_CHECKING

from compas.geometry import Point

if TYPE_CHECKING:
    from compas_brep.edge import BrepEdge

from compas_brep.vertex import BrepVertex


class BrepTrim:
    """A coedge: a directed usage of a BrepEdge within a BrepLoop on a BrepFace.

    Inspired by STEP's ORIENTED_EDGE / PCURVE model. A trim wraps a shared
    BrepEdge with:
    - ``is_reversed``: whether this usage traverses the edge backward
    - ``curve_2d``: a NurbsCurve in the face surface's UV parameter space (pcurve)

    The pcurve allows direct UV-space tessellation without 3D→UV inversion.
    The 3D curve and vertices are accessed via the underlying edge.
    """

    def __init__(
        self,
        edge: BrepEdge,
        is_reversed: bool = False,
        curve_2d=None,
    ):
        self._edge = edge
        self._is_reversed = is_reversed
        self._curve_2d = curve_2d  # NurbsCurve in UV space (pcurve), or None

    @property
    def edge(self) -> BrepEdge:
        """The underlying shared BrepEdge."""
        return self._edge

    @property
    def curve(self):
        """The 2D parametric curve in the face's UV space (pcurve)."""
        return self._curve_2d

    @curve.setter
    def curve(self, value):
        self._curve_2d = value

    @property
    def curve_2d(self):
        """Alias for the 2D parametric curve (pcurve)."""
        return self._curve_2d

    @curve_2d.setter
    def curve_2d(self, value):
        self._curve_2d = value

    @property
    def curve_3d(self):
        """The 3D curve from the underlying edge."""
        return self._edge.curve

    @property
    def iso_status(self):
        return 0  # NONE

    @property
    def is_reversed(self) -> bool:
        """Whether this trim traverses the underlying edge backward."""
        return self._is_reversed

    @property
    def start_vertex(self) -> BrepVertex:
        """Start vertex in the trim's traversal direction."""
        if self._is_reversed:
            return self._edge.last_vertex
        return self._edge.first_vertex

    @property
    def end_vertex(self) -> BrepVertex:
        """End vertex in the trim's traversal direction."""
        if self._is_reversed:
            return self._edge.first_vertex
        return self._edge.last_vertex

    @property
    def vertices(self) -> list[BrepVertex]:
        return [self.start_vertex, self.end_vertex]

    @property
    def native_trim(self):
        return self

    # =========================================================================
    # Sampling
    # =========================================================================

    def sample_points(self, surface, n: int = 64) -> list[Point]:
        """Sample points along this trim for visualization.

        When a pcurve is available, samples via pcurve → surface evaluation
        so the resulting polyline lies exactly on the tessellated surface mesh.
        Falls back to the 3D edge curve when no pcurve is present.

        Parameters
        ----------
        surface : Plane or NurbsSurface
            The parent face's surface (needed for pcurve → 3D evaluation).
        n : int, optional
            Number of segments. Defaults to 64.

        Returns
        -------
        list[Point]
        """
        if self._curve_2d is not None and hasattr(surface, "point_at"):
            t_start, t_end = self._curve_2d.domain
            if self._is_reversed:
                t_start, t_end = t_end, t_start
            points = []
            for i in range(n + 1):
                t = t_start + (t_end - t_start) * i / n
                uv = self._curve_2d.point_at(t)
                pt = surface.point_at(uv.x, uv.y)
                points.append(pt)
            return points

        return self._edge.sample_points(n=n)

    # =========================================================================
    # Serialization
    # =========================================================================

    @property
    def __data__(self) -> dict:
        data = {
            "edge": self._edge.__data__,
            "is_reversed": self._is_reversed,
        }
        curve_2d = self.curve_2d
        if curve_2d is not None:
            data["pcurve"] = curve_2d.__data__
        return data

    def __repr__(self):
        rev = " reversed" if self._is_reversed else ""
        pcurve = " +pcurve" if self._curve_2d else ""
        return f"BrepTrim({self.start_vertex.point} -> {self.end_vertex.point}{rev}{pcurve})"
