"""Backend implementations for compas_brep.

This package contains pluggable backend sub-packages for different geometry kernels.
Each backend is a sub-package with logically split modules:

- **OCC** (``occ/``): Uses cadquery-ocp-novtk.
  - ``occ/conversion.py`` — bidirectional OCC ↔ Brep conversion
  - ``occ/factories.py``  — primitive constructors and shape builders
  - ``occ/operations.py`` — boolean and geometric operations
  - ``occ/queries.py``    — property queries and tessellation
  - ``occ/io.py``         — STEP/STL/IGES import and export
  - ``occ/plugins.py``    — COMPAS plugin registrations

- **Rhino** (``rhino/``): Uses Rhino.Geometry.
  - ``rhino/conversion.py`` — bidirectional Rhino ↔ Brep conversion
  - ``rhino/factories.py``  — primitive constructors and shape builders
  - ``rhino/operations.py`` — boolean and geometric operations
  - ``rhino/io.py``         — STEP import and export
  - ``rhino/plugins.py``    — COMPAS plugin registrations

The plugin modules are only loaded by the COMPAS plugin system when the
corresponding kernel is available (``requires=["OCP"]`` or ``requires=["Rhino"]``).
They are **not** imported at package level so that ``compas_brep`` remains
importable in any environment.
"""
