"""Canonical Brep implementation based on the COMPAS framework.

Owns all geometry data (NURBS surfaces, curves, trim curves, topology) as Python objects.
Operations that require a kernel (booleans, loft, etc.) delegate to a pluggable backend
(OCC via cadquery-ocp-novtk, or Rhino when inside Rhino) via the COMPAS plugin system.
Native backend objects are cached internally for performance.
"""

from __future__ import annotations

from compas.data import Data
from compas.datastructures import Mesh
from compas.geometry import Box, Cylinder, Frame, Plane, Point, Polygon, Polyline, Sphere, Vector

from compas_brep.curves.nurbs import NurbsCurve
from compas_brep.edge import BrepEdge
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.operations import (
    boolean_difference,
    boolean_intersection,
    boolean_union,
    brep_cap_planar_holes,
    brep_contains,
    brep_fillet,
    brep_fix,
    brep_from_iges,
    brep_from_step,
    brep_heal,
    brep_make_solid,
    brep_offset,
    brep_overlap,
    brep_sew,
    brep_slice,
    brep_split,
    brep_to_iges,
    brep_to_step,
    brep_to_stl,
    brep_trimmed,
    make_box,
    make_cone,
    make_cylinder,
    make_extrusion,
    make_from_breps,
    make_from_curves,
    make_from_native,
    make_from_surface,
    make_loft,
    make_pipe,
    make_sphere,
    make_sweep,
    make_torus,
)
from compas_brep.surfaces.nurbs import NurbsSurface
from compas_brep.trim import BrepTrim
from compas_brep.vertex import BrepVertex


