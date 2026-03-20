from __future__ import annotations

from compas.geometry import Plane, Point, Polygon

from compas_brep.edge import BrepEdge
from compas_brep.loop import BrepLoop
from compas_brep.vertex import BrepVertex


class BrepFace:
    """Pure Python implementation of a Brep face.

    A face is defined by a surface and one or more boundary loops.
    For the initial implementation, all faces are planar.
    """

    def __init__(self, outer_loop: BrepLoop, surface: Plane | None = None, is_reversed: bool = False):
        self._outer_loop = outer_loop
        self._inner_loops: list[BrepLoop] = []
        self._surface = surface or self._compute_plane()
        self._is_reversed = is_reversed

    def _compute_plane(self) -> Plane:
        """Compute the face plane from the outer loop vertices."""
        points = [v.point for v in self._outer_loop.vertices]
        return _plane_from_points(points)

    @property
    def surface(self):
        return self._surface

    @property
    def loops(self) -> list[BrepLoop]:
        return [self._outer_loop, *self._inner_loops]

    @property
    def outer_loop(self) -> BrepLoop:
        return self._outer_loop

    @property
    def edges(self) -> list[BrepEdge]:
        all_edges = []
        for loop in self.loops:
            all_edges.extend(loop.edges)
        return all_edges

    @property
    def vertices(self) -> list[BrepVertex]:
        all_verts = []
        seen = set()
        for loop in self.loops:
            for v in loop.vertices:
                vid = id(v)
                if vid not in seen:
                    seen.add(vid)
                    all_verts.append(v)
        return all_verts

    @property
    def area(self) -> float:
        return self.to_polygon().area

    @property
    def centroid(self) -> Point:
        return self.to_polygon().centroid

    @property
    def is_plane(self) -> bool:
        return True

    @property
    def is_reversed(self) -> bool:
        return self._is_reversed

    @property
    def is_valid(self) -> bool:
        return len(self._outer_loop.vertices) >= 3

    @property
    def native_face(self):
        return self

    def to_polygon(self) -> Polygon:
        return Polygon([v.point for v in self._outer_loop.vertices])

    def add_loop(self, loop: BrepLoop):
        self._inner_loops.append(loop)

    def __repr__(self):
        return f"BrepFace({len(self.vertices)} vertices)"


def _plane_from_points(points: list[Point]) -> Plane:
    """Compute plane from polygon vertices using Newell's method."""
    from compas.geometry import Vector
    from compas.tolerance import TOL

    n = len(points)
    nx, ny, nz = 0.0, 0.0, 0.0
    for i in range(n):
        p0 = points[i]
        p1 = points[(i + 1) % n]
        nx += (p0.y - p1.y) * (p0.z + p1.z)
        ny += (p0.z - p1.z) * (p0.x + p1.x)
        nz += (p0.x - p1.x) * (p0.y + p1.y)
    normal = Vector(nx, ny, nz)
    length = normal.length
    if length < TOL.absolute:
        normal = Vector(0, 0, 1)
    else:
        normal = normal / length
    return Plane(points[0], normal)
