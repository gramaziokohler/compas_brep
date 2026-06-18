"""Viewer scene objects for displaying compas_brep surface geometry."""

from __future__ import annotations

from compas.datastructures import Mesh
from compas.geometry import CylindricalSurface
from compas.geometry import Line
from compas.geometry import Point
from compas.geometry import Polyline
from compas.itertools import pairwise
from compas.scene import GeometryObject
from compas_viewer.scene import GeometryObject as ViewerGeometryObject

from compas_brep.surfaces import NurbsSurface


class NurbsSurfaceObject(ViewerGeometryObject, GeometryObject):
    """Viewer scene object for displaying compas_brep NurbsSurface geometry.

    Tessellates the surface into a triangle mesh with boundary polylines
    for clean edge rendering.

    Parameters
    ----------
    **kwargs : dict
        Additional keyword arguments passed to the base classes.
    """

    geometry: NurbsSurface

    def __init__(self, n_u: int = 32, n_v: int = 32, **kwargs) -> None:
        super().__init__(**kwargs)
        self._n_u = n_u
        self._n_v = n_v
        self._viewmesh, self._boundaries = self._tessellate()

    def _tessellate(self) -> tuple[Mesh, list[Polyline]]:
        """Tessellate the surface into a mesh and boundary polylines."""
        surface = self.geometry
        u_params = surface.space_u(self._n_u)
        v_params = surface.space_v(self._n_v)

        # Sample points on surface
        vertices = []
        for u in u_params:
            for v in v_params:
                p = surface.point_at(u, v)
                vertices.append([p.x, p.y, p.z])

        # Build quad faces (as triangles)
        faces = []
        nv = len(v_params)
        for i in range(len(u_params) - 1):
            for j in range(len(v_params) - 1):
                v0 = i * nv + j
                v1 = i * nv + (j + 1)
                v2 = (i + 1) * nv + (j + 1)
                v3 = (i + 1) * nv + j
                faces.append([v0, v1, v2])
                faces.append([v0, v2, v3])

        mesh = Mesh.from_vertices_and_faces(vertices, faces) if vertices and faces else Mesh()

        # Boundary polylines (4 edges of the parameter domain)
        boundaries = []
        # U=min edge
        pts = [surface.point_at(u_params[0], v) for v in v_params]
        boundaries.append(Polyline(pts))
        # U=max edge
        pts = [surface.point_at(u_params[-1], v) for v in v_params]
        boundaries.append(Polyline(pts))
        # V=min edge
        pts = [surface.point_at(u, v_params[0]) for u in u_params]
        boundaries.append(Polyline(pts))
        # V=max edge
        pts = [surface.point_at(u, v_params[-1]) for u in u_params]
        boundaries.append(Polyline(pts))

        return mesh, boundaries

    @property
    def points(self) -> list[Point]:
        # Flatten control point grid
        pts = []
        for row in self.geometry.points:
            pts.extend(row)
        return pts

    @property
    def lines(self) -> list[Line]:
        lines = []
        for polyline in self._boundaries:
            for pair in pairwise(polyline.points):
                lines.append(Line(*pair))
        return lines

    @property
    def viewmesh(self) -> tuple[list[Point], list[list[int]]]:
        return self._viewmesh.to_vertices_and_faces(triangulated=True)


def _tessellate_parametric_surface(surface, n_u: int, n_v: int) -> tuple[Mesh, list[Polyline]]:
    """Tessellate any surface with space_u / space_v / point_at into a mesh."""
    u_params = list(surface.space_u(n_u))
    v_params = list(surface.space_v(n_v))

    vertices = []
    for u in u_params:
        for v in v_params:
            p = surface.point_at(u, v)
            vertices.append([p.x, p.y, p.z])

    faces = []
    nv = len(v_params)
    for i in range(len(u_params) - 1):
        for j in range(len(v_params) - 1):
            v0 = i * nv + j
            v1 = i * nv + (j + 1)
            v2 = (i + 1) * nv + (j + 1)
            v3 = (i + 1) * nv + j
            faces.append([v0, v1, v2])
            faces.append([v0, v2, v3])

    mesh = Mesh.from_vertices_and_faces(vertices, faces) if vertices and faces else Mesh()

    boundaries = []
    boundaries.append(Polyline([surface.point_at(u_params[0], v) for v in v_params]))
    boundaries.append(Polyline([surface.point_at(u_params[-1], v) for v in v_params]))
    boundaries.append(Polyline([surface.point_at(u, v_params[0]) for u in u_params]))
    boundaries.append(Polyline([surface.point_at(u, v_params[-1]) for u in u_params]))

    return mesh, boundaries


class AnalyticSurfaceObject(ViewerGeometryObject, GeometryObject):
    """Viewer scene object for analytic surfaces (e.g. CylindricalSurface).

    Works with any surface that exposes ``space_u`` / ``space_v`` / ``point_at``.

    Parameters
    ----------
    **kwargs : dict
        Additional keyword arguments passed to the base classes.
    """

    geometry: CylindricalSurface

    def __init__(self, n_u: int = 32, n_v: int = 32, **kwargs) -> None:
        super().__init__(**kwargs)
        self._n_u = n_u
        self._n_v = n_v
        self._viewmesh, self._boundaries = _tessellate_parametric_surface(self.geometry, n_u, n_v)

    @property
    def points(self) -> list[Point]:
        return []

    @property
    def lines(self) -> list[Line]:
        lines = []
        for polyline in self._boundaries:
            for pair in pairwise(polyline.points):
                lines.append(Line(*pair))
        return lines

    @property
    def viewmesh(self) -> tuple[list[Point], list[list[int]]]:
        return self._viewmesh.to_vertices_and_faces(triangulated=True)
