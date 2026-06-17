from compas.plugins import plugin
from compas.scene import register

from compas_brep.brep import Brep
from compas_brep.curves import NurbsCurve
from compas_brep.surfaces import NurbsSurface

from .brepobject import BrepObject
from .curveobject import NurbsCurveObject
from .surfaceobject import NurbsSurfaceObject


@plugin(category="factories", requires=["compas_viewer"])
def register_scene_objects():

    register(Brep, BrepObject, context="Viewer")
    register(NurbsCurve, NurbsCurveObject, context="Viewer")
    register(NurbsSurface, NurbsSurfaceObject, context="Viewer")
    print("Registered scene objects for compas_brep in the Viewer context.")
