"""Pure Python Brep implementation based on the COMPAS framework.

Uses BSP-tree based CSG for boolean operations and planar face representation
for the initial implementation.
"""

from __future__ import annotations

import math

from compas.data import Data
from compas.datastructures import Mesh
from compas.geometry import Box, Cylinder, Frame, Plane, Point, Polygon, Polyline, Sphere, Vector

from compas_brep.csg import CSGPolygon, csg_intersect, csg_subtract, csg_union
from compas_brep.edge import BrepEdge
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.vertex import BrepVertex


class Brep(Data):
    """Pure Python Brep implementation.

    Uses planar polygonal faces and BSP-tree CSG for boolean operations.
    Provides the same interface as ``compas.geometry.Brep``.
    """

    def __init__(self, name=None):
        super().__init__(name=name)
        self._vertices: list[BrepVertex] = []
        self._edges: list[BrepEdge] = []
        self._loops: list[BrepLoop] = []
        self._faces: list[BrepFace] = []
        self._frame: Frame = Frame.worldXY()
        self._csg_cache: list[CSGPolygon] | None = None

    # =========================================================================
    # Constructors
    # =========================================================================

    @classmethod
    def from_box(cls, box: Box) -> Brep:
        """Create a Brep from a COMPAS Box."""
        brep = cls()
        brep._build_from_box(box)
        return brep

    @classmethod
    def from_polygons(cls, polygons: list[Polygon]) -> Brep:
        """Create a Brep from a list of COMPAS Polygons."""
        brep = cls()
        brep._build_from_polygons(polygons)
        return brep

    @classmethod
    def from_csg_polygons(cls, csg_polygons: list[CSGPolygon]) -> Brep:
        """Create a Brep from CSG polygon results.

        Merges coplanar adjacent faces to produce clean topology.
        """
        brep = cls()
        polygons = [Polygon(p.vertices) for p in csg_polygons]
        polygons = _merge_coplanar_polygons(polygons)
        brep._build_from_polygons(polygons)
        return brep

    @classmethod
    def from_mesh(cls, mesh: Mesh) -> Brep:
        """Create a Brep from a COMPAS Mesh."""
        vertices, faces = mesh.to_vertices_and_faces()
        polygons = []
        for face in faces:
            pts = [Point(*vertices[i]) for i in face]
            if len(pts) >= 3:
                polygons.append(Polygon(pts))
        return cls.from_polygons(polygons)

    @classmethod
    def from_cylinder(cls, cylinder: Cylinder, n: int = 32) -> Brep:
        """Create a Brep from a COMPAS Cylinder (approximated as an N-sided prism)."""
        frame = cylinder.frame
        radius = cylinder.radius
        height = cylinder.height

        # Generate circle points in local XY of the cylinder frame
        angles = [2 * math.pi * i / n for i in range(n)]
        half_h = height / 2.0

        bottom_pts = []
        top_pts = []
        for a in angles:
            lx = radius * math.cos(a)
            ly = radius * math.sin(a)
            # Transform to world via cylinder frame
            bottom = Point(
                frame.point.x + lx * frame.xaxis.x + ly * frame.yaxis.x - half_h * frame.zaxis.x,
                frame.point.y + lx * frame.xaxis.y + ly * frame.yaxis.y - half_h * frame.zaxis.y,
                frame.point.z + lx * frame.xaxis.z + ly * frame.yaxis.z - half_h * frame.zaxis.z,
            )
            top = Point(
                frame.point.x + lx * frame.xaxis.x + ly * frame.yaxis.x + half_h * frame.zaxis.x,
                frame.point.y + lx * frame.xaxis.y + ly * frame.yaxis.y + half_h * frame.zaxis.y,
                frame.point.z + lx * frame.xaxis.z + ly * frame.yaxis.z + half_h * frame.zaxis.z,
            )
            bottom_pts.append(bottom)
            top_pts.append(top)

        polygons = []
        # Bottom face (reversed winding for outward normal pointing down)
        polygons.append(Polygon(list(reversed(bottom_pts))))
        # Top face
        polygons.append(Polygon(list(top_pts)))
        # Side faces
        for i in range(n):
            j = (i + 1) % n
            polygons.append(Polygon([bottom_pts[i], bottom_pts[j], top_pts[j], top_pts[i]]))

        return cls.from_polygons(polygons)

    @classmethod
    def from_sphere(cls, sphere: Sphere, u: int = 32, v: int = 16) -> Brep:
        """Create a Brep from a COMPAS Sphere (approximated as a UV-sphere)."""
        center = sphere.frame.point
        radius = sphere.radius

        # Generate grid of points
        # v_steps latitude rings from south pole to north pole
        points_grid = []  # [v_index][u_index]
        for vi in range(v + 1):
            lat = -math.pi / 2 + math.pi * vi / v
            ring = []
            for ui in range(u):
                lon = 2 * math.pi * ui / u
                x = center.x + radius * math.cos(lat) * math.cos(lon)
                y = center.y + radius * math.cos(lat) * math.sin(lon)
                z = center.z + radius * math.sin(lat)
                ring.append(Point(x, y, z))
            points_grid.append(ring)

        polygons = []
        # South pole triangle fan (vi=0 is south pole)
        for ui in range(u):
            ui_next = (ui + 1) % u
            polygons.append(Polygon([points_grid[0][ui], points_grid[1][ui_next], points_grid[1][ui]]))

        # Quad strips in between
        for vi in range(1, v - 1):
            for ui in range(u):
                ui_next = (ui + 1) % u
                polygons.append(
                    Polygon(
                        [
                            points_grid[vi][ui],
                            points_grid[vi][ui_next],
                            points_grid[vi + 1][ui_next],
                            points_grid[vi + 1][ui],
                        ]
                    )
                )

        # North pole triangle fan (vi=v is north pole)
        for ui in range(u):
            ui_next = (ui + 1) % u
            polygons.append(Polygon([points_grid[v][ui], points_grid[v - 1][ui], points_grid[v - 1][ui_next]]))

        return cls.from_polygons(polygons)

    @classmethod
    def from_torus(cls, torus, u: int = 32, v: int = 16) -> Brep:
        """Create a Brep from a COMPAS Torus (approximated as a UV mesh).

        Parameters
        ----------
        torus : Torus
            The torus.
        u : int, optional
            Number of divisions around the main ring.
        v : int, optional
            Number of divisions around the tube.
        """
        frame = torus.frame
        R = torus.radius_axis
        r = torus.radius_pipe

        polygons = []
        for ui in range(u):
            theta0 = 2 * math.pi * ui / u
            theta1 = 2 * math.pi * (ui + 1) / u
            for vi in range(v):
                phi0 = 2 * math.pi * vi / v
                phi1 = 2 * math.pi * (vi + 1) / v

                def _torus_pt(theta, phi):
                    x = (R + r * math.cos(phi)) * math.cos(theta)
                    y = (R + r * math.cos(phi)) * math.sin(theta)
                    z = r * math.sin(phi)
                    # Transform to world via frame
                    return Point(
                        frame.point.x + x * frame.xaxis.x + y * frame.yaxis.x + z * frame.zaxis.x,
                        frame.point.y + x * frame.xaxis.y + y * frame.yaxis.y + z * frame.zaxis.y,
                        frame.point.z + x * frame.xaxis.z + y * frame.yaxis.z + z * frame.zaxis.z,
                    )

                p0 = _torus_pt(theta0, phi0)
                p1 = _torus_pt(theta1, phi0)
                p2 = _torus_pt(theta1, phi1)
                p3 = _torus_pt(theta0, phi1)
                polygons.append(Polygon([p0, p1, p2, p3]))

        return cls.from_polygons(polygons)

    @classmethod
    def from_extrusion(cls, profile, vector: Vector, cap_ends: bool = True) -> Brep:
        """Create a Brep by extruding a profile along a vector.

        Parameters
        ----------
        profile : BrepFace or Polygon
            The profile to extrude. If a BrepFace, its boundary polygon is used.
        vector : Vector
            The extrusion direction and magnitude.
        cap_ends : bool, optional
            If True, cap the top and bottom.
        """
        # Get boundary points from profile
        if isinstance(profile, BrepFace):
            boundary = [v.point for v in profile.outer_loop.vertices]
        elif isinstance(profile, Polygon):
            boundary = list(profile.points)
        else:
            raise TypeError(f"Unsupported profile type: {type(profile)}")

        n = len(boundary)
        # Create offset points
        top_pts = [Point(p.x + vector.x, p.y + vector.y, p.z + vector.z) for p in boundary]

        polygons = []
        # Side faces
        for i in range(n):
            j = (i + 1) % n
            polygons.append(Polygon([boundary[i], boundary[j], top_pts[j], top_pts[i]]))

        if cap_ends:
            # Bottom cap (reversed winding)
            polygons.append(Polygon(list(reversed(boundary))))
            # Top cap
            polygons.append(Polygon(list(top_pts)))

        return cls.from_polygons(polygons)

    @classmethod
    def from_brepfaces(cls, faces: list[BrepFace]) -> Brep:
        """Build a Brep from a list of BrepFace objects."""
        polygons = [face.to_polygon() for face in faces]
        return cls.from_polygons(polygons)

    @classmethod
    def from_plane(
        cls,
        plane: Plane,
        domain_u: tuple[float, float] = (-1, 1),
        domain_v: tuple[float, float] = (-1, 1),
    ) -> Brep:
        """Create a single planar face Brep from a Plane with the given domain."""
        origin = plane.point
        frame = Frame.from_plane(plane)
        xaxis = Vector(*frame.xaxis)
        yaxis = Vector(*frame.yaxis)

        u0, u1 = domain_u
        v0, v1 = domain_v

        corners = [
            Point(
                origin.x + u0 * xaxis.x + v0 * yaxis.x,
                origin.y + u0 * xaxis.y + v0 * yaxis.y,
                origin.z + u0 * xaxis.z + v0 * yaxis.z,
            ),
            Point(
                origin.x + u1 * xaxis.x + v0 * yaxis.x,
                origin.y + u1 * xaxis.y + v0 * yaxis.y,
                origin.z + u1 * xaxis.z + v0 * yaxis.z,
            ),
            Point(
                origin.x + u1 * xaxis.x + v1 * yaxis.x,
                origin.y + u1 * xaxis.y + v1 * yaxis.y,
                origin.z + u1 * xaxis.z + v1 * yaxis.z,
            ),
            Point(
                origin.x + u0 * xaxis.x + v1 * yaxis.x,
                origin.y + u0 * xaxis.y + v1 * yaxis.y,
                origin.z + u0 * xaxis.z + v1 * yaxis.z,
            ),
        ]
        return cls.from_polygons([Polygon(corners)])

    @classmethod
    def from_loft(cls, curves, n: int = 32) -> Brep:
        """Create a Brep by lofting between profile curves (polygonal approximation).

        Parameters
        ----------
        curves : list
            List of NurbsCurve (or any curve with a ``point_at`` method) profiles.
        n : int, optional
            Number of sample points per curve.
        """
        if len(curves) < 2:
            raise ValueError("from_loft requires at least 2 curves")

        # Sample each curve at n points
        profiles = []
        for curve in curves:
            pts = [curve.point_at(t) for t in [i / (n - 1) for i in range(n)]]
            profiles.append(pts)

        polygons = []
        num_profiles = len(profiles)
        for pi in range(num_profiles - 1):
            for si in range(n - 1):
                p0 = profiles[pi][si]
                p1 = profiles[pi][si + 1]
                p2 = profiles[pi + 1][si + 1]
                p3 = profiles[pi + 1][si]
                polygons.append(Polygon([p0, p1, p2, p3]))

        return cls.from_polygons(polygons)

    # =========================================================================
    # Geometric operations
    # =========================================================================

    def slice(self, plane: Plane) -> list[Polyline]:
        """Intersect the Brep with a plane, returning intersection polylines.

        Parameters
        ----------
        plane : Plane
            The cutting plane.

        Returns
        -------
        list[Polyline]
            Intersection polylines.
        """
        normal = plane.normal
        d = -(normal.x * plane.point.x + normal.y * plane.point.y + normal.z * plane.point.z)

        all_segments = []
        for face in self._faces:
            points = [v.point for v in face.outer_loop.vertices]
            intersection_pts = []
            np = len(points)
            for i in range(np):
                p0 = points[i]
                p1 = points[(i + 1) % np]
                d0 = normal.x * p0.x + normal.y * p0.y + normal.z * p0.z + d
                d1 = normal.x * p1.x + normal.y * p1.y + normal.z * p1.z + d

                if abs(d0) < 1e-10:
                    intersection_pts.append(p0)
                if (d0 > 1e-10 and d1 < -1e-10) or (d0 < -1e-10 and d1 > 1e-10):
                    t = d0 / (d0 - d1)
                    ix = p0.x + t * (p1.x - p0.x)
                    iy = p0.y + t * (p1.y - p0.y)
                    iz = p0.z + t * (p1.z - p0.z)
                    intersection_pts.append(Point(ix, iy, iz))

            # Deduplicate
            deduped = []
            for pt in intersection_pts:
                is_dup = False
                for existing in deduped:
                    if (pt.x - existing.x) ** 2 + (pt.y - existing.y) ** 2 + (pt.z - existing.z) ** 2 < 1e-12:
                        is_dup = True
                        break
                if not is_dup:
                    deduped.append(pt)

            if len(deduped) >= 2:
                all_segments.append((deduped[0], deduped[1]))

        if not all_segments:
            return []

        # Chain segments into polylines
        return _chain_segments(all_segments)

    def split(self, cutter: Brep) -> list[Brep]:
        """Split this Brep by a cutter Brep (typically a planar surface).

        The cutter's first face plane is used as the splitting plane.

        Parameters
        ----------
        cutter : Brep
            The cutting Brep (its first face's plane is used).

        Returns
        -------
        list[Brep]
            List of resulting Brep parts.
        """
        if not cutter.faces:
            return [self]

        plane = cutter.faces[0].surface
        front_polys = []
        back_polys = []

        for face in self._faces:
            points = [v.point for v in face.outer_loop.vertices]
            front, back = _clip_polygon_by_plane(points, plane)
            if len(front) >= 3:
                front_polys.append(Polygon(front))
            if len(back) >= 3:
                back_polys.append(Polygon(back))

        results = []
        if front_polys:
            results.append(Brep.from_polygons(front_polys))
        if back_polys:
            results.append(Brep.from_polygons(back_polys))
        return results

    def trimmed(self, plane: Plane) -> Brep:
        """Trim the Brep with a plane, keeping the back side (opposite to normal).

        Parameters
        ----------
        plane : Plane
            The trimming plane. The side the normal points away from is kept.

        Returns
        -------
        Brep
            The trimmed Brep.
        """
        back_polys = []
        for face in self._faces:
            points = [v.point for v in face.outer_loop.vertices]
            _front, back = _clip_polygon_by_plane(points, plane)
            if len(back) >= 3:
                back_polys.append(Polygon(back))
        if not back_polys:
            return Brep()
        return Brep.from_polygons(back_polys)

    # =========================================================================
    # Boolean operations
    # =========================================================================

    @classmethod
    def from_boolean_difference(cls, brep_a: Brep, brep_b: Brep, merge: bool = True) -> Brep:
        """Boolean subtraction: A - B.

        Parameters
        ----------
        brep_a : Brep
            The base Brep.
        brep_b : Brep
            The Brep to subtract.
        merge : bool, optional
            If True, merge coplanar faces in the result. Disable for
            intermediate boolean operations to avoid performance issues.
        """
        polys_a = _brep_to_csg_polygons(brep_a)
        polys_b = _brep_to_csg_polygons(brep_b)
        result = csg_subtract(polys_a, polys_b)
        if merge:
            return cls.from_csg_polygons(result)
        return cls.from_polygons([Polygon(p.vertices) for p in result])

    @classmethod
    def from_boolean_union(cls, brep_a: Brep, brep_b: Brep, merge: bool = True) -> Brep:
        """Boolean union: A + B.

        Parameters
        ----------
        brep_a : Brep
            The first Brep.
        brep_b : Brep
            The second Brep.
        merge : bool, optional
            If True, merge coplanar faces in the result.
        """
        polys_a = _brep_to_csg_polygons(brep_a)
        polys_b = _brep_to_csg_polygons(brep_b)
        result = csg_union(polys_a, polys_b)
        if merge:
            return cls.from_csg_polygons(result)
        return cls.from_polygons([Polygon(p.vertices) for p in result])

    @classmethod
    def from_boolean_intersection(cls, brep_a: Brep, brep_b: Brep, merge: bool = True) -> Brep:
        """Boolean intersection: A & B.

        Parameters
        ----------
        brep_a : Brep
            The first Brep.
        brep_b : Brep
            The second Brep.
        merge : bool, optional
            If True, merge coplanar faces in the result.
        """
        polys_a = _brep_to_csg_polygons(brep_a)
        polys_b = _brep_to_csg_polygons(brep_b)
        result = csg_intersect(polys_a, polys_b)
        if merge:
            return cls.from_csg_polygons(result)
        return cls.from_polygons([Polygon(p.vertices) for p in result])

    @classmethod
    def from_boolean_union_multi(cls, *breps: Brep) -> Brep:
        """Boolean union of multiple Breps, chained at the CSG polygon level for performance.

        Parameters
        ----------
        *breps : Brep
            Two or more Breps to union.

        Returns
        -------
        Brep
        """
        if len(breps) < 2:
            raise ValueError("Need at least 2 breps")
        result = _brep_to_csg_polygons(breps[0])
        for b in breps[1:]:
            result = csg_union(result, _brep_to_csg_polygons(b))
        return cls.from_csg_polygons(result)

    def _get_csg_polygons(self) -> list[CSGPolygon]:
        """Get or cache the CSG polygon representation.

        Uses the cached raw CSG polygons if available (from a previous boolean
        operation), avoiding the expensive Brep → merge → Brep → CSG roundtrip.
        """
        if self._csg_cache is not None:
            return self._csg_cache
        return _brep_to_csg_polygons(self)

    def __sub__(self, other: Brep) -> Brep:
        polys_a = self._get_csg_polygons()
        polys_b = other._get_csg_polygons()
        result_csg = csg_subtract(polys_a, polys_b)
        brep = Brep.from_csg_polygons(result_csg)
        return brep

    def __add__(self, other: Brep) -> Brep:
        polys_a = self._get_csg_polygons()
        polys_b = other._get_csg_polygons()
        result_csg = csg_union(polys_a, polys_b)
        # Store raw CSG result for chaining; build Brep without merging for speed
        brep = Brep.from_polygons([Polygon(p.vertices) for p in result_csg])
        brep._csg_cache = result_csg
        return brep

    def __and__(self, other: Brep) -> Brep:
        polys_a = self._get_csg_polygons()
        polys_b = other._get_csg_polygons()
        result_csg = csg_intersect(polys_a, polys_b)
        brep = Brep.from_csg_polygons(result_csg)
        return brep

    def merge_coplanar_faces(self) -> Brep:
        """Return a new Brep with coplanar adjacent faces merged.

        Useful after chaining boolean operations to clean up the topology.

        Returns
        -------
        Brep
            A new Brep with merged faces.
        """
        polygons = self.to_polygons()
        merged = _merge_coplanar_polygons(polygons)
        return Brep.from_polygons(merged)

    # =========================================================================
    # Conversion
    # =========================================================================

    def to_meshes(self, u: int = 16, v: int = 16) -> list[Mesh]:
        """Convert the Brep to a list of meshes (one per face)."""
        meshes = []
        for face in self._faces:
            points = [v.point for v in face.outer_loop.vertices]
            verts = [[p.x, p.y, p.z] for p in points]
            # Fan triangulation for convex polygons
            faces = [[0, i, i + 1] for i in range(1, len(verts) - 1)]
            mesh = Mesh.from_vertices_and_faces(verts, faces)
            meshes.append(mesh)
        return meshes

    def to_viewmesh(self, precision: float = 1e-6) -> Mesh:
        """Convert the Brep to a single mesh for visualization."""
        all_vertices = []
        all_faces = []
        vertex_offset = 0

        for face in self._faces:
            points = [v.point for v in face.outer_loop.vertices]
            n = len(points)
            for p in points:
                all_vertices.append([p.x, p.y, p.z])
            # Fan triangulation
            for i in range(1, n - 1):
                all_faces.append([vertex_offset, vertex_offset + i, vertex_offset + i + 1])
            vertex_offset += n

        if not all_vertices:
            return Mesh()
        return Mesh.from_vertices_and_faces(all_vertices, all_faces)

    def to_polygons(self) -> list[Polygon]:
        """Convert each face to a Polygon."""
        return [face.to_polygon() for face in self._faces]

    def to_tesselation(self, linear_deflection: float = 0.1) -> tuple[Mesh, list[Polyline]]:
        """Create a tesselation of the Brep for visualization.

        Returns a triangulated mesh and a list of boundary polylines (one per edge loop).
        Matches the interface expected by compas_viewer's BRepObject.

        Parameters
        ----------
        linear_deflection : float, optional
            Maximum deviation from curved surfaces. Unused for planar faces,
            kept for interface compatibility.

        Returns
        -------
        tuple[Mesh, list[Polyline]]
            A triangulated mesh and edge boundary polylines.
        """
        mesh = self.to_viewmesh(precision=linear_deflection)
        boundaries = []
        for face in self._faces:
            loop_points = [v.point for v in face.outer_loop.vertices]
            if loop_points:
                # Close the loop
                boundaries.append(Polyline(loop_points + [loop_points[0]]))
        return mesh, boundaries

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def vertices(self) -> list[BrepVertex]:
        return self._vertices

    @property
    def edges(self) -> list[BrepEdge]:
        return self._edges

    @property
    def loops(self) -> list[BrepLoop]:
        return self._loops

    @property
    def faces(self) -> list[BrepFace]:
        return self._faces

    @property
    def frame(self) -> Frame:
        return self._frame

    @property
    def points(self) -> list[Point]:
        return [v.point for v in self._vertices]

    @property
    def curves(self):
        return [e.curve for e in self._edges]

    @property
    def surfaces(self):
        return [f.surface for f in self._faces]

    @property
    def trims(self):
        return []

    @property
    def area(self) -> float:
        return sum(f.area for f in self._faces)

    @property
    def volume(self) -> float:
        """Compute volume using the divergence theorem on triangulated faces."""
        vol = 0.0
        for face in self._faces:
            points = [v.point for v in face.outer_loop.vertices]
            for i in range(1, len(points) - 1):
                v0, v1, v2 = points[0], points[i], points[i + 1]
                vol += (
                    v0.x * (v1.y * v2.z - v2.y * v1.z)
                    - v1.x * (v0.y * v2.z - v2.y * v0.z)
                    + v2.x * (v0.y * v1.z - v1.y * v0.z)
                )
        return abs(vol) / 6.0

    @property
    def centroid(self) -> Point:
        if not self._vertices:
            return Point(0, 0, 0)
        xs = [v.point.x for v in self._vertices]
        ys = [v.point.y for v in self._vertices]
        zs = [v.point.z for v in self._vertices]
        n = len(self._vertices)
        return Point(sum(xs) / n, sum(ys) / n, sum(zs) / n)

    @property
    def is_closed(self) -> bool:
        # A rough check: each edge should be shared by exactly 2 faces
        return len(self._faces) >= 4

    @property
    def is_solid(self) -> bool:
        return self.is_closed

    @property
    def is_valid(self) -> bool:
        return len(self._faces) > 0 and len(self._vertices) > 0

    @property
    def is_manifold(self) -> bool:
        return True  # Simplified

    @property
    def is_orientable(self) -> bool:
        return True  # Simplified

    @property
    def is_shell(self) -> bool:
        return not self.is_solid

    @property
    def is_surface(self) -> bool:
        return len(self._faces) == 1

    @property
    def is_compound(self) -> bool:
        return False

    @property
    def is_compoundsolid(self) -> bool:
        return False

    @property
    def is_convex(self) -> bool:
        return False  # Conservative

    @property
    def is_infinite(self) -> bool:
        return False

    @property
    def native_brep(self):
        return self

    @property
    def orientation(self):
        return 0  # FORWARD

    @property
    def type(self):
        return 7  # SHAPE

    @property
    def shells(self):
        return [self]

    @property
    def solids(self):
        return [self] if self.is_solid else []

    # =========================================================================
    # Topology queries
    # =========================================================================

    def vertex_neighbors(self, vertex):
        neighbors = set()
        for edge in self._edges:
            if edge.first_vertex is vertex:
                neighbors.add(edge.last_vertex)
            elif edge.last_vertex is vertex:
                neighbors.add(edge.first_vertex)
        return list(neighbors)

    def vertex_edges(self, vertex):
        return [e for e in self._edges if e.first_vertex is vertex or e.last_vertex is vertex]

    def vertex_faces(self, vertex):
        return [f for f in self._faces if vertex in f.vertices]

    def edge_faces(self, edge):
        return [f for f in self._faces if edge in f.edges]

    def edge_loop(self, edge):
        for loop in self._loops:
            if edge in loop.edges:
                return loop
        return None

    # =========================================================================
    # Internal builders
    # =========================================================================

    def _build_from_box(self, box: Box):
        """Build Brep topology from a COMPAS Box."""
        self._frame = box.frame
        corners = box.points

        # Create vertices for all 8 corners
        self._vertices = [BrepVertex(p) for p in corners]

        # Box.points returns:
        # 0(-x,-y,-z) 1(-x,+y,-z) 2(+x,+y,-z) 3(+x,-y,-z)
        # 4(-x,-y,+z) 5(+x,-y,+z) 6(+x,+y,+z) 7(-x,+y,+z)
        # Face winding: CCW → outward Newell normal
        face_indices = [
            [0, 1, 2, 3],  # bottom (-Z)
            [4, 5, 6, 7],  # top (+Z)
            [0, 3, 5, 4],  # front (-Y)
            [1, 7, 6, 2],  # back (+Y)
            [3, 2, 6, 5],  # right (+X)
            [0, 4, 7, 1],  # left (-X)
        ]

        self._edges = []
        self._loops = []
        self._faces = []

        for indices in face_indices:
            face_verts = [self._vertices[i] for i in indices]
            edges = []
            for j in range(len(face_verts)):
                v0 = face_verts[j]
                v1 = face_verts[(j + 1) % len(face_verts)]
                edge = BrepEdge(v0, v1)
                edges.append(edge)
                self._edges.append(edge)

            loop = BrepLoop(edges)
            self._loops.append(loop)

            face = BrepFace(loop)
            self._faces.append(face)

    def _build_from_polygons(self, polygons: list[Polygon]):
        """Build Brep topology from a list of polygons."""
        vertex_map: dict[tuple[float, float, float], BrepVertex] = {}
        self._vertices = []
        self._edges = []
        self._loops = []
        self._faces = []

        precision = 6  # decimal places for vertex merging

        for polygon in polygons:
            face_verts = []
            for pt in polygon.points:
                key = (round(pt.x, precision), round(pt.y, precision), round(pt.z, precision))
                if key not in vertex_map:
                    vertex = BrepVertex(Point(*key))
                    vertex_map[key] = vertex
                    self._vertices.append(vertex)
                face_verts.append(vertex_map[key])

            if len(face_verts) < 3:
                continue

            # Deduplicate consecutive vertices
            deduped = [face_verts[0]]
            for v in face_verts[1:]:
                if v is not deduped[-1]:
                    deduped.append(v)
            if len(deduped) >= 2 and deduped[-1] is deduped[0]:
                deduped.pop()
            if len(deduped) < 3:
                continue
            face_verts = deduped

            edges = []
            for j in range(len(face_verts)):
                v0 = face_verts[j]
                v1 = face_verts[(j + 1) % len(face_verts)]
                edge = BrepEdge(v0, v1)
                edges.append(edge)
                self._edges.append(edge)

            loop = BrepLoop(edges)
            self._loops.append(loop)

            face = BrepFace(loop)
            self._faces.append(face)

    # =========================================================================
    # Data serialization
    # =========================================================================

    @property
    def __data__(self) -> dict:
        faces_data = []
        for face in self._faces:
            pts = [v.point for v in face.outer_loop.vertices]
            faces_data.append([[p.x, p.y, p.z] for p in pts])
        return {"faces": faces_data}

    @__data__.setter
    def __data__(self, data: dict) -> None:
        polygons = []
        for face_pts in data["faces"]:
            pts = [Point(*xyz) for xyz in face_pts]
            if len(pts) >= 3:
                polygons.append(Polygon(pts))
        self._build_from_polygons(polygons)

    @classmethod
    def __from_data__(cls, data: dict) -> Brep:
        polygons = []
        for face_pts in data["faces"]:
            pts = [Point(*xyz) for xyz in face_pts]
            if len(pts) >= 3:
                polygons.append(Polygon(pts))
        return cls.from_polygons(polygons)

    def __repr__(self):
        return f"Brep(vertices={len(self._vertices)}, edges={len(self._edges)}, faces={len(self._faces)})"

    def __str__(self):
        return (
            "Brep\n"
            "-----\n"
            f"Vertices: {len(self._vertices)}\n"
            f"Edges: {len(self._edges)}\n"
            f"Loops: {len(self._loops)}\n"
            f"Faces: {len(self._faces)}\n"
            f"Frame: {self._frame}\n"
            f"Area: {self.area}\n"
            f"Volume: {self.volume}"
        )


