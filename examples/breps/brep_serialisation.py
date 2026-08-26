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

    # A subtraction returns one Brep per resulting solid; these three cylinders
    # bore through the box without cutting it into pieces, so there is just one.
    tool = Brep.from_boolean_union_multi(cylx, cyly, cylz)[0]
    results = Brep.from_boolean_difference(box, tool)
    return results[0]


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
