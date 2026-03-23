from pathlib import Path

from compas.geometry import Box, Cylinder, Frame
from compas_viewer import Viewer

from compas_brep import Brep

IGES = Path(__file__).parent / "booleans.iges"
STEP = Path(__file__).parent / "booleans.step"

# =============================================================================
# Construct boolean Brep
# =============================================================================

R = 1.4
YZ = Frame.worldYZ()
ZX = Frame.worldZX()
XY = Frame.worldXY()

box = Brep.from_box(Box(2 * R))
cx = Brep.from_cylinder(Cylinder(0.7 * R, 4 * R, frame=YZ))
cy = Brep.from_cylinder(Cylinder(0.7 * R, 4 * R, frame=ZX))
cz = Brep.from_cylinder(Cylinder(0.7 * R, 4 * R, frame=XY))

brep = box + cx + cy + cz

# =============================================================================
# Write/Read to IGES
# =============================================================================

brep.to_iges(IGES)
brep = Brep.from_iges(IGES)

# =============================================================================
# Write/Read to STEP
# =============================================================================

brep.to_step(STEP)
brep = Brep.from_step(STEP)

# =============================================================================
# Visualisation
# =============================================================================

viewer = Viewer()

viewer.renderer.camera.target = [0, 0, 0]
viewer.renderer.camera.position = [4, -6, 2]

viewer.scene.add(brep, linewidth=2, show_points=False)

viewer.show()
