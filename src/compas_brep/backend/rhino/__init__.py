"""Rhino backend sub-package for compas_brep.

Modules
-------
conversion
    Bidirectional conversion between canonical Brep data and Rhino shapes
    (``rhino_to_brep``, ``brep_to_rhino``, and all private helper functions).
factories
    Primitive constructors and shape builders
    (``make_box``, ``make_cylinder``, ``rhino_sweep``, ``rhino_from_breps``, …).
operations
    Boolean and geometric operations
    (``boolean_difference``, ``rhino_trimmed``, ``rhino_fillet``, ``rhino_rebuild``, …).
io
    File import/export
    (``rhino_to_step``, ``rhino_from_step``).
plugins
    COMPAS plugin registrations for the Rhino backend.
"""
