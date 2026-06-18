"""Viewer scene object for displaying compas_brep Brep geometry."""

from __future__ import annotations

from compas.geometry import Line
from compas.geometry import Point
from compas.scene import GeometryObject
from compas.tolerance import TOL
from compas_viewer.scene import GeometryObject as ViewerGeometryObject

from compas_brep.brep import Brep


class BrepObject(ViewerGeometryObject, GeometryObject):
    """Viewer scene object for displaying compas_brep Brep geometry.

    Parameters
    ----------
    **kwargs : dict
        Additional keyword arguments passed to the base classes.

    Attributes
    ----------
    geometry : :class:`compas_brep.Brep`
        The Brep geometry.
    """

    geometry: Brep

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._viewmesh, self._boundaries = self.geometry.to_tesselation(TOL.lineardeflection)

    @property
    def points(self) -> list[Point]:
        return self.geometry.points

    @property
    def lines(self) -> list[Line]:
        lines = []
        for polyline in self._boundaries:
            lines += polyline.lines
        return lines

    @property
    def viewmesh(self) -> tuple[list[Point], list[list[int]]]:
        return self._viewmesh.to_vertices_and_faces(triangulated=True)
