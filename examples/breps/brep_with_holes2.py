"""Create a polygonal face with polygonal holes using boolean subtraction."""

from compas.geometry import Cylinder, Frame, Point, Polygon, Vector
from compas_viewer.viewer import Viewer

from compas_brep import Brep

# Create a pentagonal face
polygon = Polygon.from_sides_and_radius_xy(5, 10.0)
face = Brep.from_polygons([polygon])

# Create cylinders for the holes (approximated by n-gon cross sections)
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
