"""Boolean subtraction whose result falls apart into two solids.

A 4x4x4 box minus a wide, flat box through its middle leaves a lid and a base
with nothing joining them, so the subtraction returns two Breps rather than one.

Nothing below is backend-specific — it is the plain ``compas_brep`` API, and the
same lines run on OCC and on Rhino, now with the same answer on both.

See ``examples/rhino/brep_boolean_disjoint.py`` for the same subtraction drawn
into the Rhino document instead of the viewer.
"""

from compas.colors import Color
from compas.geometry import Box
from compas.geometry import Frame
from compas.geometry import Point
from compas_viewer import Viewer

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

viewer = Viewer()

viewer.renderer.camera.target = [0, 0, 0]
viewer.renderer.camera.position = [8, -10, 5]

colors = [Color.red(), Color.blue(), Color.green(), Color.yellow()]

for i, result in enumerate(results):
    color = colors[i % len(colors)]
    viewer.scene.add(
        result,
        surfacecolor=color.lightened(50),
        linecolor=color,
        linewidth=2,
        show_points=False,
    )

viewer.show()