def _brep_to_csg_polygons(brep: Brep) -> list[CSGPolygon]:
    """Convert a Brep's faces to CSG polygons."""
    csg_polys = []
    for i, face in enumerate(brep.faces):
        points = [Point(v.point.x, v.point.y, v.point.z) for v in face.outer_loop.vertices]
        if len(points) >= 3:
            csg_polys.append(CSGPolygon(vertices=points, shared=i))
    return csg_polys


# =============================================================================
# Coplanar face merging
# =============================================================================

_MERGE_PRECISION = 6


def _vertex_key(point: Point) -> tuple[float, float, float]:
    """Round a point to a hashable key for vertex matching."""
    return (
        round(point.x, _MERGE_PRECISION),
        round(point.y, _MERGE_PRECISION),
        round(point.z, _MERGE_PRECISION),
    )


def _plane_key(polygon: Polygon) -> tuple[float, float, float, float]:
    """Compute a hashable key for the plane of a polygon.

    Uses Newell normal + signed distance from origin. Two polygons
    are coplanar iff they share the same plane key.
    """
    from compas.geometry import Vector

    pts = polygon.points
    n = len(pts)
    nx, ny, nz = 0.0, 0.0, 0.0
    for i in range(n):
        p0 = pts[i]
        p1 = pts[(i + 1) % n]
        nx += (p0.y - p1.y) * (p0.z + p1.z)
        ny += (p0.z - p1.z) * (p0.x + p1.x)
        nz += (p0.x - p1.x) * (p0.y + p1.y)
    normal = Vector(nx, ny, nz)
    length = normal.length
    if length < 1e-10:
        return (0.0, 0.0, 0.0, 0.0)
    normal = normal / length

    # Signed distance from origin: d = dot(normal, any_point_on_plane)
    d = normal.x * pts[0].x + normal.y * pts[0].y + normal.z * pts[0].z

    # Canonicalize: ensure the first non-zero component of the normal is positive
    # so that opposite-facing normals get different keys (they're not coplanar).
    prec = 4
    return (round(normal.x, prec), round(normal.y, prec), round(normal.z, prec), round(d, prec))


