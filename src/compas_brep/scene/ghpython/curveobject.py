"""Grasshopper scene object for outputting a compas_brep NurbsCurve as Rhino geometry."""

from __future__ import annotations

from typing import Any

from compas.scene import GeometryObject
from compas_ghpython.scene import GHSceneObject  # type: ignore
from compas_rhino.conversions import transformation_to_rhino  # type: ignore

from compas_brep.backend import nurbs_curve_to_rhino


class NurbsCurveObject(GHSceneObject, GeometryObject):
    """Scene object for outputting a compas_brep NurbsCurve as Grasshopper geometry."""

    def draw(self) -> list[Any]:
        geometry = nurbs_curve_to_rhino(self.geometry)
        geometry.Transform(transformation_to_rhino(self.worldtransformation))
        self._guids = [geometry]
        return self.guids
