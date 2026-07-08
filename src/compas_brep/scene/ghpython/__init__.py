"""Scene object plugins for visualising compas_brep objects in Grasshopper.

Unlike the Rhino scene objects, which bake geometry into the Rhino document,
these scene objects return Rhino.Geometry instances so they can be passed
along as Grasshopper output data.
"""

from compas.plugins import plugin
from compas.scene import register

from compas_brep.brep import Brep
from compas_brep.curves import NurbsCurve
from compas_brep.surfaces import NurbsSurface

from .brepobject import BrepObject
from .curveobject import NurbsCurveObject
from .surfaceobject import NurbsSurfaceObject


@plugin(category="factories", requires=["Rhino"])
def register_scene_objects():
    register(Brep, BrepObject, context="Grasshopper")
    register(NurbsCurve, NurbsCurveObject, context="Grasshopper")
    register(NurbsSurface, NurbsSurfaceObject, context="Grasshopper")
    print("Registered scene objects for compas_brep in the Grasshopper context.")
