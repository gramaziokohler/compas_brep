"""Create a Brep face with a circular hole using boolean subtraction.

This demonstrates using a cylinder subtracted from a surface Brep to create
a face with a circular hole — using the OCC backend for exact NURBS topology.
"""

from compas.geometry import Cylinder, Frame, Point, Vector
from compas_viewer import Viewer

from compas_brep import Brep, NurbsSurface

points = [
    [Point(0, 0, 0), Point(1, 0, 0), Point(2, 0, 0), Point(3, 0, 0)],
    [Point(0, 1, 0), Point(1, 1, 2), Point(2, 1, 2), Point(3, 1, 0)],
    [Point(0, 2, 0), Point(1, 2, 2), Point(2, 2, 2), Point(3, 2, 0)],
    [Point(0, 3, 0), Point(1, 3, 0), Point(2, 3, 0), Point(3, 3, 0)],
]

surface_brep = Brep.from_surface(NurbsSurface.from_points(points=points))

# Create a cylinder to punch the hole
hole = Brep.from_cylinder(
    Cylinder(
        0.5,
        4.0,
        frame=Frame(Point(1.5, 1.5, -1), Vector(0, 0, 1), Vector(1, 0, 0)),
    )
)

brep = Brep.from_boolean_difference(surface_brep, hole)

# =============================================================================
# Visualization
# =============================================================================

viewer = Viewer()
viewer.scene.add(brep, linewidth=2, show_points=False)
viewer.show()
