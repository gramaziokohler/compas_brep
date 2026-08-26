"""Boolean subtraction whose result falls apart into two solids — in Rhino.

Run inside Rhino. The subtraction is the same one as
``examples/breps/brep_boolean_disjoint.py``, written against the same plain
``compas_brep`` API — only the drawing differs, baking into the Rhino document
rather than opening the viewer.

A 4x4x4 box minus a wide, flat box through its middle leaves a lid and a base
with nothing joining them, so the subtraction returns two Breps rather than one.
Run both files and the numbers now agree across backends.
"""

import scriptcontext as sc  # type: ignore
from compas.colors import Color
from compas.geometry import Box
from compas.geometry import Frame
from compas.geometry import Point
from compas.scene import Scene

from compas_brep import Brep

box = Brep.from_box(Box(4, 4, 4, Frame.worldXY()))
knife = Brep.from_box(Box(6, 6, 1, Frame(Point(0, 0, 0))))

results = Brep.from_boolean_difference(box, knife)

print(f"pieces  {len(results)}")
for i, result in enumerate(results):
    print(f"  [{i}] volume {result.volume:.3f}, {len(result.faces)} faces, centroid {result.centroid}")
print(f"total   {sum(result.volume for result in results):.3f}")

# `-` is just the operator spelling of from_boolean_difference, list result and all.
assert len(box - knife) == len(results)

# ==============================================================================
# Visualisation
# ==============================================================================

scene = Scene()

colors = [Color.red(), Color.blue(), Color.green(), Color.yellow()]

for i, result in enumerate(results):
    scene.add(result, color=colors[i % len(colors)])

scene.draw()

sc.doc.Views.Redraw()
