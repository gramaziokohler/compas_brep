"""OCC backend sub-package for compas_brep.

Modules
-------
conversion
    Bidirectional conversion between canonical Brep data and OCC shapes
    (``occ_to_brep``, ``brep_to_occ``, and all private helper functions).
factories
    Primitive constructors and shape builders
    (``make_box``, ``make_cylinder``, ``occ_sweep``, ``occ_from_surface``, …).
operations
    Boolean and geometric operations
    (``boolean_difference``, ``occ_trimmed``, ``occ_fillet``, ``occ_rebuild``, …).
queries
    Property queries and tessellation
    (``occ_area``, ``occ_aabb``, ``occ_tessellate``, …).
io
    File import/export
    (``occ_to_step``, ``occ_from_step``, ``occ_to_stl``, …).
plugins
    COMPAS plugin registrations for the OCC backend.
"""
