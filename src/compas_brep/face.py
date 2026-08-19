from __future__ import annotations

from compas.geometry import ConicalSurface
from compas.geometry import CylindricalSurface
from compas.geometry import Frame
from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Polygon
from compas.geometry import SphericalSurface
from compas.geometry import SurfaceType
from compas.geometry import ToroidalSurface
from compas.geometry import Vector
from compas.tolerance import TOL

from compas_brep.edge import BrepEdge
from compas_brep.errors import BrepError
from compas_brep.loop import BrepLoop
from compas_brep.operations import face_to_nurbssurface
from compas_brep.surfaces import NurbsSurface
from compas_brep.vertex import BrepVertex


class BrepFace:
    """A Brep face defined by a surface and boundary loops.

    The surface can be a Plane, CylindricalSurface, or NurbsSurface.
    The outer loop defines the face boundary; inner loops define holes.
    """

    def __init__(
        self,
        outer_loop: BrepLoop,
        surface: Plane | CylindricalSurface | SphericalSurface | ToroidalSurface | ConicalSurface | NurbsSurface | None = None,
        is_reversed: bool = False,
        domain_u: tuple[float, float] | None = None,
        domain_v: tuple[float, float] | None = None,
    ) -> None:
        self._outer_loop = outer_loop
        self._inner_loops: list[BrepLoop] = []
        self._surface: Plane | CylindricalSurface | SphericalSurface | ToroidalSurface | ConicalSurface | NurbsSurface = surface or self._compute_plane()
        self._is_reversed = is_reversed
        self._domain_u = domain_u
        self._domain_v = domain_v
        self._mark_loops()

    def _mark_loops(self) -> None:
        """Tag the loops of this face as outer/inner.

        Called by every ``BrepFace`` constructor, including the backend subclasses,
        so that ``loop.is_outer`` is meaningful for loops reached via ``Brep.loops``.
        """
        self._outer_loop.is_outer = True
        for loop in self._inner_loops:
            loop.is_outer = False

    def _compute_plane(self) -> Plane:
        """Compute the face plane from the outer loop vertices."""
        points = [v.point for v in self._outer_loop.vertices]
        return _plane_from_points(points)

    @property
    def surface(self) -> Plane | CylindricalSurface | SphericalSurface | ToroidalSurface | ConicalSurface | NurbsSurface:
        return self._surface

    @surface.setter
    def surface(self, value: Plane | CylindricalSurface | SphericalSurface | ToroidalSurface | ConicalSurface | NurbsSurface) -> None:
        self._surface = value

    @property
    def surface_type(self) -> str:
        """Return the surface type as a string: 'plane', 'cylinder', 'sphere', 'torus', 'cone', or 'nurbs'."""
        if isinstance(self.surface, Plane):
            return "plane"
        if isinstance(self.surface, CylindricalSurface):
            return "cylinder"
        if isinstance(self.surface, SphericalSurface):
            return "sphere"
        if isinstance(self.surface, ToroidalSurface):
            return "torus"
        if isinstance(self.surface, ConicalSurface):
            return "cone"
        if isinstance(self.surface, NurbsSurface):
            return "nurbs"
        return type(self.surface).__name__.lower()

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
    def is_cylinder(self) -> bool:
        return isinstance(self.surface, CylindricalSurface)

    @property
    def is_sphere(self) -> bool:
        return isinstance(self.surface, SphericalSurface)

    @property
    def is_torus(self) -> bool:
        return isinstance(self.surface, ToroidalSurface)

    @property
    def is_cone(self) -> bool:
        return isinstance(self.surface, ConicalSurface)

    @property
    def is_bspline(self) -> bool:
        """Alias of :attr:`is_nurbs`, for compatibility with ``compas.geometry.BrepFace``."""
        return self.is_nurbs

    @property
    def type(self) -> int:
        """One of the :class:`compas.geometry.SurfaceType` constants."""
        return _SURFACE_TYPES.get(self.surface_type, SurfaceType.OTHER_SURFACE)

    @property
    def loops(self) -> list[BrepLoop]:
        return [self._outer_loop, *self._inner_loops]

    @property
    def outer_loop(self) -> BrepLoop:
        return self._outer_loop

    @property
    def boundary(self) -> BrepLoop:
        """Alias of :attr:`outer_loop`, for compatibility with ``compas_rhino``."""
        return self._outer_loop

    @property
    def holes(self) -> list[BrepLoop]:
        """The inner loops of this face."""
        return list(self._inner_loops)

    @property
    def native_face(self) -> object | None:
        """The underlying backend face, or None for a face not backed by a kernel."""
        return None

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
        loop.is_outer = False
        self._inner_loops.append(loop)

    # =========================================================================
    # Surface evaluation
    # =========================================================================

    def frame_at(self, u: float | None = None, v: float | None = None) -> Frame:
        """The frame of the face at the given surface parameters.

        The zaxis of the returned frame is the *face* normal: for a face whose
        :attr:`is_reversed` is True the underlying surface normal is flipped, so that
        opposite faces of a solid report opposite normals. Use :attr:`surface` directly
        to get the unflipped surface.

        Parameters
        ----------
        u
            The u parameter, in the parametrization of :attr:`surface`. Defaults to the
            middle of :attr:`domain_u`.
        v
            The v parameter, in the parametrization of :attr:`surface`. Defaults to the
            middle of :attr:`domain_v`.

        Returns
        -------
        :class:`compas.geometry.Frame`
            A new frame; modifying it does not affect the face.

        Notes
        -----
        A planar face has no parametrization to speak of - :attr:`surface` is a
        :class:`compas.geometry.Plane`, which carries no x-direction - so for planar
        faces `u` and `v` are distances along the axes of the plane's own frame,
        measured from the plane's origin, and omitting them puts the frame on the face
        centroid rather than in the middle of the uv domain.

        """
        surface = self.surface
        if isinstance(surface, Plane):
            frame = Frame.from_plane(surface)
            if u is None and v is None:
                point = surface.projected_point(self.centroid)
            else:
                du = 0.0 if u is None else u
                dv = 0.0 if v is None else v
                point = frame.point + frame.xaxis * du + frame.yaxis * dv
            frame = Frame(point, frame.xaxis, frame.yaxis)
        else:
            frame = surface.frame_at(
                _default_parameter(u, self.domain_u),
                _default_parameter(v, self.domain_v),
            )

        if self._is_reversed:
            # Flip the yaxis (not the xaxis) so the zaxis - the normal - flips with it.
            frame = Frame(frame.point, frame.xaxis, frame.yaxis.scaled(-1))
        return frame

    def normal_at(self, u: float | None = None, v: float | None = None) -> Vector:
        """The outward normal of the face at the given surface parameters.

        Accounts for :attr:`is_reversed`, see :meth:`frame_at`.

        Returns
        -------
        :class:`compas.geometry.Vector`
            A new vector; modifying it does not affect the face.

        """
        return self.frame_at(u, v).zaxis

    @property
    def nurbssurface(self) -> NurbsSurface:
        """The underlying surface of this face as a NURBS surface.

        Provided for compatibility with ``compas.geometry.BrepFace``. Like the old
        implementations, this returns the *unflipped* underlying surface - it does not
        account for :attr:`is_reversed`. Prefer :meth:`frame_at` where a face normal is
        what is wanted.
        """
        surface = self.surface
        if isinstance(surface, NurbsSurface):
            return surface
        if self.native_face is None:
            raise BrepError(f"Converting a {self.surface_type} face to a NURBS surface requires a face backed by a geometry kernel.")

        return face_to_nurbssurface(self)

    def __repr__(self) -> str:
        return f"BrepFace({len(self.vertices)} vertices, {self.surface_type})"


_SURFACE_TYPES = {
    "plane": SurfaceType.PLANE,
    "cylinder": SurfaceType.CYLINDER,
    "cone": SurfaceType.CONE,
    "sphere": SurfaceType.SPHERE,
    "torus": SurfaceType.TORUS,
    "nurbs": SurfaceType.BSPLINE_SURFACE,
}


def _default_parameter(value: float | None, domain: tuple[float, float] | None) -> float:
    """Resolve an omitted surface parameter to the middle of the domain, or 0.0."""
    if value is not None:
        return value
    if domain is None:
        return 0.0
    return 0.5 * (domain[0] + domain[1])


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
