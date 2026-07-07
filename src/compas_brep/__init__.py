"""compas_brep: Pure Python Brep implementation based on the COMPAS framework."""

__version__ = "0.1.2"

import os

from compas_brep.brep import Brep
from compas_brep.curves import NurbsCurve
from compas_brep.edge import BrepEdge
from compas_brep.errors import BrepError
from compas_brep.errors import BrepFilletError
from compas_brep.errors import BrepInvalidError
from compas_brep.errors import BrepTrimmingError
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.surfaces import NurbsSurface
from compas_brep.trim import BrepTrim
from compas_brep.vertex import BrepVertex

DATA = os.path.join(os.path.dirname(__file__), "data")


__all_plugins__ = [
    "compas_brep.scene",
    "compas_brep.backend.occ.plugins",
    "compas_brep.backend.rhino.plugins",
    "compas_brep.scene.viewer",
    "compas_brep.scene.rhino",
]

__all__ = [
    "DATA",
    "Brep",
    "BrepVertex",
    "BrepEdge",
    "BrepLoop",
    "BrepFace",
    "BrepTrim",
    "NurbsCurve",
    "NurbsSurface",
    "BrepError",
    "BrepInvalidError",
    "BrepTrimmingError",
    "BrepFilletError",
]
