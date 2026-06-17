from compas.plugins import plugin
from compas.scene import register

from compas_brep.brep import Brep
from compas_brep.curves import NurbsCurve
from compas_brep.surfaces import NurbsSurface

from .brepobject import RhinoBrepObject
from .curveobject import RhinoNurbsCurveObject
from .surfaceobject import RhinoNurbsSurfaceObject


@plugin(category="factories", requires=["Rhino"])
def register_scene_objects():

    register(Brep, RhinoBrepObject, context="Rhino")
    register(NurbsCurve, RhinoNurbsCurveObject, context="Rhino")
    register(NurbsSurface, RhinoNurbsSurfaceObject, context="Rhino")
    print("Registered scene objects for compas_brep in the Rhino context.")
