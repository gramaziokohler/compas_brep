"""Grasshopper scene object for outputting a compas_brep NurbsSurface as Rhino geometry."""

from __future__ import annotations

from typing import Any

from compas.scene import GeometryObject
from compas_ghpython.scene import GHSceneObject  # type: ignore
from compas_rhino.conversions import transformation_to_rhino  # type: ignore

from compas_brep.backend import nurbs_surface_to_rhino


class NurbsSurfaceObject(GHSceneObject, GeometryObject):
    """Scene object for outputting a compas_brep NurbsSurface as Grasshopper geometry."""

    def draw(self) -> list[Any]:
        geometry = nurbs_surface_to_rhino(self.geometry)
        geometry.Transform(transformation_to_rhino(self.worldtransformation))
        self._guids = [geometry]
        return self.guids
