from compas.geometry import Circle, Polygon, Vector
from compas_viewer.viewer import Viewer

from compas_brep import Brep

# Approximate circle as a polygon profile
circle = Circle(radius=0.3)
n = 32
points = [circle.point_at(i / n) for i in range(n)]
profile = Polygon(points)

brep = Brep.from_extrusion(profile, Vector(0, 0, 10))

viewer = Viewer()
viewer.scene.add(brep)
viewer.show()
