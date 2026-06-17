"""COMPAS plugin registration for compas_brep Rhino backend."""

from compas.plugins import plugin

# --- brep-factories ---


@plugin(category="brep-factories", requires=["Rhino"])
def make_box(box):
    from .factories import make_box as _impl

    return _impl(box)


@plugin(category="brep-factories", requires=["Rhino"])
def make_cylinder(cylinder):
    from .factories import make_cylinder as _impl

    return _impl(cylinder)


@plugin(category="brep-factories", requires=["Rhino"])
def make_sphere(sphere):
    from .factories import make_sphere as _impl

    return _impl(sphere)


@plugin(category="brep-factories", requires=["Rhino"])
def make_cone(cone):
    from .factories import make_cone as _impl

    return _impl(cone)


@plugin(category="brep-factories", requires=["Rhino"])
def make_torus(torus):
    from .factories import make_torus as _impl

    return _impl(torus)


@plugin(category="brep-factories", requires=["Rhino"])
def make_from_mesh(mesh):
    from .factories import make_from_mesh as _impl

    return _impl(mesh)


@plugin(category="brep-factories", requires=["Rhino"])
def make_extrusion(face_or_curve, vector, cap_planar_holes=True):
    from .factories import make_extrusion as _impl

    return _impl(face_or_curve, vector, cap_planar_holes)


@plugin(category="brep-factories", requires=["Rhino"])
def make_loft(profiles):
    from .factories import make_loft as _impl

    return _impl(profiles)


@plugin(category="brep-factories", requires=["Rhino"])
def make_from_native(native_brep):
    from .factories import from_native as _impl

    return _impl(native_brep)


@plugin(category="brep-factories", requires=["Rhino"])
def make_sweep(profile, path):
    from .factories import rhino_sweep

    return rhino_sweep(profile, path)


@plugin(category="brep-factories", requires=["Rhino"])
def make_pipe(path, radius):
    from .factories import rhino_pipe

    return rhino_pipe(path, radius)


@plugin(category="brep-factories", requires=["Rhino"])
def make_from_curves(curves):
    from .factories import rhino_from_curves

    return rhino_from_curves(curves)


@plugin(category="brep-factories", requires=["Rhino"])
def make_from_breps(breps):
    from .factories import rhino_from_breps

    return rhino_from_breps(breps)


@plugin(category="brep-factories", requires=["Rhino"])
def make_from_surface(surface, domain_u=None, domain_v=None):
    import Rhino.Geometry as rg

    from .conversion import _compas_nurbs_surface_to_rhino
    from .conversion import rhino_to_brep

    rhino_surface = _compas_nurbs_surface_to_rhino(surface)
    if domain_u is not None:
        rhino_surface.SetDomain(0, rg.Interval(domain_u[0], domain_u[1]))
    if domain_v is not None:
        rhino_surface.SetDomain(1, rg.Interval(domain_v[0], domain_v[1]))
    native = rg.Brep.CreateFromSurface(rhino_surface)
    if native is None:
        raise RuntimeError("Rhino failed to create Brep from NurbsSurface")
    return rhino_to_brep(native)


# --- brep-operations ---


@plugin(category="brep-operations", requires=["Rhino"])
def boolean_difference(brep_a, brep_b):
    from .operations import boolean_difference as _impl

    return _impl(brep_a, brep_b)


@plugin(category="brep-operations", requires=["Rhino"])
def boolean_union(brep_a, brep_b):
    from .operations import boolean_union as _impl

    return _impl(brep_a, brep_b)


