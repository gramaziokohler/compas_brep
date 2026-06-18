from __future__ import annotations

from compas_brep.edge import BrepEdge
from compas_brep.trim import BrepTrim
from compas_brep.vertex import BrepVertex


class BrepLoop:
    """Pure Python implementation of a Brep loop.

    A loop can store edges directly (legacy) or trims (STEP-inspired).
    When trims are present, edges are derived from them.
    """

    def __init__(self, edges: list[BrepEdge] | None = None, trims: list[BrepTrim] | None = None) -> None:
        self._trims: list[BrepTrim] = list(trims) if trims else []
        # Legacy: store edges directly when no trims are provided
        self._edges: list[BrepEdge] = list(edges) if edges and not trims else []

    @property
    def trims(self) -> list[BrepTrim]:
        """The ordered list of trims (coedges) in this loop."""
        return self._trims

    @property
    def edges(self) -> list[BrepEdge]:
        """The ordered list of edges in this loop.

        If trims are present, returns their underlying edges.
        Otherwise returns the directly-stored edges (legacy path).
        """
        if self._trims:
            return [t.edge for t in self._trims]
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
    def is_valid(self) -> bool:
        n = len(self._trims) if self._trims else len(self._edges)
        return n >= 1  # A single closed curve (circle) is valid

    @property
    def native_loop(self) -> BrepLoop:
        return self

    # =========================================================================
    # Serialization
    # =========================================================================

    @property
    def __data__(self) -> list[dict]:
        return [trim.__data__ for trim in self._trims]

    def __repr__(self) -> str:
        if self._trims:
            return f"BrepLoop({len(self._trims)} trims)"
        return f"BrepLoop({len(self._edges)} edges)"
