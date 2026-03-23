from __future__ import annotations

from compas.geometry import Plane, Point, Polygon

from compas_brep.edge import BrepEdge
from compas_brep.loop import BrepLoop
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
        from compas_brep.surfaces.nurbs import NurbsSurface

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
        """Tessellate this face into triangles with outward-pointing normals.

        Parameters
        ----------
        n : int
            Resolution for NURBS surface tessellation (UV grid density) and
            angular deflection control for OCC tessellation.

        Returns
        -------
        tuple[list[list[float]], list[list[int]]]
            Vertices and triangle faces (winding consistent with outward normals).
        """
        # Use OCC's own tessellation when a native face is cached.
        # It correctly handles trim curves, holes, and complex NURBS topology.
        if self._native_face is not None:
            verts, faces = self._tessellate_occ(n)
            if verts is not None:
                return verts, faces

        if self.is_planar:
            return self._tessellate_planar(n=n)

        # NURBS face: UV grid gives ∂S/∂u × ∂S/∂v normal.
        # For is_reversed=True, the shell uses the opposite orientation,
        # so flip triangle winding to ensure outward normals.
        verts, faces = self._tessellate_nurbs(n)
        if self._is_reversed and faces:
            faces = [[f[0], f[2], f[1]] for f in faces]
        return verts, faces

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

    def _tessellate_planar(self, n: int = 16):
        """Fan triangulation for a planar polygon.

        For degenerate loops (< 3 unique vertices from simple vertex list),
        falls back to sampling edge curves to get boundary points.
        """
        from compas_brep.curves.nurbs import NurbsCurve

        points = [v.point for v in self._outer_loop.vertices]

        # Deduplicate consecutive identical points
        unique = []
        for p in points:
            if not unique or (abs(p.x - unique[-1].x) + abs(p.y - unique[-1].y) + abs(p.z - unique[-1].z)) > 1e-9:
                unique.append(p)
        dx = abs(unique[-1].x - unique[0].x)
        dy = abs(unique[-1].y - unique[0].y)
        dz = abs(unique[-1].z - unique[0].z)
        if len(unique) >= 2 and dx + dy + dz < 1e-9:
            unique.pop()
        points = unique

        if len(points) < 3:
            # Degenerate vertex loop — sample edge curves for boundary points
            sampled = []
            for edge in self._outer_loop.edges:
                if isinstance(edge.curve, NurbsCurve):
                    t_start, t_end = edge.curve.domain
                    for i in range(n):
                        t = t_start + (t_end - t_start) * i / n
                        pt = edge.curve.point_at(t)
                        sampled.append(pt)
                else:
                    sp = edge.first_vertex.point
                    ep = edge.last_vertex.point
                    if (abs(sp.x - ep.x) + abs(sp.y - ep.y) + abs(sp.z - ep.z)) > 1e-9:
                        sampled.append(sp)
            # For reversed faces, reverse point order to get outward-pointing normals
            if self._is_reversed:
                sampled = sampled[::-1]
            points = sampled

        if len(points) < 3:
            return [], []

        vertices = [[p.x, p.y, p.z] for p in points]
        faces = []
        for i in range(1, len(points) - 1):
            faces.append([0, i, i + 1])
        return vertices, faces

    def _tessellate_nurbs(self, n: int = 16):
        """UV grid tessellation for a NURBS surface face."""
        surface = self._surface
        # Always use the surface's own parametric domain for evaluation
        du = surface.domain_u
        dv = surface.domain_v

        u_vals = [du[0] + (du[1] - du[0]) * i / n for i in range(n + 1)]
        v_vals = [dv[0] + (dv[1] - dv[0]) * i / n for i in range(n + 1)]

        vertices = []
        for u in u_vals:
            for v in v_vals:
                pt = surface.point_at(u, v)
                vertices.append([pt.x, pt.y, pt.z])

        faces = []
        nv = n + 1
        for i in range(n):
            for j in range(n):
                a = i * nv + j
                b = a + 1
                c = a + nv + 1
                d = a + nv
                # Reversed winding: UV grid gives ∂S/∂v × ∂S/∂u (inward),
                # so swap to get ∂S/∂u × ∂S/∂v (outward surface normal).
                faces.append([a, c, b])
                faces.append([a, d, c])

        return vertices, faces

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
