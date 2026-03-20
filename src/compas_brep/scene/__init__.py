"""Scene objects for compas_brep visualization in compas_viewer."""

from compas.plugins import plugin
from compas.scene import register


@plugin(category="factories", requires=["compas_viewer"])
def register_scene_objects():
    from compas_brep.brep import Brep
    from compas_brep.curves.nurbs import NurbsCurve
    from compas_brep.scene.brepobject import BrepObject
    from compas_brep.scene.curveobject import NurbsCurveObject
    from compas_brep.scene.surfaceobject import NurbsSurfaceObject
    from compas_brep.surfaces.nurbs import NurbsSurface

    register(Brep, BrepObject, context="Viewer")
    register(NurbsCurve, NurbsCurveObject, context="Viewer")
    register(NurbsSurface, NurbsSurfaceObject, context="Viewer")


__all__ = [
    "register_scene_objects",
]