def _merge_polygon_group(polygons: list[Polygon]) -> list[Polygon]:
    """Merge a group of coplanar polygons by removing shared internal edges.

    Shared edges (appearing as A->B in one polygon and B->A in another)
    are internal and get cancelled. The remaining boundary edges are chained
    into closed loops, each becoming a merged polygon.
    """
    # Collect all directed half-edges; cancel shared pairs
    half_edges: dict[tuple, tuple[Point, Point]] = {}

    for polygon in polygons:
        pts = polygon.points
        n = len(pts)
        for i in range(n):
            p0 = pts[i]
            p1 = pts[(i + 1) % n]
            k0 = _vertex_key(p0)
            k1 = _vertex_key(p1)
            rev = (k1, k0)
            if rev in half_edges:
                # Shared internal edge — cancel both directions
                del half_edges[rev]
            else:
                half_edges[(k0, k1)] = (p0, p1)

    if not half_edges:
        return []

    # Build adjacency map: start_key -> list of (end_key, start_point, end_point)
    # Using a list to handle vertices with multiple outgoing boundary edges
    # (can happen at T-junctions from BSP splitting).
    adj: dict[tuple, list[tuple]] = {}
    for (k0, k1), (p0, p1) in half_edges.items():
        adj.setdefault(k0, []).append((k1, p0, p1))

    # Chain edges into closed loops
    result = []
    used_edges: set[tuple] = set()

    for start_key in adj:
        if all((start_key, nk) in used_edges for nk, _, _ in adj.get(start_key, [])):
            continue

        loop_points: list[Point] = []
        current = start_key

        while True:
            neighbors = adj.get(current, [])
            # Find the first unused outgoing edge
            next_entry = None
            for entry in neighbors:
                edge_key = (current, entry[0])
                if edge_key not in used_edges:
                    next_entry = entry
                    break

            if next_entry is None:
                break

            next_key, p0, _p1 = next_entry
            used_edges.add((current, next_key))
            loop_points.append(p0)
            current = next_key

            if current == start_key:
                break

        if len(loop_points) >= 3:
            result.append(Polygon(loop_points))

    return result


