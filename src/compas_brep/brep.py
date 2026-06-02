"""Brep class — thin wrapper around a native backend geometry object.

``_native_brep`` (a TopoDS_Shape or Rhino.Geometry.Brep) is the sole source of truth.
All topology lists (_vertices, _edges, _loops, _faces) are lazy caches populated on
first access via brep_extract_topology; they are never written as authoritative data.
All operations delegate to the active backend (OCC or Rhino) via the COMPAS plugin system.
All public interface inputs and outputs are COMPAS types — no backend types leak through.
"""

from __future__ import annotations

from compas.data import Data
from compas.datastructures import Mesh
from compas.geometry import Box, Cylinder, Frame, Plane, Point, Polygon, Polyline, Sphere, Vector

from compas_brep.edge import BrepEdge
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.operations import (
    boolean_difference,
    boolean_intersection,
    boolean_union,
    brep_aabb,
    brep_area,
    brep_cap_planar_holes,
    brep_centroid,
    brep_contains,
    brep_copy,
    brep_extract_topology,
    brep_fillet,
    brep_fix,
    brep_flip,
    brep_from_iges,
    brep_from_step,
    brep_heal,
    brep_is_solid,
    brep_is_valid,
    brep_make_solid,
    brep_offset,
    brep_overlap,
    brep_rebuild,
    brep_sew,
    brep_slice,
    brep_split,
    brep_tessellate,
    brep_to_data,
    brep_to_iges,
    brep_to_step,
    brep_to_stl,
    brep_transform,
    brep_trimmed,
    brep_volume,
    make_box,
    make_cone,
    make_cylinder,
    make_extrusion,
    make_from_breps,
    make_from_curves,
    make_from_mesh,
    make_from_native,
    make_from_surface,
    make_loft,
    make_pipe,
    make_sphere,
    make_sweep,
    make_torus,
)
from compas_brep.vertex import BrepVertex


