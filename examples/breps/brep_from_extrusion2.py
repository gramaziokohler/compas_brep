from compas.colors import Color
from compas.geometry import Box, Plane, Polygon, Polyline, Vector, offset_polyline
from compas_viewer.viewer import Viewer

from compas_brep import Brep

polyline = Polyline([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0], [0, 5, 0]])

inside = Polyline(offset_polyline(polyline, 0.05))
outside = Polyline(offset_polyline(polyline, -0.05))

polygon = Polygon(outside.points + inside.points[::-1])

brep = Brep.from_polygons([polygon])
extrusion = Brep.from_extrusion(brep.faces[0], Vector(0, 0, 5))

box = Brep.from_box(Box(10, 1, 3))
extrusion = Brep.from_boolean_difference(extrusion, box)

plane = Plane([3, 5, 7.5], [1, 0, 0])
cutter = Brep.from_plane(plane, domain_u=(-10, 10), domain_v=(-10, 10))
extrusion = extrusion.split(cutter)[1]

print(extrusion.is_closed)
print(extrusion.is_orientable)

print(extrusion.is_compound)
print(extrusion.is_solid)
print(extrusion.is_infinite)

viewer = Viewer()
viewer.scene.add(polyline)

viewer.scene.add(inside, color=Color.red())
viewer.scene.add(outside, color=Color.blue())
viewer.scene.add(polygon, color=Color.green())

viewer.scene.add(extrusion, facecolor=Color.cyan(), linecolor=Color.cyan().contrast)

viewer.show()