def _merge_coplanar_polygons(polygons: list[Polygon]) -> list[Polygon]:
    """Group polygons by coplanar plane and merge each group."""
    groups: dict[tuple, list[Polygon]] = {}
    for polygon in polygons:
        key = _plane_key(polygon)
        groups.setdefault(key, []).append(polygon)

    result = []
    for _key, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
        else:
            # Resolve T-junctions first, then merge by edge cancellation
            resolved = _resolve_t_junctions(group)
            merged = _merge_polygon_group(resolved)
            result.extend(merged)

    return result


# =============================================================================
# T-junction resolution
# =============================================================================


def _point_on_segment(p: Point, a: Point, b: Point, tol: float = 1e-5) -> bool:
    """Check if point p lies strictly on segment a-b (not at endpoints)."""
    abx, aby, abz = b.x - a.x, b.y - a.y, b.z - a.z
    apx, apy, apz = p.x - a.x, p.y - a.y, p.z - a.z

    # Cross product magnitude (collinearity check)
    cx = aby * apz - abz * apy
    cy = abz * apx - abx * apz
    cz = abx * apy - aby * apx
    cross_len_sq = cx * cx + cy * cy + cz * cz
    seg_len_sq = abx * abx + aby * aby + abz * abz
    if seg_len_sq < tol * tol:
        return False
    if cross_len_sq / seg_len_sq > tol * tol:
        return False

    # Parametric position on segment
    t = (apx * abx + apy * aby + apz * abz) / seg_len_sq
    return tol < t < 1.0 - tol


