"""COMPAS plugin registration for compas_brep OCC backend."""

from compas.plugins import plugin

# --- brep-factories ---


@plugin(category="brep-factories", requires=["OCP"])
def make_box(box):
    from compas_brep.backend.occ.factories import make_box as _impl

    return _impl(box)


@plugin(category="brep-factories", requires=["OCP"])
def make_cylinder(cylinder):
    from compas_brep.backend.occ.factories import make_cylinder as _impl

    return _impl(cylinder)


@plugin(category="brep-factories", requires=["OCP"])
def make_sphere(sphere):
    from compas_brep.backend.occ.factories import make_sphere as _impl

    return _impl(sphere)


@plugin(category="brep-factories", requires=["OCP"])
def make_cone(cone):
    from compas_brep.backend.occ.factories import make_cone as _impl

    return _impl(cone)


@plugin(category="brep-factories", requires=["OCP"])
def make_torus(torus):
    from compas_brep.backend.occ.factories import make_torus as _impl

    return _impl(torus)


@plugin(category="brep-factories", requires=["OCP"])
def make_from_mesh(mesh):
    from compas_brep.backend.occ.factories import make_from_mesh as _impl

    return _impl(mesh)


@plugin(category="brep-factories", requires=["OCP"])
def make_extrusion(face_or_curve, vector):
    from compas_brep.backend.occ.factories import make_extrusion as _impl

    return _impl(face_or_curve, vector)


@plugin(category="brep-factories", requires=["OCP"])
def make_loft(profiles):
    from compas_brep.backend.occ.factories import make_loft as _impl

    return _impl(profiles)


@plugin(category="brep-factories", requires=["OCP"])
def make_from_native(native_brep):
    from compas_brep.backend.occ.factories import from_native as _impl

    return _impl(native_brep)


@plugin(category="brep-factories", requires=["OCP"])
def make_sweep(profile, path):
    from compas_brep.backend.occ.factories import occ_sweep

    return occ_sweep(profile, path)


@plugin(category="brep-factories", requires=["OCP"])
def make_pipe(path, radius):
    from compas_brep.backend.occ.factories import occ_pipe

    return occ_pipe(path, radius)


@plugin(category="brep-factories", requires=["OCP"])
def make_from_curves(curves):
    from compas_brep.backend.occ.factories import occ_from_curves

    return occ_from_curves(curves)


@plugin(category="brep-factories", requires=["OCP"])
def make_from_breps(breps):
    from compas_brep.backend.occ.factories import occ_from_breps

    return occ_from_breps(breps)


@plugin(category="brep-factories", requires=["OCP"])
def make_from_surface(surface, domain_u=None, domain_v=None):
    from compas_brep.backend.occ.factories import occ_from_surface

    return occ_from_surface(surface, domain_u, domain_v)


# --- brep-operations ---


@plugin(category="brep-operations", requires=["OCP"])
def boolean_difference(brep_a, brep_b):
    from compas_brep.backend.occ.operations import boolean_difference as _impl

    return _impl(brep_a, brep_b)


@plugin(category="brep-operations", requires=["OCP"])
def boolean_union(brep_a, brep_b):
    from compas_brep.backend.occ.operations import boolean_union as _impl

    return _impl(brep_a, brep_b)


@plugin(category="brep-operations", requires=["OCP"])
def boolean_intersection(brep_a, brep_b):
    from compas_brep.backend.occ.operations import boolean_intersection as _impl

    return _impl(brep_a, brep_b)


@plugin(category="brep-operations", requires=["OCP"])
def brep_trimmed(brep, plane):
    from compas_brep.backend.occ.operations import occ_trimmed

    return occ_trimmed(brep, plane)


@plugin(category="brep-operations", requires=["OCP"])
def brep_split(brep, cutter):
    from compas_brep.backend.occ.operations import occ_split

    return occ_split(brep, cutter)


@plugin(category="brep-operations", requires=["OCP"])
def brep_slice(brep, plane):
    from compas_brep.backend.occ.operations import occ_slice

    return occ_slice(brep, plane)


@plugin(category="brep-operations", requires=["OCP"])
def brep_fillet(brep, radius, edges=None):
    from compas_brep.backend.occ.operations import occ_fillet

    return occ_fillet(brep, radius, edges)


@plugin(category="brep-operations", requires=["OCP"])
def brep_offset(brep, distance):
    from compas_brep.backend.occ.operations import occ_offset

    return occ_offset(brep, distance)


@plugin(category="brep-operations", requires=["OCP"])
def brep_cap_planar_holes(brep):
    from compas_brep.backend.occ.operations import occ_cap_planar_holes

    return occ_cap_planar_holes(brep)


