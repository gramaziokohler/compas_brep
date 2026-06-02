"""Pluggable operations for compas_brep — implemented by the active backend (OCC or Rhino)."""

from compas.plugins import pluggable

# ---- Primitive constructors ----


@pluggable(category="brep-factories")
def make_box(box):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_cylinder(cylinder):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_sphere(sphere):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_cone(cone):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_torus(torus):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_mesh(mesh):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_extrusion(face_or_curve, vector):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_loft(profiles):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_native(native_brep):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_sweep(profile, path):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_pipe(path, radius):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_curves(curves):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_breps(breps):
    raise NotImplementedError


@pluggable(category="brep-factories")
def make_from_surface(surface, domain_u=None, domain_v=None):
    raise NotImplementedError


# ---- Boolean operations ----


@pluggable(category="brep-operations")
def boolean_difference(brep_a, brep_b):
    raise NotImplementedError


@pluggable(category="brep-operations")
def boolean_union(brep_a, brep_b):
    raise NotImplementedError


@pluggable(category="brep-operations")
def boolean_intersection(brep_a, brep_b):
    raise NotImplementedError


# ---- Instance operations ----


@pluggable(category="brep-operations")
def brep_trimmed(brep, plane):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_split(brep, cutter):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_slice(brep, plane):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_fillet(brep, radius, edges=None):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_offset(brep, distance):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_cap_planar_holes(brep):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_overlap(brep_a, brep_b, deflection=None, tolerance=0.0):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_contains(brep, obj):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_fix(brep):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_heal(brep):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_sew(brep):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_make_solid(brep):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_transform(brep, transformation):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_flip(brep):
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_copy(brep):
    raise NotImplementedError


# ---- Queries ----


@pluggable(category="brep-queries")
def brep_area(brep):
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_volume(brep):
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_centroid(brep):
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_aabb(brep):
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_is_solid(brep):
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_extract_topology(brep):
    """Populate a Brep's topology lists in-place from its native backend shape.

    Called lazily the first time topology (vertices, edges, loops, faces) is
    accessed on a Brep that was returned from a backend operation without
    eager extraction.
    """
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_is_valid(brep):
    raise NotImplementedError


@pluggable(category="brep-queries")
def brep_tessellate(brep, linear_deflection=0.1, n=16, n_curves=64):
    raise NotImplementedError


# ---- Serialization ----


@pluggable(category="brep-operations")
def brep_to_data(brep) -> dict:
    """Extract a STEP-inspired JSON-serializable dict from the native backend.

    Called from Brep.__data__ to produce the canonical serialization.
    Requires an active backend (OCC or Rhino).
    """
    raise NotImplementedError


@pluggable(category="brep-operations")
def brep_rebuild(brep, data: dict) -> None:
    """Rebuild the native backend object from a STEP-inspired JSON data dict.

    Called from Brep.__from_data__ to reconstruct the native shape.
    Requires an active backend (OCC or Rhino).
    """
    raise NotImplementedError


# ---- File I/O ----


@pluggable(category="brep-io")
def brep_to_step(brep, filepath, **kwargs):
    raise NotImplementedError


@pluggable(category="brep-io")
def brep_from_step(filepath):
    raise NotImplementedError


@pluggable(category="brep-io")
def brep_to_stl(brep, filepath, **kwargs):
    raise NotImplementedError


@pluggable(category="brep-io")
def brep_to_iges(brep, filepath):
    raise NotImplementedError


@pluggable(category="brep-io")
def brep_from_iges(filepath):
    raise NotImplementedError
