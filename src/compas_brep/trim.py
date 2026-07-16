from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from compas.geometry import Point

if TYPE_CHECKING:
    from compas_brep.edge import BrepEdge

from compas_brep.curves import NurbsCurve
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
        edge: BrepEdge | None,
        is_reversed: bool = False,
        curve_2d: NurbsCurve | None = None,
        vertex: BrepVertex | None = None,
    ) -> None:
        self._edge = edge
        self._is_reversed = is_reversed
        self._curve_2d: NurbsCurve | None = curve_2d
        self._vertex = vertex

    @property
    def edge(self) -> BrepEdge | None:
        """The underlying shared BrepEdge, or None for a singular trim."""
        return self._edge

    @property
    def vertex(self) -> BrepVertex | None:
        """The vertex a singular trim collapses to. None for an ordinary trim."""
        return self._vertex

    @property
    def is_singular(self) -> bool:
        """Whether this trim has no edge and collapses to a single vertex.

        A sphere's poles are the canonical case: the trim spans the full u-range
        of the surface at v = min or v = max, but every point on it is the same
        point in 3D.
        """
        return self._edge is None

    @property
    def curve(self) -> NurbsCurve | None:
        """The 2D parametric curve in the face's UV space (pcurve)."""
        return self._curve_2d

    @curve.setter
    def curve(self, value: NurbsCurve | None) -> None:
        self._curve_2d = value

    @property
    def curve_2d(self) -> NurbsCurve | None:
        """Alias for the 2D parametric curve (pcurve)."""
        return self._curve_2d

    @curve_2d.setter
    def curve_2d(self, value: NurbsCurve | None) -> None:
        self._curve_2d = value

    @property
    def curve_3d(self) -> Any:
        """The 3D curve from the underlying edge. None for a singular trim."""
        if self._edge is None:
            return None
        return self._edge.curve

    @property
    def iso_status(self) -> int:
        return 0  # NONE

    @property
    def is_reversed(self) -> bool:
        """Whether this trim traverses the underlying edge backward."""
        return self._is_reversed

    @property
    def start_vertex(self) -> BrepVertex:
        """Start vertex in the trim's traversal direction."""
        if self._edge is None:
            return self._vertex
        if self._is_reversed:
            return self._edge.last_vertex
        return self._edge.first_vertex

    @property
    def end_vertex(self) -> BrepVertex:
        """End vertex in the trim's traversal direction."""
        if self._edge is None:
            return self._vertex
        if self._is_reversed:
            return self._edge.first_vertex
        return self._edge.last_vertex

    @property
    def vertices(self) -> list[BrepVertex]:
        return [self.start_vertex, self.end_vertex]

    @property
    def native_trim(self) -> BrepTrim:
        return self

    # =========================================================================
    # Sampling
    # =========================================================================

    def sample_points(self, surface: Any, n: int = 64) -> list[Point]:
        """Sample points along this trim for visualization.

        When a pcurve is available, samples via pcurve → surface evaluation
        so the resulting polyline lies exactly on the tessellated surface mesh.
        Falls back to the 3D edge curve when no pcurve is present.

        Parameters
        ----------
        surface
            The parent face's surface (needed for pcurve → 3D evaluation).
        n
            Number of segments. Defaults to 64.
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

        if self._edge is None:
            # A singular trim is a single point in 3D; without a pcurve to walk
            # there is nothing to sample but the vertex it collapses to.
            return [self._vertex.point] * (n + 1)

        return self._edge.sample_points(n=n)

    # =========================================================================
    # Serialization
    # =========================================================================

    @property
    def __data__(self) -> dict:
        data = {
            "edge": self._edge.__data__ if self._edge is not None else None,
            "is_reversed": self._is_reversed,
        }
        curve_2d = self.curve_2d
        if curve_2d is not None:
            data["pcurve"] = curve_2d.__data__
        return data

    def __repr__(self) -> str:
        rev = " reversed" if self._is_reversed else ""
        pcurve = " +pcurve" if self._curve_2d else ""
        return f"BrepTrim({self.start_vertex.point} -> {self.end_vertex.point}{rev}{pcurve})"