class Brep(Data):
    """Canonical Brep implementation that owns all geometry and topology data.

    Stores NURBS surfaces, curves, trim curves, and topology as Python objects
    that are fully serializable. Operations requiring a geometric kernel
    (booleans, SSI, loft, sweep) delegate to a pluggable backend (OCC or Rhino).
    Native backend objects are cached for performance.
    """

    def __new__(cls, *args, **kwargs):
        return object.__new__(cls)

    def __init__(self, name=None):
        super().__init__(name=name)
        self._vertices: list[BrepVertex] = []
        self._edges: list[BrepEdge] = []
        self._loops: list[BrepLoop] = []
        self._faces: list[BrepFace] = []
        self._frame: Frame = Frame.worldXY()
        # Native backend object cache
        self._native_brep = None  # cached OCC TopoDS_Shape or Rhino.Geometry.Brep
        self._native_dirty: bool = True  # True when canonical data changed since last native sync
        # Tessellation cache — populated by to_tesselation(), serialized
        # alongside the Brep data so visualization works without a backend.
        # Set cache_tessellation=False to exclude it from serialization.
        self._tessellation_cache: tuple[Mesh, list[Polyline]] | None = None
        self.cache_tessellation: bool = True

    # =========================================================================
    # Data
    # =========================================================================

    @property
    def __data__(self) -> dict:
        data = {"version": 3, "faces": [face.__data__ for face in self._faces]}
        if self.cache_tessellation:
            # Eagerly compute tessellation if not cached yet but native
            # faces are available (i.e. Brep was just created via backend).
            if self._tessellation_cache is None:
                has_native = any(f._native_face is not None for f in self._faces)
                if has_native:
                    self.to_tesselation()
            if self._tessellation_cache is not None:
                mesh, boundaries = self._tessellation_cache
                verts, faces = mesh.to_vertices_and_faces()
                data["tessellation"] = {
                    "vertices": [[v[0], v[1], v[2]] for v in verts],
                    "faces": faces,
                    "boundaries": [[[p.x, p.y, p.z] for p in b.points] for b in boundaries],
                }
        return data

    @classmethod
    def __from_data__(cls, data: dict) -> Brep:
        brep = _deserialize_brep_data(data)
        # Always rebuild native backend object so tessellation and operations work.
        brep._rebuild_native()
        # Restore tessellation cache if present (avoids re-tessellation).
        tess = data.get("tessellation")
        if tess is not None:
            mesh = Mesh.from_vertices_and_faces(tess["vertices"], tess["faces"])
            boundaries = [Polyline([Point(*p) for p in b]) for b in tess["boundaries"]]
            brep._tessellation_cache = (mesh, boundaries)
        return brep

    # =========================================================================
    # Dunder methods
    # =========================================================================

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

    def __sub__(self, other: Brep) -> Brep:
        return Brep.from_boolean_difference(self, other)

    def __add__(self, other: Brep) -> Brep:
        return Brep.from_boolean_union(self, other)

    def __and__(self, other: Brep) -> Brep:
        return Brep.from_boolean_intersection(self, other)

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
        all_trims = []
        for face in self._faces:
            for loop in face.loops:
                all_trims.extend(getattr(loop, "trims", []))
        return all_trims

    @property
    def area(self) -> float:
        return sum(f.area for f in self._faces)

    @property
    def volume(self) -> float:
        """Compute volume using the divergence theorem on the tessellated mesh.

        Uses the cached tessellation or rebuilds native geometry if needed.
        """
        # Ensure we have tessellated geometry
        self._ensure_native()
        mesh = self.to_viewmesh()
        verts, faces = mesh.to_vertices_and_faces()
        vol = 0.0
        for tri in faces:
            v0 = verts[tri[0]]
            v1 = verts[tri[1]]
            v2 = verts[tri[2]]
            vol += (
                v0[0] * (v1[1] * v2[2] - v2[1] * v1[2])
                - v1[0] * (v0[1] * v2[2] - v2[1] * v0[2])
                + v2[0] * (v0[1] * v1[2] - v1[1] * v0[2])
            )
        return abs(vol) / 6.0

    def _ensure_native(self):
        """Ensure native faces are available for tessellation.

        Native geometry is always rebuilt on deserialization, so this is
        only needed as a safety net.
        """
        if any(f._native_face is not None for f in self._faces):
            return
        self._rebuild_native()

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

    @property
    def aabb(self):
        """Axis-aligned bounding box as a :class:`compas.geometry.Box`.

        Returns
        -------
        :class:`compas.geometry.Box`
        """
        if not self._vertices:
            return Box(1, 1, 1)
        pts = self.points
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        zs = [p.z for p in pts]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        zmin, zmax = min(zs), max(zs)
        cx = (xmin + xmax) / 2
        cy = (ymin + ymax) / 2
        cz = (zmin + zmax) / 2
        dx = max(xmax - xmin, 1e-10)
        dy = max(ymax - ymin, 1e-10)
        dz = max(zmax - zmin, 1e-10)
        return Box(dx, dy, dz, Frame(Point(cx, cy, cz), [1, 0, 0], [0, 1, 0]))

    # =========================================================================
    # Constructors
    # =========================================================================

    @classmethod
    def from_box(cls, box: Box) -> Brep:
        """Create a Brep from a COMPAS Box."""
        return make_box(box)

    @classmethod
    def from_polygons(cls, polygons: list[Polygon]) -> Brep:
        """Create a Brep from a list of COMPAS Polygons."""
        brep = cls()
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
    def from_cylinder(cls, cylinder: Cylinder) -> Brep:
        """Create a Brep from a COMPAS Cylinder."""
        return make_cylinder(cylinder)

    @classmethod
    def from_sphere(cls, sphere: Sphere) -> Brep:
        """Create a Brep from a COMPAS Sphere."""
        return make_sphere(sphere)

    @classmethod
    def from_torus(cls, torus) -> Brep:
        """Create a Brep from a COMPAS Torus."""
        return make_torus(torus)

    @classmethod
    def from_extrusion(cls, profile, vector: Vector, cap_ends: bool = True) -> Brep:
        """Create a Brep by extruding a profile along a vector.

        Tries the active backend first for exact NURBS extrusion.
        Falls back to polygonal extrusion if no backend is available.

        Parameters
        ----------
        profile : BrepFace, Polygon, or curve
            The profile to extrude.
        vector : Vector
            The extrusion direction and magnitude.
        cap_ends : bool, optional
            If True, cap the top and bottom.
        """
        try:
            return make_extrusion(profile, vector)
        except Exception:
            pass

        # Fallback: polygonal extrusion
        if isinstance(profile, BrepFace):
            boundary = [v.point for v in profile.outer_loop.vertices]
        elif isinstance(profile, Polygon):
            boundary = list(profile.points)
        else:
            raise TypeError(f"Unsupported profile type: {type(profile)}")

        n = len(boundary)
        top_pts = [Point(p.x + vector.x, p.y + vector.y, p.z + vector.z) for p in boundary]

        polygons = []
        for i in range(n):
            j = (i + 1) % n
            polygons.append(Polygon([boundary[i], boundary[j], top_pts[j], top_pts[i]]))

        if cap_ends:
            polygons.append(Polygon(list(reversed(boundary))))
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
    def from_loft(cls, curves) -> Brep:
        """Create a Brep by lofting between profile curves.

        Delegates to the active backend (OCC or Rhino) for exact NURBS lofting.

        Parameters
        ----------
        curves : list
            List of NurbsCurve profiles.
        """
        return make_loft(curves)

    @classmethod
    def from_cone(cls, cone) -> Brep:
        """Create a Brep from a COMPAS Cone.

        Parameters
        ----------
        cone : :class:`compas.geometry.Cone`
        """
        return make_cone(cone)

    @classmethod
    def from_native(cls, native_brep) -> Brep:
        """Create a Brep from a native backend object (OCC TopoDS_Shape or Rhino.Geometry.Brep).

        Parameters
        ----------
        native_brep : object
            A native OCC or Rhino brep object.
        """
        return make_from_native(native_brep)

    @classmethod
    def from_sweep(cls, profile, path) -> Brep:
        """Create a Brep by sweeping a profile along a path.

        Parameters
        ----------
        profile : Brep
            The profile to sweep.
        path : Brep
            The path to sweep along.
        """
        return make_sweep(profile, path)

    @classmethod
    def from_pipe(cls, path, radius: float) -> Brep:
        """Create a pipe Brep by sweeping a circle along a path.

        Parameters
        ----------
        path : Brep
            The path curve (as a Brep with edges).
        radius : float
            The pipe radius.
        """
        return make_pipe(path, radius)

    @classmethod
    def from_curves(cls, curves) -> Brep:
        """Create a Brep from planar boundary curves.

        Parameters
        ----------
        curves : list
            List of curves defining a planar face boundary.
        """
        return make_from_curves(curves)

    @classmethod
    def from_breps(cls, breps) -> Brep:
        """Join multiple Breps into one by sewing overlapping edges.

        Parameters
        ----------
        breps : list[Brep]
            Breps to join.
        """
        return make_from_breps(breps)

    @classmethod
    def from_surface(cls, surface, domain_u=None, domain_v=None) -> Brep:
        """Create a Brep from a NURBS surface.

        Parameters
        ----------
        surface : :class:`compas_brep.surfaces.nurbs.NurbsSurface`
            The surface.
        domain_u : tuple[float, float], optional
            U parameter domain.
        domain_v : tuple[float, float], optional
            V parameter domain.
        """
        return make_from_surface(surface, domain_u, domain_v)

    @classmethod
    def from_step(cls, filepath: str) -> Brep:
        """Import a Brep from a STEP file.

        Parameters
        ----------
        filepath : str
            Path to the .step or .stp file.
        """
        return brep_from_step(filepath)

    @classmethod
    def from_iges(cls, filepath: str) -> Brep:
        """Import a Brep from an IGES file.

        Parameters
        ----------
        filepath : str
            Path to the .igs or .iges file.
        """
        return brep_from_iges(filepath)

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
        return brep_slice(self, plane)

    def split(self, cutter: Brep) -> list[Brep]:
        """Split this Brep by a cutter Brep (typically a planar surface).

        Parameters
        ----------
        cutter : Brep
            The cutting Brep.

        Returns
        -------
        list[Brep]
            List of resulting Brep parts.
        """
        return brep_split(self, cutter)

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
        return brep_trimmed(self, plane)

    def trim(self, plane: Plane) -> None:
        """Trim the Brep in-place with a plane.

        Parameters
        ----------
        plane : Plane
            The trimming plane.
        """
        self._replace_from(self.trimmed(plane))

    def contains(self, obj) -> bool:
        """Check if a point is contained inside this solid Brep.

        Parameters
        ----------
        obj : Point
            The point to test.

        Returns
        -------
        bool
        """
        return brep_contains(self, obj)

    def fillet(self, radius: float, edges=None) -> None:
        """Fillet edges in-place.

        Parameters
        ----------
        radius : float
            The fillet radius.
        edges : list[int], optional
            Indices of edges to fillet. If None, fillets all edges.
        """
        self._replace_from(self.filleted(radius, edges))

    def filleted(self, radius: float, edges=None) -> Brep:
        """Return a filleted copy of this Brep.

        Parameters
        ----------
        radius : float
            The fillet radius.
        edges : list[int], optional
            Indices of edges to fillet. If None, fillets all edges.

        Returns
        -------
        Brep
        """
        return brep_fillet(self, radius, edges)

    def offset(self, distance: float) -> Brep:
        """Return an offset copy of this Brep.

        Parameters
        ----------
        distance : float
            The offset distance (positive = outward, negative = inward).

        Returns
        -------
        Brep
        """
        return brep_offset(self, distance)

    def overlap(self, other: Brep, deflection=None, tolerance: float = 0.0):
        """Compute the overlap between this Brep and another.

        Parameters
        ----------
        other : Brep
            The other Brep.
        deflection : float, optional
            Linear deflection for mesh approximation.
        tolerance : float, optional
            Tolerance for overlap detection.

        Returns
        -------
        Brep
            The overlapping region.
        """
        return brep_overlap(self, other, deflection, tolerance)

    def cap_planar_holes(self) -> None:
        """Cap planar holes in this Brep in-place."""
        self._replace_from(brep_cap_planar_holes(self))

    def fix(self) -> None:
        """Fix/repair this Brep in-place."""
        self._replace_from(brep_fix(self))

    def heal(self) -> None:
        """Heal this Brep in-place (fix + sew)."""
        self._replace_from(brep_heal(self))

    def sew(self) -> None:
        """Sew this Brep in-place."""
        self._replace_from(brep_sew(self))

    def make_solid(self) -> None:
        """Convert this Brep from a shell to a solid in-place."""
        self._replace_from(brep_make_solid(self))

    def flip(self) -> None:
        """Flip face orientations of this Brep in-place."""
        for face in self._faces:
            face._is_reversed = not face._is_reversed
        self._invalidate_native()

    def transform(self, matrix) -> None:
        """Transform this Brep in-place by a transformation matrix.

        Parameters
        ----------
        matrix : :class:`compas.geometry.Transformation`
            The transformation to apply.
        """
        from compas.geometry import transform_points

        pts = [[v.point.x, v.point.y, v.point.z] for v in self._vertices]
        transformed = transform_points(pts, matrix)
        for vertex, xyz in zip(self._vertices, transformed):
            vertex._point = Point(*xyz)
        self._invalidate_native()

    def transformed(self, matrix) -> Brep:
        """Return a transformed copy of this Brep.

        Parameters
        ----------
        matrix : :class:`compas.geometry.Transformation`
            The transformation to apply.

        Returns
        -------
        Brep
        """
        copy = self.copy()
        copy.transform(matrix)
        return copy

    def copy(self) -> Brep:
        """Return a deep copy of this Brep.

        Returns
        -------
        Brep
        """
        # TODO: use the native copy mechanism of the backend when possible,
        # to preserve native data and avoid expensive Python-level copying.
        import copy as _copy

        return _copy.deepcopy(self)

    def contours(self, planes: list[Plane]) -> list[list[Polyline]]:
        """Generate contour lines by slicing with multiple planes.

        Parameters
        ----------
        planes : list[Plane]
            The slicing planes.

        Returns
        -------
        list[list[Polyline]]
            For each plane, a list of intersection polylines.
        """
        return [self.slice(plane) for plane in planes]

    # =========================================================================
    # File I/O
    # =========================================================================

    def to_step(self, filepath: str, **kwargs) -> None:
        """Export this Brep to a STEP file.

        Parameters
        ----------
        filepath : str
            Path to the output .step or .stp file.
        """
        brep_to_step(self, filepath, **kwargs)

    def to_stl(self, filepath: str, **kwargs) -> None:
        """Export this Brep to an STL file.

        Parameters
        ----------
        filepath : str
            Path to the output .stl file.
        """
        brep_to_stl(self, filepath, **kwargs)

    def to_iges(self, filepath: str) -> None:
        """Export this Brep to an IGES file.

        Parameters
        ----------
        filepath : str
            Path to the output .igs or .iges file.
        """
        brep_to_iges(self, filepath)

    # =========================================================================
    # Boolean operations
    # =========================================================================

    @classmethod
    def from_boolean_difference(cls, brep_a: Brep, brep_b: Brep) -> Brep:
        """Boolean subtraction: A - B."""
        return boolean_difference(brep_a, brep_b)

    @classmethod
    def from_boolean_union(cls, brep_a: Brep, brep_b: Brep) -> Brep:
        """Boolean union: A + B."""
        return boolean_union(brep_a, brep_b)

    @classmethod
    def from_boolean_intersection(cls, brep_a: Brep, brep_b: Brep) -> Brep:
        """Boolean intersection: A & B."""
        return boolean_intersection(brep_a, brep_b)

    @classmethod
    def from_boolean_union_multi(cls, *breps: Brep) -> Brep:
        """Boolean union of multiple Breps, chained pairwise.

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
        result = breps[0]
        for b in breps[1:]:
            result = cls.from_boolean_union(result, b)
        return result

    # =========================================================================
    # Conversion
    # =========================================================================

    def to_meshes(self, u: int = 16, v: int = 16) -> list[Mesh]:
        """Convert the Brep to a list of meshes (one per face).

        Requires a backend (OCC or Rhino) for tessellation.

        Parameters
        ----------
        u : int, optional
            Resolution for tessellation.
        v : int, optional
            Unused, kept for interface compatibility.
        """
        self._ensure_native()
        meshes = []
        for face in self._faces:
            verts, faces = face.tessellate(n=u)
            if verts:
                mesh = Mesh.from_vertices_and_faces(verts, faces)
                meshes.append(mesh)
        return meshes

    def to_viewmesh(self, precision: float = 1e-6, n: int = 16) -> Mesh:
        """Convert the Brep to a single mesh for visualization.

        Uses cached tessellation if available, otherwise ensures native
        geometry is present and tessellates each face via the backend.

        Parameters
        ----------
        precision : float, optional
            Unused, kept for interface compatibility.
        n : int, optional
            Resolution for face tessellation.
        """
        if self._tessellation_cache is not None:
            return self._tessellation_cache[0]

        self._ensure_native()

        all_vertices = []
        all_faces = []
        vertex_offset = 0

        for face in self._faces:
            verts, faces = face.tessellate(n=n)
            for v in verts:
                all_vertices.append(v)
            for f in faces:
                all_faces.append([fi + vertex_offset for fi in f])
            vertex_offset += len(verts)

        if not all_vertices:
            return Mesh()
        return Mesh.from_vertices_and_faces(all_vertices, all_faces)

    def to_polygons(self) -> list[Polygon]:
        """Convert each face to a Polygon."""
        return [face.to_polygon() for face in self._faces]

    def to_tesselation(
        self, linear_deflection: float = 0.1, n: int = 16, n_curves: int = 64
    ) -> tuple[Mesh, list[Polyline]]:
        """Create a tessellation of the Brep for visualization.

        Returns a triangulated mesh and a list of boundary polylines (one per
        unique edge).  Matches the interface expected by compas_viewer's
        BRepObject.

        Uses cached tessellation when available (populated by a previous call
        or restored from serialized data).  Otherwise tessellates via the
        backend (OCC/Rhino) and caches the result.  The cache is included
        in serialized data when ``cache_tessellation`` is ``True`` (default).

        Parameters
        ----------
        linear_deflection : float, optional
            Unused, kept for interface compatibility.
        n : int, optional
            Resolution for face tessellation.
        n_curves : int, optional
            Number of samples per curved edge for boundary polylines.
            Higher values produce smoother curves. Defaults to 64.

        Returns
        -------
        tuple[Mesh, list[Polyline]]
            A triangulated mesh and edge boundary polylines.
        """
        if self._tessellation_cache is not None:
            return self._tessellation_cache

        mesh = self.to_viewmesh(n=n)

        # Sample edge polylines from edge curves.
        boundaries: list[Polyline] = []
        for edge in self._edges:
            pts = edge.sample_points(n=n_curves)
            if pts and len(pts) >= 2:
                boundaries.append(Polyline(pts))

        self._tessellation_cache = (mesh, boundaries)
        return self._tessellation_cache

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

    def edge_loops(self, edge):
        """Get all loops that contain this edge.

        Parameters
        ----------
        edge : BrepEdge

        Returns
        -------
        list[BrepLoop]
        """
        return [loop for loop in self._loops if edge in loop.edges]

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _invalidate_native(self):
        """Mark the native cache as stale (canonical data was modified)."""
        self._native_brep = None
        self._native_dirty = True
        self._tessellation_cache = None

    def _rebuild_native(self):
        """Rebuild the native OCC shape from canonical data, if OCP is available.

        This restores ``_native_face`` on each :class:`BrepFace` so that
        OCC-based tessellation (with proper trim curves and holes) works
        correctly — e.g. after deserialization where native caches are lost.

        This is optional — the pure-Python tessellation handles trimmed NURBS
        faces using edge curves directly. Native rebuild only improves quality
        for operations that need a kernel (booleans, fillet, etc.).

        Does nothing if OCP is not installed or if reconstruction fails.
        """
        try:
            from compas_brep.backend.occ_backend import brep_to_occ

            brep_to_occ(self)
        except ImportError:
            pass
        except Exception:
            pass

    def _replace_from(self, other: Brep) -> None:
        """Replace this Brep's topology with another's (for in-place operations)."""
        self._vertices = other._vertices
        self._edges = other._edges
        self._loops = other._loops
        self._faces = other._faces
        self._invalidate_native()

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

            trims = []
            for j in range(len(face_verts)):
                v0 = face_verts[j]
                v1 = face_verts[(j + 1) % len(face_verts)]
                edge = BrepEdge(v0, v1)
                self._edges.append(edge)
                trims.append(BrepTrim(edge=edge, is_reversed=False))

            loop = BrepLoop(trims=trims)
            self._loops.append(loop)

            face = BrepFace(loop)
            self._faces.append(face)


def _deserialize_brep_data(data: dict) -> Brep:
    """Deserialize Brep from v3 data dict."""
    brep = Brep()
    vertex_map: dict[tuple[float, float, float], BrepVertex] = {}
    edge_map: dict[tuple, BrepEdge] = {}
    precision = 6

    def _get_vertex(xyz: list[float]) -> BrepVertex:
        key = (round(xyz[0], precision), round(xyz[1], precision), round(xyz[2], precision))
        if key not in vertex_map:
            vertex = BrepVertex(Point(*key))
            vertex_map[key] = vertex
            brep._vertices.append(vertex)
        return vertex_map[key]

    def _get_edge(edge_data: dict) -> BrepEdge:
        start = _get_vertex(edge_data["start"])
        end = _get_vertex(edge_data["end"])
        # Deduplicate edges by their canonical vertex pair (unordered)
        s = edge_data["start"]
        e = edge_data["end"]
        sk = (round(s[0], precision), round(s[1], precision), round(s[2], precision))
        ek = (round(e[0], precision), round(e[1], precision), round(e[2], precision))
        key = (sk, ek) if sk <= ek else (ek, sk)
        if key not in edge_map:
            edge = BrepEdge.__from_data__(edge_data, start, end)
            edge_map[key] = edge
            brep._edges.append(edge)
        return edge_map[key]

    for face_data in data["faces"]:
        surface_info = face_data["surface"]
        if surface_info["type"] == "nurbs":
            surface = NurbsSurface.__from_data__(surface_info["data"])
        else:
            sd = surface_info["data"]
            surface = Plane(Point(*sd["point"]), Vector(*sd["normal"]))

        loops = []
        for loop_data in face_data["loops"]:
            trims = []
            for trim_data in loop_data:
                edge = _get_edge(trim_data["edge"])
                is_reversed = trim_data.get("is_reversed", False)
                pcurve = None
                if "pcurve" in trim_data:
                    pcurve = NurbsCurve.__from_data__(trim_data["pcurve"])
                trim = BrepTrim(edge=edge, is_reversed=is_reversed, curve_2d=pcurve)
                trims.append(trim)
            loop = BrepLoop(trims=trims)
            brep._loops.append(loop)
            loops.append(loop)

        domain_u = tuple(face_data["domain_u"]) if "domain_u" in face_data else None
        domain_v = tuple(face_data["domain_v"]) if "domain_v" in face_data else None
        is_reversed = face_data.get("is_reversed", False)

        face = BrepFace(
            loops[0],
            surface=surface,
            is_reversed=is_reversed,
            domain_u=domain_u,
            domain_v=domain_v,
        )
        for inner_loop in loops[1:]:
            face.add_loop(inner_loop)
        brep._faces.append(face)

    return brep
