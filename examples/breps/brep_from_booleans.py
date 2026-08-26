from compas.geometry import Box, Cylinder, Frame
from compas.tolerance import TOL
from compas_viewer import Viewer

from compas_brep import Brep

TOL.lineardeflection = 0.1

R = 1.4
YZ = Frame.worldYZ()
ZX = Frame.worldZX()
XY = Frame.worldXY()

box = Brep.from_box(Box(2 * R))
cx = Brep.from_cylinder(Cylinder(0.7 * R, 4 * R, frame=YZ))
cy = Brep.from_cylinder(Cylinder(0.7 * R, 4 * R, frame=ZX))
cz = Brep.from_cylinder(Cylinder(0.7 * R, 4 * R, frame=XY))

# The three cylinders cross, so their union is a single solid.
tool = Brep.from_boolean_union_multi(cx, cy, cz)[0]

# A subtraction returns one Brep per resulting solid.
results = Brep.from_boolean_difference(box, tool)

# ==============================================================================
# Visualisation
# ==============================================================================

viewer = Viewer()

viewer.renderer.camera.target = [0, 0, 0]
viewer.renderer.camera.position = [4, -6, 2]

for result in results:
    viewer.scene.add(result, linewidth=2, show_points=False)

viewer.show()
