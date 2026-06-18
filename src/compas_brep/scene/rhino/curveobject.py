"""Rhino scene object for baking a compas_brep NurbsCurve into the Rhino document."""

from __future__ import annotations

from typing import Any

import scriptcontext as sc  # type: ignore
from compas.scene import GeometryObject
from compas_rhino.conversions import transformation_to_rhino  # type: ignore
from compas_rhino.scene import RhinoSceneObject  # type: ignore

from compas_brep.backend import nurbs_curve_to_rhino


class RhinoNurbsCurveObject(RhinoSceneObject, GeometryObject):
    """Scene object for baking a compas_brep NurbsCurve into the Rhino document."""

    def draw(self) -> list[Any]:
        attr = self.compile_attributes()
        geometry = nurbs_curve_to_rhino(self.geometry)
        geometry.Transform(transformation_to_rhino(self.worldtransformation))
        self._guids = [sc.doc.Objects.AddCurve(geometry, attr)]
        return self.guids
