"""Visualize analytic surfaces extracted from Brep faces.

Builds a cylinder, sphere, torus, and cone, extracts the analytic face.surface
from each, and draws them individually via the viewer scene objects.
"""

from compas.geometry import Cone
from compas.geometry import Cylinder
from compas.geometry import Sphere
from compas.geometry import Torus
from compas_viewer import Viewer

from compas_brep import Brep

# ==============================================================================
# Build primitives and extract analytic face surfaces
# ==============================================================================

breps = [
    (Brep.from_cylinder(Cylinder(radius=1.0, height=2.0)), "cylinder"),
    (Brep.from_sphere(Sphere(radius=1.0)), "sphere"),
    (Brep.from_torus(Torus(radius_axis=2.0, radius_pipe=0.5)), "torus"),
    (Brep.from_cone(Cone(radius=1.0, height=2.0)), "cone"),
]

analytic_surfaces = []
for brep, label in breps:
    for face in brep.faces:
        if face.surface_type not in ("plane", "nurbs"):
            print(f"  {label}: surface_type={face.surface_type!r}  surface={face.surface!r}")
            analytic_surfaces.append(face.surface)
            break

# ==============================================================================
# Visualize
# ==============================================================================

viewer = Viewer()

for surface in analytic_surfaces:
    viewer.scene.add(surface)

viewer.show()