def _resolve_t_junctions(polygons: list[Polygon]) -> list[Polygon]:
    """Insert vertices at T-junctions between coplanar polygons.

    When a vertex from one polygon lies on an edge of another polygon
    (but is not an endpoint of that edge), it creates a T-junction.
    This function splits such edges by inserting the missing vertex,
    so that subsequent edge-cancellation merge works correctly.
    """
    # Collect all unique vertices from all polygons
    all_vertices: dict[tuple, Point] = {}
    for poly in polygons:
        for p in poly.points:
            all_vertices[_vertex_key(p)] = p

    vertex_list = list(all_vertices.items())

    result = []
    for poly in polygons:
        pts = poly.points
        n = len(pts)
        new_pts: list[Point] = []
        for i in range(n):
            p0 = pts[i]
            p1 = pts[(i + 1) % n]
            new_pts.append(p0)

            k0 = _vertex_key(p0)
            k1 = _vertex_key(p1)

            # Find vertices from other polygons that lie on this edge
            insertions: list[tuple[float, Point]] = []
            for vkey, vpt in vertex_list:
                if vkey == k0 or vkey == k1:
                    continue
                if _point_on_segment(vpt, p0, p1):
                    abx = p1.x - p0.x
                    aby = p1.y - p0.y
                    abz = p1.z - p0.z
                    apx = vpt.x - p0.x
                    apy = vpt.y - p0.y
                    apz = vpt.z - p0.z
                    seg_len_sq = abx * abx + aby * aby + abz * abz
                    t = (apx * abx + apy * aby + apz * abz) / seg_len_sq
                    insertions.append((t, vpt))

            # Insert in parametric order along the edge
            insertions.sort(key=lambda x: x[0])
            for _, vpt in insertions:
                new_pts.append(vpt)

        if len(new_pts) >= 3:
            result.append(Polygon(new_pts))

    return result


