from __future__ import annotations

from compas_brep.edge import BrepEdge
from compas_brep.trim import BrepTrim
from compas_brep.vertex import BrepVertex


class LoopType:
    """Constants describing the role of a loop within its face.

    Mirrors the loop types of ``Rhino.Geometry.BrepLoopType`` for the two cases
    compas_brep distinguishes.
    """

    UNKNOWN = 0
    OUTER = 1
    INNER = 2


class BrepLoop:
    """Pure Python implementation of a Brep loop.

    A loop can store edges directly (legacy) or trims (STEP-inspired).
    When trims are present, edges are derived from them.
    """

    def __init__(
        self,
        edges: list[BrepEdge] | None = None,
        trims: list[BrepTrim] | None = None,
        is_outer: bool = True,
    ) -> None:
        self._trims: list[BrepTrim] = list(trims) if trims else []
        # Legacy: store edges directly when no trims are provided
        self._edges: list[BrepEdge] = list(edges) if edges and not trims else []
        # Set by the owning BrepFace; a loop which isn't part of a face is its own boundary.
        self._is_outer = is_outer

    @property
    def trims(self) -> list[BrepTrim]:
        """The ordered list of trims (coedges) in this loop."""
        return self._trims

    @property
    def edges(self) -> list[BrepEdge]:
        """The ordered list of edges in this loop.

        If trims are present, returns their underlying edges. Singular trims
        contribute nothing — they have no edge. Otherwise returns the
        directly-stored edges (legacy path).
        """
        if self._trims:
            return [t.edge for t in self._trims if t.edge is not None]
        return self._edges

    @property
    def vertices(self) -> list[BrepVertex]:
        verts = []
        if self._trims:
            for trim in self._trims:
                if not verts or verts[-1] is not trim.start_vertex:
                    verts.append(trim.start_vertex)
                verts.append(trim.end_vertex)
        else:
            for edge in self._edges:
                if not verts or verts[-1] is not edge.first_vertex:
                    verts.append(edge.first_vertex)
                verts.append(edge.last_vertex)
        # Remove duplicate closing vertex
        if verts and verts[0] is verts[-1]:
            verts.pop()
        return verts

    @property
    def is_outer(self) -> bool:
        """True if this loop is the outer boundary of its face."""
        return self._is_outer

    @is_outer.setter
    def is_outer(self, value: bool) -> None:
        self._is_outer = bool(value)

    @property
    def is_inner(self) -> bool:
        """True if this loop is an inner loop (a hole) of its face."""
        return not self._is_outer

    @property
    def loop_type(self) -> int:
        """One of the :class:`LoopType` constants."""
        return LoopType.OUTER if self._is_outer else LoopType.INNER

    @property
    def is_valid(self) -> bool:
        n = len(self._trims) if self._trims else len(self._edges)
        return n >= 1  # A single closed curve (circle) is valid

    @property
    def native_loop(self) -> BrepLoop:
        return self

    def __repr__(self) -> str:
        if self._trims:
            return f"BrepLoop({len(self._trims)} trims)"
        return f"BrepLoop({len(self._edges)} edges)"
