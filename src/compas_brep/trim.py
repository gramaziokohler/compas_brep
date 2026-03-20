from __future__ import annotations

from compas_brep.vertex import BrepVertex


class BrepTrim:
    """Pure Python implementation of a Brep trim.

    For the initial planar-face implementation, trims are simplified -
    they correspond directly to edges in 2D parameter space.
    """

    def __init__(self, start_vertex: BrepVertex, end_vertex: BrepVertex):
        self._start = start_vertex
        self._end = end_vertex

    @property
    def curve(self):
        return None  # 2D trim curves not yet implemented

    @property
    def iso_status(self):
        return 0  # NONE

    @property
    def is_reversed(self) -> bool:
        return False

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
