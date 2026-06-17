"""Viewer scene object for displaying compas_brep NurbsCurve geometry."""

from __future__ import annotations

from compas.geometry import Line
from compas.geometry import Point
from compas.itertools import pairwise
from compas.scene import GeometryObject
from compas_viewer.scene import GeometryObject as ViewerGeometryObject

from compas_brep.curves import NurbsCurve


class NurbsCurveObject(ViewerGeometryObject, GeometryObject):
    """Viewer scene object for displaying compas_brep NurbsCurve geometry.

    Parameters
    ----------
    **kwargs : dict
        Additional keyword arguments passed to the base classes.
    """

    geometry: NurbsCurve

    @property
    def points(self) -> list[Point] | None:
        return self.geometry.points

    @property
    def lines(self) -> list[Line] | None:
        lines = []
        polyline = self.geometry.to_polyline()
        for pair in pairwise(polyline.points):
            lines.append(Line(*pair))
        return lines

    @property
    def viewmesh(self):
        return None
