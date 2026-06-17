"""Rhino scene object for baking a compas_brep Brep into the Rhino document."""

from __future__ import annotations

import scriptcontext as sc  # type: ignore

from compas.scene import GeometryObject
from compas_rhino.conversions import transformation_to_rhino  # type: ignore
from compas_rhino.scene.sceneobject import RhinoSceneObject  # type: ignore

from compas_brep.backend.rhino.conversion import brep_to_rhino


class RhinoBrepObject(RhinoSceneObject, GeometryObject):
    """Scene object for baking a compas_brep Brep into the Rhino document."""

    def draw(self):
        attr = self.compile_attributes()
        geometry = brep_to_rhino(self.geometry)
        geometry.Transform(transformation_to_rhino(self.worldtransformation))
        self._guids = [sc.doc.Objects.AddBrep(geometry, attr)]
        return self.guids
