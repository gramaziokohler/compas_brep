from __future__ import annotations

from compas.geometry import Plane, Point, Polygon

from compas_brep.edge import BrepEdge
from compas_brep.loop import BrepLoop
from compas_brep.surfaces.nurbs import NurbsSurface
from compas_brep.vertex import BrepVertex


class BrepFace:
    """A Brep face defined by a surface and boundary loops.

    The surface can be a Plane (planar face) or a NurbsSurface (curved face).
    The outer loop defines the face boundary; inner loops define holes.
    """

    def __init__(
        self,
        outer_loop: BrepLoop,
        surface: Plane | None = None,
        is_reversed: bool = False,
        domain_u: tuple[float, float] | None = None,
        domain_v: tuple[float, float] | None = None,
    ):
        self._outer_loop = outer_loop
        self._inner_loops: list[BrepLoop] = []
        self._surface = surface or self._compute_plane()
        self._is_reversed = is_reversed
        self._domain_u = domain_u
        self._domain_v = domain_v
        self._native_face = None  # cached OCC face for tessellation; never serialized

    def _compute_plane(self) -> Plane:
        """Compute the face plane from the outer loop vertices."""
        points = [v.point for v in self._outer_loop.vertices]
        return _plane_from_points(points)

    @property
    def surface(self):
        return self._surface

    @surface.setter
    def surface(self, value):
        self._surface = value

    @property
    def domain_u(self) -> tuple[float, float] | None:
        return self._domain_u

    @property
    def domain_v(self) -> tuple[float, float] | None:
        return self._domain_v

    @property
    def is_planar(self) -> bool:
        return isinstance(self._surface, Plane)

    @property
    def is_plane(self) -> bool:
        return self.is_planar

    @property
    def is_nurbs(self) -> bool:
        return isinstance(self._surface, NurbsSurface)

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

    @property
    def native_face(self):
        return self

    def to_polygon(self) -> Polygon:
        return Polygon([v.point for v in self._outer_loop.vertices])

    def add_loop(self, loop: BrepLoop):
        self._inner_loops.append(loop)

    def tessellate(self, n: int = 16):
        """Tessellate this face into triangles via the backend (OCC or Rhino).

        Requires a cached ``_native_face`` — set by the backend when the
        Brep is created or reconstructed.  Returns ``([], [])`` when no
        native face is available.

        Parameters
        ----------
        n : int
            Angular deflection control for OCC tessellation (higher = finer).

        Returns
        -------
        tuple[list[list[float]], list[list[int]]]
            Vertices and triangle faces (winding consistent with outward normals).
        """
        if self._native_face is not None:
            verts, faces = self._tessellate_occ(n)
            if verts is not None:
                return verts, faces

        return [], []

    def _tessellate_occ(self, n: int = 16):
        """Tessellate using OCC's BRepMesh — correctly handles trim curves and holes.

        Returns (vertices, faces) or (None, None) if OCC is unavailable or fails.
        """
        import math

        try:
            from OCP.BRep import BRep_Tool
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.gp import gp_Pnt
            from OCP.TopLoc import TopLoc_Location
        except ImportError:
            return None, None

        try:
            # Angular deflection controls how many segments approximate curved edges.
            # pi / (n * 4) gives ~8n segments per full circle.
            ang_def = math.pi / max(n * 4, 16)
            BRepMesh_IncrementalMesh(self._native_face, 0.05, True, ang_def).Perform()

            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(self._native_face, loc)
            if tri is None or tri.NbTriangles() == 0:
                return None, None

            trsf = loc.Transformation() if not loc.IsIdentity() else None

            vertices = []
            for i in range(1, tri.NbNodes() + 1):
                node = tri.Node(i)
                if trsf is not None:
                    pnt = gp_Pnt(node.X(), node.Y(), node.Z())
                    pnt.Transform(trsf)
                    vertices.append([pnt.X(), pnt.Y(), pnt.Z()])
                else:
                    vertices.append([node.X(), node.Y(), node.Z()])

            faces = []
            for i in range(1, tri.NbTriangles() + 1):
                n1, n2, n3 = tri.Triangle(i).Get()
                if self._is_reversed:
                    faces.append([n1 - 1, n3 - 1, n2 - 1])
                else:
                    faces.append([n1 - 1, n2 - 1, n3 - 1])

            return vertices, faces

        except Exception:
            return None, None

    # =========================================================================
    # Serialization
    # =========================================================================

    @property
    def __data__(self) -> dict:
        surface = self._surface
        if isinstance(surface, NurbsSurface):
            surface_data = {"type": "nurbs", "data": surface.__data__}
        else:
            surface_data = {
                "type": "plane",
                "data": {
                    "point": [surface.point.x, surface.point.y, surface.point.z],
                    "normal": [surface.normal.x, surface.normal.y, surface.normal.z],
                },
            }

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

    def __repr__(self):
        surface_type = "plane" if self.is_planar else "nurbs"
        return f"BrepFace({len(self.vertices)} vertices, {surface_type})"


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
