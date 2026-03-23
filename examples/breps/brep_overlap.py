from compas.colors import Color
from compas.geometry import Box, Frame, Point, Vector
from compas_viewer import Viewer

from compas_brep import Brep

A = Brep.from_box(Box(1))
B = Brep.from_box(Box(1, frame=Frame(Point(0.5, 0.3, 0.25), Vector(1, 0, 0), Vector(0, 1, 0))))

# overlap returns the boolean intersection (common volume)
overlap = A.overlap(B)

# =============================================================================
# Visualization
# =============================================================================

viewer = Viewer()

viewer.renderer.camera.target = [0, 0, 0]
viewer.renderer.camera.position = [3, -3, 1]

viewer.scene.add(A, opacity=0.3, linewidth=2)
viewer.scene.add(B, opacity=0.3, linewidth=2)
viewer.scene.add(
    overlap,
    surfacecolor=Color.red().lightened(50),
    linewidth=3,
    linecolor=Color.red(),
)

viewer.show()
