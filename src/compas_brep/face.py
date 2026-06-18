from __future__ import annotations

from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Polygon
from compas.geometry import Vector
from compas.tolerance import TOL

from compas_brep.edge import BrepEdge
from compas_brep.loop import BrepLoop
from compas_brep.surfaces import NurbsSurface
from compas_brep.surfaces import surface_to_data
from compas_brep.vertex import BrepVertex


class BrepFace:
    """A Brep face defined by a surface and boundary loops.

    The surface can be a Plane (planar face) or a NurbsSurface (curved face).
    The outer loop defines the face boundary; inner loops define holes.
    """

    def __init__(
        self,
        outer_loop: BrepLoop,
        surface: Plane | NurbsSurface | None = None,
        is_reversed: bool = False,
        domain_u: tuple[float, float] | None = None,
        domain_v: tuple[float, float] | None = None,
    ) -> None:
        self._outer_loop = outer_loop
        self._inner_loops: list[BrepLoop] = []
        self._surface: Plane | NurbsSurface = surface or self._compute_plane()
        self._is_reversed = is_reversed
        self._domain_u = domain_u
        self._domain_v = domain_v

    def _compute_plane(self) -> Plane:
        """Compute the face plane from the outer loop vertices."""
        points = [v.point for v in self._outer_loop.vertices]
        return _plane_from_points(points)

    @property
    def surface(self) -> Plane | NurbsSurface:
        return self._surface

    @surface.setter
    def surface(self, value: Plane | NurbsSurface) -> None:
        self._surface = value

    @property
    def domain_u(self) -> tuple[float, float] | None:
        return self._domain_u

    @property
    def domain_v(self) -> tuple[float, float] | None:
        return self._domain_v

    @property
    def is_planar(self) -> bool:
        return isinstance(self.surface, Plane)

    @property
    def is_plane(self) -> bool:
        return self.is_planar

    @property
    def is_nurbs(self) -> bool:
        return isinstance(self.surface, NurbsSurface)

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
    def is_reversed(self) -> bool:
        return self._is_reversed

    @property
    def is_valid(self) -> bool:
        return len(self._outer_loop.vertices) >= 3

    def to_polygon(self) -> Polygon:
        return Polygon([v.point for v in self._outer_loop.vertices])

    def add_loop(self, loop: BrepLoop) -> None:
        self._inner_loops.append(loop)

    # =========================================================================
    # Serialization
    # =========================================================================

    @property
    def __data__(self) -> dict:
        surface_data = surface_to_data(self.surface)

        face_data = {
            "surface": surface_data,
            "loops": [loop.__data__ for loop in self.loops],
            "is_reversed": self._is_reversed,
        }
        if self._domain_u is not None:
            face_data["domain_u"] = list(self._domain_u)
        if self._domain_v is not None:
            face_data["domain_v"] = list(self._domain_v)
        return face_data

    def __repr__(self) -> str:
        surface_type = "plane" if self.is_planar else "nurbs"
        return f"BrepFace({len(self.vertices)} vertices, {surface_type})"


def _plane_from_points(points: list[Point]) -> Plane:
    """Compute plane from polygon vertices using Newell's method."""
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
