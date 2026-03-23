from math import radians

from compas.colors import Color
from compas.geometry import Box, Plane, Rotation, is_point_infrontof_plane
from compas_viewer import Viewer

from compas_brep import Brep

box = Brep.from_box(Box(1))

R = Rotation.from_axis_and_angle([0, 1, 0], radians(30))
plane = Plane.worldXY()
plane.transform(R)
splitter = Brep.from_plane(plane, domain_u=(-2, +2), domain_v=(-2, +2))

result = box.split(splitter)

# =============================================================================
# Visualization
# =============================================================================

viewer = Viewer()

viewer.renderer.camera.target = [0, 0, 0]
viewer.renderer.camera.position = [2, -4, 1]

viewer.scene.add(splitter, linewidth=2, opacity=0.3)

for brep in result:  # type: ignore
    if is_point_infrontof_plane(brep.centroid, plane):
        viewer.scene.add(
            brep,
            surfacecolor=Color.red().lightened(50),
            linecolor=Color.red(),
            linewidth=2,
            show_points=False,
        )
    else:
        viewer.scene.add(
            brep,
            surfacecolor=Color.blue().lightened(50),
            linecolor=Color.blue(),
            linewidth=2,
            show_points=False,
        )

viewer.show()
