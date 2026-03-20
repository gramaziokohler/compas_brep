"""Boolean subtraction of two boxes, visualized with compas_viewer."""

from compas.colors import Color
from compas.geometry import Box, Frame, Point, Vector
from compas_viewer import Viewer

from compas_brep import Brep

# Create two overlapping boxes
box_a = Box(2.0, 2.0, 2.0, Frame(Point(0, 0, 0), Vector(1, 0, 0), Vector(0, 1, 0)))
box_b = Box(1.5, 1.5, 1.5, Frame(Point(0.5, 0.5, 0.5), Vector(1, 0, 0), Vector(0, 1, 0)))

# Create Breps from boxes
brep_a = Brep.from_box(box_a)
brep_b = Brep.from_box(box_b)

print(f"Brep A: {brep_a}")
print(f"Brep B: {brep_b}")
print(f"Brep A volume: {brep_a.volume:.4f}")
print(f"Brep B volume: {brep_b.volume:.4f}")

# Boolean subtraction: A - B
result = brep_a - brep_b

print(f"Result: {result}")
print(f"Result volume: {result.volume:.4f}")
print(f"Result faces: {len(result.faces)}")
print(f"Result vertices: {len(result.vertices)}")

# Visualize with compas_viewer - pass Brep directly
viewer = Viewer()
viewer.scene.add(result, surfacecolor=Color(0.2, 0.6, 0.9))
viewer.show()
