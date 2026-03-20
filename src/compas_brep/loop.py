from __future__ import annotations

from compas_brep.edge import BrepEdge
from compas_brep.vertex import BrepVertex


class BrepLoop:
    """Pure Python implementation of a Brep loop."""

    def __init__(self, edges: list[BrepEdge]):
        self._edges = list(edges)

    @property
    def edges(self) -> list[BrepEdge]:
        return self._edges

    @property
    def vertices(self) -> list[BrepVertex]:
        verts = []
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
        return len(self._edges) >= 3

    @property
    def native_loop(self):
        return self

    def __repr__(self):
        return f"BrepLoop({len(self._edges)} edges)"
