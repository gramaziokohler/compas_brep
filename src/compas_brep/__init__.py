"""compas_brep: Pure Python Brep implementation based on the COMPAS framework."""

from compas_brep.brep import Brep
from compas_brep.curves.nurbs import NurbsCurve
from compas_brep.edge import BrepEdge
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.surfaces.nurbs import NurbsSurface
from compas_brep.trim import BrepTrim
from compas_brep.vertex import BrepVertex

__all_plugins__ = [
    "compas_brep.scene",
    "compas_brep.backend.occ_plugins",
    "compas_brep.backend.rhino_plugins",
]

__all__ = [
    "Brep",
    "BrepVertex",
    "BrepEdge",
    "BrepLoop",
    "BrepFace",
    "BrepTrim",
    "NurbsCurve",
    "NurbsSurface",
]
