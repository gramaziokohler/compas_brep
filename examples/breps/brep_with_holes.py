"""Create a planar face with multiple circular holes using boolean subtraction."""

from compas.geometry import Cylinder, Frame, Plane, Point, Vector
from compas_viewer import Viewer

from compas_brep import Brep

# Create a large planar face
face = Brep.from_plane(Plane.worldXY(), domain_u=(-5, 5), domain_v=(-5, 5))

# Create cylinders for the holes
c1 = Brep.from_cylinder(Cylinder(1.0, 2.0, frame=Frame(Point(2, 2, -1), Vector(0, 0, 1), Vector(1, 0, 0))))
c2 = Brep.from_cylinder(Cylinder(2.0, 2.0, frame=Frame(Point(-2, -2, -1), Vector(0, 0, 1), Vector(1, 0, 0))))
c3 = Brep.from_cylinder(Cylinder(0.5, 2.0, frame=Frame(Point(2, -2, -1), Vector(0, 0, 1), Vector(1, 0, 0))))

brep = face - c1 - c2 - c3

# =============================================================================
# Visualization
# =============================================================================

viewer = Viewer()
viewer.scene.add(brep, linewidth=2, show_points=False)
viewer.show()
