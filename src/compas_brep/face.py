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
        """Tessellation for a planar face, handling holes via Delaunay + filtering.

        Samples outer and inner loop edges to get boundary polygons, projects
        to 2D on the face plane, triangulates with scipy Delaunay, and filters
        out triangles inside holes. Falls back to fan triangulation when there
        are no inner loops or scipy is unavailable.
        """
        # Sample the outer boundary
        outer_3d = _sample_loop_3d(self._outer_loop, n)
        if len(outer_3d) < 3:
            return [], []

        # Ensure the boundary winding matches the face's outward normal.
        # Edge curves may have been stored with their natural parameterization,
        # which doesn't always match the face orientation.
        outer_3d = _orient_boundary(outer_3d, self._surface, self._is_reversed)

        # Simple case: no holes → fan triangulation
        if not self._inner_loops:
            return _fan_triangulate(outer_3d)

        # Has holes — need Delaunay + filtering
        # Sample all inner loops (holes)
        holes_3d = []
        for inner_loop in self._inner_loops:
            hole = _sample_loop_3d(inner_loop, n)
            if len(hole) >= 3:
                holes_3d.append(hole)

        # Project everything to 2D on the face plane
        all_3d = list(outer_3d)
        for hole in holes_3d:
            all_3d.extend(hole)

        try:
            import numpy as np
            from scipy.spatial import Delaunay

            pts = np.array(all_3d)
            origin = pts.mean(axis=0)
            centered = pts - origin
            _, s, vt = np.linalg.svd(centered, full_matrices=False)
            if s[1] < 1e-12:
                return _fan_triangulate(outer_3d)
            u_axis = vt[0]
            v_axis = vt[1]
            pts_2d = np.column_stack([centered @ u_axis, centered @ v_axis])

            tri = Delaunay(pts_2d)
            triangles = tri.simplices.tolist()
        except Exception:
            return _fan_triangulate(outer_3d)

        # Project boundaries to 2D for inside/outside tests
        outer_2d = [[float(pts_2d[i, 0]), float(pts_2d[i, 1])] for i in range(len(outer_3d))]
        holes_2d = []
        offset = len(outer_3d)
        for hole in holes_3d:
            hole_2d = [[float(pts_2d[offset + i, 0]), float(pts_2d[offset + i, 1])] for i in range(len(hole))]
            holes_2d.append(hole_2d)
            offset += len(hole)

        # Filter: keep triangles inside outer boundary and outside all holes
        filtered = []
        for t in triangles:
            cx = float((pts_2d[t[0], 0] + pts_2d[t[1], 0] + pts_2d[t[2], 0]) / 3)
            cy = float((pts_2d[t[0], 1] + pts_2d[t[1], 1] + pts_2d[t[2], 1]) / 3)
            centroid = [cx, cy]
            if not _point_in_polygon_2d(centroid, outer_2d):
                continue
            in_hole = False
            for hole_2d in holes_2d:
                if _point_in_polygon_2d(centroid, hole_2d):
                    in_hole = True
                    break
            if not in_hole:
                filtered.append(t)

        if not filtered:
            return _fan_triangulate(outer_3d)

        vertices = [[p[0], p[1], p[2]] for p in all_3d]
        return vertices, filtered

    def _tessellate_nurbs(self, n: int = 16):
        """Trimmed NURBS tessellation using pcurves or edge curves.

        When pcurves (2D UV trim curves) are available from trims, they are
        sampled directly in UV space — no 3D→UV inversion needed. This is
        the STEP-inspired approach and is both faster and more robust.

        Falls back to the Newton-tracking approach when pcurves are absent
        (e.g. for legacy v2 data without trims).
        """
        # Try pcurve-based approach first
        boundary_uv = _sample_loop_pcurves(self._outer_loop, n)
        if boundary_uv is not None and len(boundary_uv) >= 3:
            return self._tessellate_nurbs_from_uv(boundary_uv, n)

        # Fallback: 3D edge sampling + Newton UV inversion
        return self._tessellate_nurbs_from_edges(n)

    def _tessellate_nurbs_from_uv(self, boundary_uv, n: int = 16):
        """Tessellate using pre-computed UV boundary (from pcurves).

        1. Add interior UV grid points inside the trim polygon
        2. Triangulate in UV with scipy Delaunay, filter outside-boundary triangles
        3. Handle holes via inner loop pcurves
        4. Evaluate surface at all UV points to get 3D mesh vertices
        """
        surface = self._surface

        # Compute UV bounding box of the boundary for grid placement
        u_coords = [p[0] for p in boundary_uv]
        v_coords = [p[1] for p in boundary_uv]
        u_lo, u_hi = min(u_coords), max(u_coords)
        v_lo, v_hi = min(v_coords), max(v_coords)
        # Shrink slightly to avoid boundary artifacts
        u_margin = (u_hi - u_lo) * 0.02
        v_margin = (v_hi - v_lo) * 0.02
        u_lo, u_hi = u_lo + u_margin, u_hi - u_margin
        v_lo, v_hi = v_lo + v_margin, v_hi - v_margin

        all_uv = list(boundary_uv)
        for i in range(1, n):
            u = u_lo + (u_hi - u_lo) * i / n
            for j in range(1, n):
                v = v_lo + (v_hi - v_lo) * j / n
                if _point_in_polygon_2d([u, v], boundary_uv):
                    all_uv.append([u, v])

        try:
            import numpy as np
            from scipy.spatial import Delaunay

            pts_uv = np.array(all_uv)
            tri = Delaunay(pts_uv)
            triangles = tri.simplices.tolist()
        except Exception:
            return self._tessellate_nurbs_untrimmed(n)

        # Filter triangles outside outer boundary and ensure CCW winding in UV
        # CCW in UV → triangle normal aligns with ∂S/∂u × ∂S/∂v (surface outward normal)
        filtered = []
        for t in triangles:
            cu = (all_uv[t[0]][0] + all_uv[t[1]][0] + all_uv[t[2]][0]) / 3
            cv = (all_uv[t[0]][1] + all_uv[t[1]][1] + all_uv[t[2]][1]) / 3
            if not _point_in_polygon_2d([cu, cv], boundary_uv):
                continue
            # Ensure CCW winding in UV space (positive signed area)
            u0, v0 = all_uv[t[0]]
            u1, v1 = all_uv[t[1]]
            u2, v2 = all_uv[t[2]]
            cross = (u1 - u0) * (v2 - v0) - (u2 - u0) * (v1 - v0)
            if cross < 0:
                filtered.append([t[0], t[2], t[1]])  # Flip to CCW
            else:
                filtered.append(t)

        # Filter inner loops (holes) — use pcurves if available
        for inner_loop in self._inner_loops:
            hole_uv = _sample_loop_pcurves(inner_loop, n)
            if hole_uv is None:
                hole_uv = _sample_loop_to_uv(inner_loop, surface, n)
            if hole_uv and len(hole_uv) >= 3:
                filtered = [
                    t
                    for t in filtered
                    if not _point_in_polygon_2d(
                        [
                            (all_uv[t[0]][0] + all_uv[t[1]][0] + all_uv[t[2]][0]) / 3,
                            (all_uv[t[0]][1] + all_uv[t[1]][1] + all_uv[t[2]][1]) / 3,
                        ],
                        hole_uv,
                    )
                ]

        if not filtered:
            return self._tessellate_nurbs_untrimmed(n)

        # Evaluate surface at all UV points for 3D mesh
        vertices = []
        for uv in all_uv:
            uw, vw = surface._wrap_param(uv[0], uv[1])
            pt = surface.point_at(uw, vw)
            vertices.append([pt.x, pt.y, pt.z])

        return vertices, filtered

    def _tessellate_nurbs_from_edges(self, n: int = 16):
        """Fallback NURBS tessellation via 3D edge sampling + Newton UV inversion.

        Used when pcurves are not available (legacy v2 data).
        """
        from compas_brep.curves.nurbs import NurbsCurve

        surface = self._surface

        # Sample boundary edges to get dense 3D points
        boundary_3d = []
        for edge in self._outer_loop.edges:
            curve = edge.curve
            if isinstance(curve, NurbsCurve):
                t0, t1 = curve.domain
                for i in range(n):
                    t = t0 + (t1 - t0) * i / n
                    pt = curve.point_at(t)
                    boundary_3d.append([pt.x, pt.y, pt.z])
            else:
                sp = edge.first_vertex.point
                ep = edge.last_vertex.point
                dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5
                if dist > 1e-9:
                    n_line = max(2, n // 4)
                    for i in range(n_line):
                        t = i / n_line
                        boundary_3d.append(
                            [
                                sp.x + t * (ep.x - sp.x),
                                sp.y + t * (ep.y - sp.y),
                                sp.z + t * (ep.z - sp.z),
                            ]
                        )

        if len(boundary_3d) < 3:
            return self._tessellate_nurbs_untrimmed(n)

        # Invert 3D boundary points to UV space
        boundary_uv = _invert_boundary_to_uv(boundary_3d, surface)
        if boundary_uv is None or len(boundary_uv) < 3:
            return self._tessellate_nurbs_untrimmed(n)

        return self._tessellate_nurbs_from_uv(boundary_uv, n)

    def _tessellate_nurbs_untrimmed(self, n: int = 16):
        """Fallback: full UV grid tessellation without trim curves."""
        surface = self._surface
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
                faces.append([a, c, b])
                faces.append([a, d, c])

        return vertices, faces

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


def _sample_loop_pcurves(loop, n):
    """Sample a BrepLoop's trims' pcurves (2D UV curves) to get a UV boundary.

    Returns a list of [u, v] pairs, or None if any trim lacks a pcurve.
    The pcurve is sampled in the trim's traversal direction (respecting
    ``is_reversed`` on the trim).
    """
    if not loop.trims:
        return None

    uv_points = []
    for trim in loop.trims:
        pcurve = trim.curve_2d
        if pcurve is None:
            return None  # Can't use pcurve path if any trim lacks one

        t0, t1 = pcurve.domain
        if trim.is_reversed:
            # Sample backward: the pcurve direction matches the edge's
            # canonical direction, so for reversed trims we sample in reverse
            for i in range(n):
                t = t1 - (t1 - t0) * i / n
                pt = pcurve.point_at(t)
                uv_points.append([pt.x, pt.y])  # x=u, y=v, z=0
        else:
            for i in range(n):
                t = t0 + (t1 - t0) * i / n
                pt = pcurve.point_at(t)
                uv_points.append([pt.x, pt.y])

    return uv_points if len(uv_points) >= 3 else None


def _orient_boundary(boundary_3d, surface, is_reversed):
    """Ensure the boundary winding produces the face's outward normal.

    For a planar face, the outward normal is the plane normal (or its opposite
    if ``is_reversed`` is True). The boundary's Newell normal is compared to
    this expected direction and reversed if they disagree.

    For non-planar faces, returns the boundary unchanged.
    """
    if not isinstance(surface, Plane) or len(boundary_3d) < 3:
        return boundary_3d

    # Expected outward normal
    nx, ny, nz = surface.normal.x, surface.normal.y, surface.normal.z
    if is_reversed:
        nx, ny, nz = -nx, -ny, -nz

    # Compute Newell normal of the sampled boundary
    m = len(boundary_3d)
    bnx, bny, bnz = 0.0, 0.0, 0.0
    for i in range(m):
        p0 = boundary_3d[i]
        p1 = boundary_3d[(i + 1) % m]
        bnx += (p0[1] - p1[1]) * (p0[2] + p1[2])
        bny += (p0[2] - p1[2]) * (p0[0] + p1[0])
        bnz += (p0[0] - p1[0]) * (p0[1] + p1[1])

    # Dot product: if negative, winding is opposite to expected
    dot = bnx * nx + bny * ny + bnz * nz
    if dot < 0:
        boundary_3d = boundary_3d[::-1]

    return boundary_3d


def _sample_loop_3d(loop, n):
    """Sample a BrepLoop's edges to dense 3D point coordinates.

    When trims are present, respects the trim direction (is_reversed)
    to ensure correct boundary winding.
    """
    from compas_brep.curves.nurbs import NurbsCurve

    pts = []

    if loop.trims:
        for trim in loop.trims:
            curve = trim.edge.curve
            reversed_dir = trim.is_reversed
            if isinstance(curve, NurbsCurve):
                t0, t1 = curve.domain
                for i in range(n):
                    if reversed_dir:
                        t = t1 - (t1 - t0) * i / n
                    else:
                        t = t0 + (t1 - t0) * i / n
                    pt = curve.point_at(t)
                    pts.append([pt.x, pt.y, pt.z])
            else:
                # Line edge: use trim direction
                sp = trim.start_vertex.point
                ep = trim.end_vertex.point
                dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5
                if dist > 1e-9:
                    n_line = max(2, n // 4)
                    for i in range(n_line):
                        t = i / n_line
                        pts.append(
                            [
                                sp.x + t * (ep.x - sp.x),
                                sp.y + t * (ep.y - sp.y),
                                sp.z + t * (ep.z - sp.z),
                            ]
                        )
                else:
                    pts.append([sp.x, sp.y, sp.z])
    else:
        # Legacy path: edges without trims
        for edge in loop.edges:
            curve = edge.curve
            if isinstance(curve, NurbsCurve):
                t0, t1 = curve.domain
                for i in range(n):
                    t = t0 + (t1 - t0) * i / n
                    pt = curve.point_at(t)
                    pts.append([pt.x, pt.y, pt.z])
            else:
                sp = edge.first_vertex.point
                ep = edge.last_vertex.point
                dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5
                if dist > 1e-9:
                    n_line = max(2, n // 4)
                    for i in range(n_line):
                        t = i / n_line
                        pts.append(
                            [
                                sp.x + t * (ep.x - sp.x),
                                sp.y + t * (ep.y - sp.y),
                                sp.z + t * (ep.z - sp.z),
                            ]
                        )
                else:
                    pts.append([sp.x, sp.y, sp.z])
    return pts


def _invert_boundary_to_uv(boundary_3d, surface):
    """Invert 3D boundary points to UV parameters on a NURBS surface.

    Uses a tracking approach: the first point is located via a global grid
    search (``closest_parameters``), then each subsequent point is found by
    taking Newton steps from the previous UV. Parameters accumulate freely
    (may go beyond the domain bounds) to maintain path continuity across
    periodic seams — the ``uv_step`` method handles wrapping internally for
    surface evaluation while preserving the unwrapped path.

    Returns a list of [u, v] pairs, or None if inversion fails.
    """
    if not boundary_3d:
        return None

    # Global search for the first point (within domain)
    u, v = surface.closest_parameters(boundary_3d[0])
    for _ in range(3):
        u, v = surface.uv_step(u, v, boundary_3d[0])
    uv_points = [[u, v]]

    # Track incrementally — parameters accumulate freely for continuity
    for p in boundary_3d[1:]:
        for _ in range(3):
            u, v = surface.uv_step(u, v, p)
        uv_points.append([u, v])

    return uv_points


def _sample_loop_to_uv(loop, surface, n):
    """Sample a BrepLoop's edges to 3D points and invert to UV space."""
    from compas_brep.curves.nurbs import NurbsCurve

    pts_3d = []
    for edge in loop.edges:
        curve = edge.curve
        if isinstance(curve, NurbsCurve):
            t0, t1 = curve.domain
            for i in range(n):
                t = t0 + (t1 - t0) * i / n
                pt = curve.point_at(t)
                pts_3d.append([pt.x, pt.y, pt.z])
        else:
            sp = edge.first_vertex.point
            ep = edge.last_vertex.point
            dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5
            if dist > 1e-9:
                n_line = max(2, n // 4)
                for i in range(n_line):
                    t = i / n_line
                    pts_3d.append(
                        [
                            sp.x + t * (ep.x - sp.x),
                            sp.y + t * (ep.y - sp.y),
                            sp.z + t * (ep.z - sp.z),
                        ]
                    )

    if len(pts_3d) < 3:
        return None
    return _invert_boundary_to_uv(pts_3d, surface)


def _point_in_polygon_2d(point, polygon):
    """Ray-casting point-in-polygon test in 2D.

    Parameters
    ----------
    point : list[float]
        [x, y] coordinates.
    polygon : list[list[float]]
        List of [x, y] vertices forming a closed polygon.

    Returns
    -------
    bool
    """
    x, y = point[0], point[1]
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _fan_triangulate(points_3d):
    """Simple fan triangulation of a 3D polygon.

    Returns (vertices, faces) in the standard tessellation format.
    """
    if len(points_3d) < 3:
        return [], []
    vertices = [[p[0], p[1], p[2]] for p in points_3d]
    faces = [[0, i, i + 1] for i in range(1, len(points_3d) - 1)]
    return vertices, faces


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