# =============================================================================
# Plane-polygon clipping
# =============================================================================


def _clip_polygon_by_plane(points: list[Point], plane: Plane) -> tuple[list[Point], list[Point]]:
    """Split polygon by plane. Returns (front_points, back_points).

    Front is the side the plane normal points towards (d >= 0).
    """
    normal = plane.normal
    d = -(normal.x * plane.point.x + normal.y * plane.point.y + normal.z * plane.point.z)

    front: list[Point] = []
    back: list[Point] = []
    n = len(points)
    for i in range(n):
        p0 = points[i]
        p1 = points[(i + 1) % n]
        d0 = normal.x * p0.x + normal.y * p0.y + normal.z * p0.z + d
        d1 = normal.x * p1.x + normal.y * p1.y + normal.z * p1.z + d

        if d0 >= 0:
            front.append(p0)
        if d0 < 0:
            back.append(p0)

        # Edge crosses plane
        if (d0 > 0 and d1 < 0) or (d0 < 0 and d1 > 0):
            t = d0 / (d0 - d1)
            ix = p0.x + t * (p1.x - p0.x)
            iy = p0.y + t * (p1.y - p0.y)
            iz = p0.z + t * (p1.z - p0.z)
            intersection = Point(ix, iy, iz)
            front.append(intersection)
            back.append(intersection)

    return front, back