@plugin(category="brep-operations", requires=["OCP"])
def brep_overlap(brep_a, brep_b, deflection=None, tolerance=0.0):
    from compas_brep.backend.occ.operations import occ_overlap

    return occ_overlap(brep_a, brep_b, deflection, tolerance)


@plugin(category="brep-operations", requires=["OCP"])
def brep_contains(brep, obj):
    from compas_brep.backend.occ.operations import occ_contains

    return occ_contains(brep, obj)


@plugin(category="brep-operations", requires=["OCP"])
def brep_fix(brep):
    from compas_brep.backend.occ.operations import occ_fix

    return occ_fix(brep)


@plugin(category="brep-operations", requires=["OCP"])
def brep_heal(brep):
    from compas_brep.backend.occ.operations import occ_heal

    return occ_heal(brep)


@plugin(category="brep-operations", requires=["OCP"])
def brep_sew(brep):
    from compas_brep.backend.occ.operations import occ_sew

    return occ_sew(brep)


@plugin(category="brep-operations", requires=["OCP"])
def brep_make_solid(brep):
    from compas_brep.backend.occ.operations import occ_make_solid

    return occ_make_solid(brep)


@plugin(category="brep-operations", requires=["OCP"])
def brep_transform(brep, transformation):
    from compas_brep.backend.occ.operations import occ_transform

    return occ_transform(brep, transformation)


@plugin(category="brep-operations", requires=["OCP"])
def brep_flip(brep):
    from compas_brep.backend.occ.operations import occ_flip

    return occ_flip(brep)


@plugin(category="brep-operations", requires=["OCP"])
def brep_copy(brep):
    from compas_brep.backend.occ.operations import occ_copy

    return occ_copy(brep)


# --- brep-queries ---


@plugin(category="brep-queries", requires=["OCP"])
def brep_area(brep):
    from compas_brep.backend.occ.queries import occ_area

    return occ_area(brep)


@plugin(category="brep-queries", requires=["OCP"])
def brep_volume(brep):
    from compas_brep.backend.occ.queries import occ_volume

    return occ_volume(brep)


@plugin(category="brep-queries", requires=["OCP"])
def brep_centroid(brep):
    from compas_brep.backend.occ.queries import occ_centroid

    return occ_centroid(brep)


@plugin(category="brep-queries", requires=["OCP"])
def brep_aabb(brep):
    from compas_brep.backend.occ.queries import occ_aabb

    return occ_aabb(brep)


@plugin(category="brep-queries", requires=["OCP"])
def brep_is_solid(brep):
    from compas_brep.backend.occ.queries import occ_is_solid

    return occ_is_solid(brep)


@plugin(category="brep-queries", requires=["OCP"])
def brep_extract_topology(brep):
    from compas_brep.backend.occ.conversion import occ_extract_topology

    return occ_extract_topology(brep)


@plugin(category="brep-queries", requires=["OCP"])
def brep_is_valid(brep):
    from compas_brep.backend.occ.queries import occ_is_valid

    return occ_is_valid(brep)


@plugin(category="brep-queries", requires=["OCP"])
def brep_tessellate(brep, linear_deflection=0.1, n=16, n_curves=64):
    from compas_brep.backend.occ.queries import occ_tessellate

    return occ_tessellate(brep, linear_deflection, n, n_curves)


@plugin(category="brep-operations", requires=["OCP"])
def brep_rebuild(brep):
    from compas_brep.backend.occ.operations import occ_rebuild

    return occ_rebuild(brep)


# --- brep-io ---


@plugin(category="brep-io", requires=["OCP"])
def brep_to_step(brep, filepath, **kwargs):
    from compas_brep.backend.occ.io import occ_to_step

    return occ_to_step(brep, filepath, **kwargs)


@plugin(category="brep-io", requires=["OCP"])
def brep_from_step(filepath):
    from compas_brep.backend.occ.io import occ_from_step

    return occ_from_step(filepath)


@plugin(category="brep-io", requires=["OCP"])
def brep_to_stl(brep, filepath, **kwargs):
    from compas_brep.backend.occ.io import occ_to_stl

    return occ_to_stl(brep, filepath, **kwargs)


@plugin(category="brep-io", requires=["OCP"])
def brep_to_iges(brep, filepath):
    from compas_brep.backend.occ.io import occ_to_iges

    return occ_to_iges(brep, filepath)


@plugin(category="brep-io", requires=["OCP"])
def brep_from_iges(filepath):
    from compas_brep.backend.occ.io import occ_from_iges

    return occ_from_iges(filepath)
