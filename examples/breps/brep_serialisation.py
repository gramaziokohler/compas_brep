import compas
from compas.geometry import Box, Cylinder, Frame
from compas_viewer import Viewer

from compas_brep import Brep


def brep_from_booleans():
    R = 1.4

    box = Brep.from_box(Box(2 * R))

    cylx = Brep.from_cylinder(Cylinder(radius=0.7 * R, height=3 * R, frame=Frame.worldYZ()))
    cyly = Brep.from_cylinder(Cylinder(radius=0.7 * R, height=3 * R, frame=Frame.worldZX()))
    cylz = Brep.from_cylinder(Cylinder(radius=0.7 * R, height=3 * R, frame=Frame.worldXY()))

    brep = box - (cylx + cyly + cylz)
    return brep


# =============================================================================
# Dump/Load
# =============================================================================

# brep = Brep.from_box(Box(1))
# brep = Brep.from_sphere(Sphere(1.0))
# brep = Brep.from_cylinder(Cylinder(1.0, 2.0))
brep = brep_from_booleans()

brep: Brep = compas.json_loads(compas.json_dumps(brep))  # type: ignore

# =============================================================================
# Viz
# =============================================================================

viewer = Viewer()
viewer.scene.add(brep)
viewer.show()