def _chain_segments(segments: list[tuple[Point, Point]]) -> list[Polyline]:
    """Chain line segments into polylines by connecting endpoints."""
    if not segments:
        return []

    precision = 6

    def _key(p: Point) -> tuple:
        return (round(p.x, precision), round(p.y, precision), round(p.z, precision))

    # Build adjacency
    adj: dict[tuple, list[tuple[tuple, Point, Point]]] = {}
    for p0, p1 in segments:
        k0 = _key(p0)
        k1 = _key(p1)
        adj.setdefault(k0, []).append((k1, p0, p1))
        adj.setdefault(k1, []).append((k0, p1, p0))

    used: set[int] = set()
    polylines = []

    for seg_idx, (p0, p1) in enumerate(segments):
        if seg_idx in used:
            continue
        used.add(seg_idx)
        chain = [p0, p1]

        # Extend forward from p1
        current_key = _key(p1)
        while True:
            found = False
            for _ni, (nk, _np0, np1) in enumerate(adj.get(current_key, [])):
                # Find the original segment index
                orig_idx = None
                for si, (sp0, sp1) in enumerate(segments):
                    if si in used:
                        continue
                    sk0, sk1 = _key(sp0), _key(sp1)
                    if (sk0 == current_key and sk1 == nk) or (sk1 == current_key and sk0 == nk):
                        orig_idx = si
                        break
                if orig_idx is not None:
                    used.add(orig_idx)
                    chain.append(np1)
                    current_key = nk
                    found = True
                    break
            if not found:
                break

        if len(chain) >= 2:
            # Close the polyline if endpoints match
            if _key(chain[0]) == _key(chain[-1]):
                chain[-1] = chain[0]  # Exact closure
            polylines.append(Polyline(chain))

    return polylines
