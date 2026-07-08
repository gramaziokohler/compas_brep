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
    # compas treats "Rhino" and "Grasshopper" as separate registration namespaces
    # (see compas.scene.context.detect_current_context) even though both run inside
    # the same Rhino process — register for both so drawing works from either.
    for context in ("Rhino", "Grasshopper"):
        register(Brep, RhinoBrepObject, context=context)
        register(NurbsCurve, RhinoNurbsCurveObject, context=context)
        register(NurbsSurface, RhinoNurbsSurfaceObject, context=context)
    print("Registered scene objects for compas_brep in the Rhino and Grasshopper contexts.")