@plugin(category="brep-operations", requires=["Rhino"])
def boolean_intersection(brep_a, brep_b):
    from .operations import boolean_intersection as _impl

    return _impl(brep_a, brep_b)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_trimmed(brep, plane):
    from .operations import rhino_trimmed

    return rhino_trimmed(brep, plane)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_split(brep, cutter):
    from .operations import rhino_split

    return rhino_split(brep, cutter)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_slice(brep, plane):
    from .operations import rhino_slice

    return rhino_slice(brep, plane)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_fillet(brep, radius, edges=None):
    from .operations import rhino_fillet

    return rhino_fillet(brep, radius, edges)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_cap_planar_holes(brep):
    from .operations import rhino_cap_planar_holes

    return rhino_cap_planar_holes(brep)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_contains(brep, obj):
    from .operations import rhino_contains

    return rhino_contains(brep, obj)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_fix(brep):
    from .operations import rhino_fix

    return rhino_fix(brep)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_heal(brep):
    from .operations import rhino_fix

    return rhino_fix(brep)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_sew(brep):
    from .factories import rhino_from_breps

    return rhino_from_breps([brep])


@plugin(category="brep-operations", requires=["Rhino"])
def brep_make_solid(brep):
    from .operations import rhino_cap_planar_holes

    return rhino_cap_planar_holes(brep)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_offset(brep, distance):
    raise NotImplementedError("offset not yet implemented for Rhino backend")


@plugin(category="brep-operations", requires=["Rhino"])
def brep_overlap(brep_a, brep_b, deflection=None, tolerance=0.0):
    from .operations import boolean_intersection

    return boolean_intersection(brep_a, brep_b)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_transform(brep, transformation):
    from .operations import rhino_transform

    return rhino_transform(brep, transformation)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_flip(brep):
    from .operations import rhino_flip

    return rhino_flip(brep)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_copy(brep):
    from .operations import rhino_copy

    return rhino_copy(brep)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_to_data(brep) -> dict:
    from .conversion import rhino_brep_to_data

    return rhino_brep_to_data(brep)


@plugin(category="brep-operations", requires=["Rhino"])
def brep_rebuild(brep, data: dict) -> None:
    from .operations import rhino_rebuild

    return rhino_rebuild(brep, data)


# --- brep-queries ---


@plugin(category="brep-queries", requires=["Rhino"])
def brep_area(brep):
    from .operations import rhino_area

    return rhino_area(brep)


@plugin(category="brep-queries", requires=["Rhino"])
def brep_volume(brep):
    from .operations import rhino_volume

    return rhino_volume(brep)


@plugin(category="brep-queries", requires=["Rhino"])
def brep_centroid(brep):
    from .operations import rhino_centroid

    return rhino_centroid(brep)


@plugin(category="brep-queries", requires=["Rhino"])
def brep_aabb(brep):
    from .operations import rhino_aabb

    return rhino_aabb(brep)


@plugin(category="brep-queries", requires=["Rhino"])
def brep_is_solid(brep):
    from .operations import rhino_is_solid

    return rhino_is_solid(brep)


@plugin(category="brep-queries", requires=["Rhino"])
def brep_is_valid(brep):
    from .operations import rhino_is_valid

    return rhino_is_valid(brep)


@plugin(category="brep-queries", requires=["Rhino"])
def brep_extract_topology(brep):
    from .conversion import rhino_extract_topology

    return rhino_extract_topology(brep)


@plugin(category="brep-queries", requires=["Rhino"])
def brep_tessellate(brep, linear_deflection=0.1, n=16, n_curves=64):
    from .operations import rhino_tessellate

    return rhino_tessellate(brep, linear_deflection, n, n_curves)


# --- brep-io ---


@plugin(category="brep-io", requires=["Rhino"])
def brep_to_step(brep, filepath, **kwargs):
    from .io import rhino_to_step

    return rhino_to_step(brep, filepath, **kwargs)


@plugin(category="brep-io", requires=["Rhino"])
def brep_from_step(filepath):
    from .io import rhino_from_step

    return rhino_from_step(filepath)


@plugin(category="brep-io", requires=["Rhino"])
def brep_to_stl(brep, filepath, **kwargs):
    raise NotImplementedError("STL export not yet implemented for Rhino backend")


@plugin(category="brep-io", requires=["Rhino"])
def brep_to_iges(brep, filepath):
    raise NotImplementedError("IGES export not yet implemented for Rhino backend")


@plugin(category="brep-io", requires=["Rhino"])
def brep_from_iges(filepath):
    raise NotImplementedError("IGES import not yet implemented for Rhino backend")
