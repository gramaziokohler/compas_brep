"""Inspect analytic surface types extracted from Brep faces.

Builds a cylinder and sphere Brep, iterates faces, prints surface_type and
key parameters, then demonstrates a JSON round-trip that preserves the
exact analytic type.
"""

from compas.geometry import Cylinder
from compas.geometry import Sphere

from compas_brep import Brep

# ==============================================================================
# Build primitives
# ==============================================================================

cylinder = Brep.from_cylinder(Cylinder(radius=1.0, height=2.0))
sphere = Brep.from_sphere(Sphere(radius=1.5))

# ==============================================================================
# Inspect surface types
# ==============================================================================

print("=== Cylinder faces ===")
for i, face in enumerate(cylinder.faces):
    s = face.surface
    print(f"  face {i}: {face.surface_type!r}  ->  {s!r}")
    if face.is_cylinder:
        print(f"           radius={s.radius:.4f}  frame_origin={s.frame.point}")

print()
print("=== Sphere faces ===")
for i, face in enumerate(sphere.faces):
    s = face.surface
    print(f"  face {i}: {face.surface_type!r}  ->  {s!r}")
    if face.is_sphere:
        print(f"           radius={s.radius:.4f}  frame_origin={s.frame.point}")

# ==============================================================================
# JSON round-trip
# ==============================================================================

print()
print("=== JSON round-trip (cylinder) ===")
json_string = cylinder.to_jsonstring(pretty=False)
cylinder2 = Brep.from_jsonstring(json_string)

for i, face in enumerate(cylinder2.faces):
    print(f"  face {i}: {face.surface_type!r}")

assert len(cylinder2.faces) == len(cylinder.faces), "face count mismatch after round-trip"
print("Face count preserved:", len(cylinder.faces))

original_types = [f.surface_type for f in cylinder.faces]
restored_types = [f.surface_type for f in cylinder2.faces]
assert original_types == restored_types, f"surface types changed: {original_types} -> {restored_types}"
print("Surface types preserved:", original_types)

print()
print("=== JSON round-trip (sphere) ===")
json_string2 = sphere.to_jsonstring(pretty=False)
sphere2 = Brep.from_jsonstring(json_string2)

for i, face in enumerate(sphere2.faces):
    print(f"  face {i}: {face.surface_type!r}")

assert len(sphere2.faces) == len(sphere.faces), "face count mismatch after round-trip"
print("Face count preserved:", len(sphere.faces))

original_types2 = [f.surface_type for f in sphere.faces]
restored_types2 = [f.surface_type for f in sphere2.faces]
assert original_types2 == restored_types2, f"surface types changed: {original_types2} -> {restored_types2}"
print("Surface types preserved:", original_types2)

print()
print("Done.")
