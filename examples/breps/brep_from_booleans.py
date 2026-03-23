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

# result = Brep.from_boolean_difference(box, [cx, cy, cz])
result = box - (cx + cy + cz)

# ==============================================================================
# Visualisation
# ==============================================================================

viewer = Viewer()

viewer.renderer.camera.target = [0, 0, 0]
viewer.renderer.camera.position = [4, -6, 2]

viewer.scene.add(result, linewidth=2, show_points=False)

viewer.show()