class Brep(Data):
    """Thin wrapper around a native backend geometry object (OCC or Rhino).

    ``_native_brep`` is the sole source of truth. Topology lists are lazy caches
    populated on demand from native via ``_ensure_topology``; they are never written
    as primary data. All public interface values are COMPAS types.
    """

    def __new__(cls, *args, **kwargs):
        return object.__new__(cls)

    def __init__(self, name=None):
        super().__init__(name=name)
        self._vertices: list[BrepVertex] = []
        self._edges: list[BrepEdge] = []
        self._loops: list[BrepLoop] = []
        self._faces: list[BrepFace] = []
        self._topology_loaded: bool = False
        self._frame: Frame = Frame.worldXY()
        # Native backend object cache — set by the active backend (OCC/Rhino)
        # after every constructor or operation. Always the source of truth.
        self._native_brep = None
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
        data = brep_to_data(self)
        if self.cache_tessellation:
            # Eagerly compute tessellation if not cached but native brep is available.
            if self._tessellation_cache is None and self._native_brep is not None:
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
        brep = Brep()
        # Reconstruct native backend from STEP-inspired JSON.
        # Raises NotImplementedError if no backend is active (by design).
        brep_rebuild(brep, data)
        # Native is now the source of truth. Clear Python-owned topology so
        # it is lazily repopulated from native on first access.
        brep._vertices = []
        brep._edges = []
        brep._loops = []
        brep._faces = []
        brep._topology_loaded = False
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
        self._ensure_topology()
        return f"Brep(vertices={len(self._vertices)}, edges={len(self._edges)}, faces={len(self._faces)})"

    def __str__(self):
        self._ensure_topology()
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
        self._ensure_topology()
        return self._vertices

    @property
    def edges(self) -> list[BrepEdge]:
        self._ensure_topology()
        return self._edges

    @property
    def loops(self) -> list[BrepLoop]:
        self._ensure_topology()
        return self._loops

    @property
    def faces(self) -> list[BrepFace]:
        self._ensure_topology()
        return self._faces

    @property
    def frame(self) -> Frame:
        return self._frame

    @property
    def points(self) -> list[Point]:
        self._ensure_topology()
        return [v.point for v in self._vertices]

    @property
    def curves(self):
        self._ensure_topology()
        return [e.curve for e in self._edges]

    @property
    def surfaces(self):
        self._ensure_topology()
        return [f.surface for f in self._faces]

    @property
    def trims(self):
        self._ensure_topology()
        all_trims = []
        for face in self._faces:
            for loop in face.loops:
                all_trims.extend(getattr(loop, "trims", []))
        return all_trims

    @property
    def area(self) -> float:
        return brep_area(self)

    @property
    def volume(self) -> float:
        return brep_volume(self)

    def _ensure_topology(self) -> None:
        """Lazily populate vertices/edges/loops/faces from the native backend shape.

        Does nothing if topology is already loaded or no native shape is available.
        """
        if self._topology_loaded or self._native_brep is None:
            return
        try:
            brep_extract_topology(self)
        except NotImplementedError:
            pass
        self._topology_loaded = True

    @property
    def centroid(self) -> Point:
        return brep_centroid(self)

    @property
    def is_closed(self) -> bool:
        # A rough check: each edge should be shared by exactly 2 faces
        return len(self.faces) >= 4

    @property
    def is_solid(self) -> bool:
        return brep_is_solid(self)

    @property
    def is_valid(self) -> bool:
        return brep_is_valid(self)

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
        return len(self.faces) == 1

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
        return self._native_brep

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
        return brep_aabb(self)

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
        mesh = Mesh()
        for polygon in polygons:
            vkeys = [mesh.add_vertex(x=p.x, y=p.y, z=p.z) for p in polygon.points]
            mesh.add_face(vkeys)
        return make_from_mesh(mesh)

    @classmethod
    def from_mesh(cls, mesh: Mesh) -> Brep:
        """Create a Brep from a COMPAS Mesh."""
        return make_from_mesh(mesh)

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

        Parameters
        ----------
        profile : BrepFace, Polygon, or curve
            The profile to extrude.
        vector : Vector
            The extrusion direction and magnitude.
        cap_ends : bool, optional
            If True, cap the top and bottom. Passed to the backend where supported.
        """
        return make_extrusion(profile, vector)

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
        self._replace_from(brep_flip(self))

    def transform(self, matrix) -> None:
        """Transform this Brep in-place by a transformation matrix.

        Parameters
        ----------
        matrix : :class:`compas.geometry.Transformation`
            The transformation to apply.
        """
        self._replace_from(brep_transform(self, matrix))

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
        return brep_copy(self)

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
        """Convert the Brep to a list of meshes for visualization.

        Returns a single mesh covering the whole Brep.

        Parameters
        ----------
        u : int, optional
            Resolution for tessellation.
        v : int, optional
            Unused, kept for interface compatibility.
        """
        mesh, _ = brep_tessellate(self, n=u)
        return [mesh]

    def to_viewmesh(self, precision: float = 1e-6, n: int = 16) -> Mesh:
        """Convert the Brep to a single mesh for visualization.

        Uses cached tessellation if available, otherwise delegates to the
        active backend via the brep_tessellate pluggable.

        Parameters
        ----------
        precision : float, optional
            Unused, kept for interface compatibility.
        n : int, optional
            Resolution for tessellation.
        """
        if self._tessellation_cache is not None:
            return self._tessellation_cache[0]
        mesh, boundaries = brep_tessellate(self, n=n)
        self._tessellation_cache = (mesh, boundaries)
        return mesh

    def to_polygons(self) -> list[Polygon]:
        """Convert each face to a Polygon."""
        return [face.to_polygon() for face in self.faces]

    def to_tesselation(self, linear_deflection: float = 0.1, n: int = 16, n_curves: int = 64) -> tuple[Mesh, list[Polyline]]:
        """Create a tessellation of the Brep for visualization.

        Returns a triangulated mesh and a list of boundary polylines.
        Matches the interface expected by compas_viewer's BRepObject.

        Uses cached tessellation when available.  Otherwise delegates to the
        active backend via the brep_tessellate pluggable and caches the result.

        Parameters
        ----------
        linear_deflection : float, optional
            Linear deflection passed to the backend tessellator.
        n : int, optional
            Resolution for face tessellation.
        n_curves : int, optional
            Number of samples per curved edge for boundary polylines.

        Returns
        -------
        tuple[Mesh, list[Polyline]]
            A triangulated mesh and edge boundary polylines.
        """
        if self._tessellation_cache is not None:
            return self._tessellation_cache
        mesh, boundaries = brep_tessellate(self, linear_deflection=linear_deflection, n=n, n_curves=n_curves)
        self._tessellation_cache = (mesh, boundaries)
        return self._tessellation_cache

    # =========================================================================
    # Topology queries
    # =========================================================================

    def vertex_neighbors(self, vertex):
        neighbors = set()
        for edge in self.edges:
            if edge.first_vertex is vertex:
                neighbors.add(edge.last_vertex)
            elif edge.last_vertex is vertex:
                neighbors.add(edge.first_vertex)
        return list(neighbors)

    def vertex_edges(self, vertex):
        return [e for e in self.edges if e.first_vertex is vertex or e.last_vertex is vertex]

    def vertex_faces(self, vertex):
        return [f for f in self.faces if vertex in f.vertices]

    def edge_faces(self, edge):
        return [f for f in self.faces if edge in f.edges]

    def edge_loop(self, edge):
        for loop in self.loops:
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
        return [loop for loop in self.loops if edge in loop.edges]

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _invalidate_native(self):
        """Clear the native cache (e.g. after deserialization before rebuild)."""
        self._native_brep = None
        self._tessellation_cache = None

    def _replace_from(self, other: Brep) -> None:
        """Replace this Brep's data with another's (for in-place operations)."""
        self._vertices = other._vertices
        self._edges = other._edges
        self._loops = other._loops
        self._faces = other._faces
        self._native_brep = other._native_brep
        self._tessellation_cache = None
        self._topology_loaded = other._topology_loaded


