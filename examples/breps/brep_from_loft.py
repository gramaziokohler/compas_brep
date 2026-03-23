from compas.geometry import Circle, Frame
from compas.tolerance import TOL
from compas_viewer import Viewer

from compas_brep import Brep, NurbsCurve

frame = Frame.worldYZ()
c1 = Circle(1.0, frame=frame)

frame = Frame.worldYZ()
frame.point = [3, 0, 0]
c2 = Circle(3.0, frame=frame)

frame = Frame.worldYZ()
frame.point = [6, 0, 0]
c3 = Circle(0.5, frame=frame)

frame = Frame.worldYZ()
frame.point = [9, 0, 0]
c4 = Circle(3.0, frame=frame)

curves = [
    NurbsCurve.from_circle(c1),
    NurbsCurve.from_circle(c2),
    NurbsCurve.from_circle(c3),
    NurbsCurve.from_circle(c4),
]

brep = Brep.from_loft(curves)  # type: ignore

TOL.lineardeflection = 1

viewer = Viewer()
viewer.scene.add(brep, linewidth=2)
viewer.show()
