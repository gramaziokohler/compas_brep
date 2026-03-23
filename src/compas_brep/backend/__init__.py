"""Backend implementations for compas_brep.

This package contains pluggable backend modules for different geometry kernels.
Each backend provides plugin registrations (discovered via ``__all_plugins__``)
and an implementation module:

- **OCC** (``occ_plugins.py`` / ``occ_backend.py``): Uses cadquery-ocp-novtk.
- **Rhino** (``rhino_plugins.py`` / ``rhino_backend.py``): Uses Rhino.Geometry.

The plugin modules are only loaded by the COMPAS plugin system when the
corresponding kernel is available (``requires=["OCP"]`` or ``requires=["Rhino"]``).
They are **not** imported at package level so that ``compas_brep`` remains
importable in any environment.
"""
