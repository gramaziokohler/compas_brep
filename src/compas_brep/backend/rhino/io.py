"""Rhino file import/export."""

from __future__ import annotations

from compas_brep.backend.rhino.conversion import brep_to_rhino, rhino_to_brep


def rhino_to_step(brep, filepath, **kwargs):
    """Export a Brep to a STEP file."""
    import Rhino.FileIO as rio

    rhino_brep = brep_to_rhino(brep)
    rio.File3dm.WriteToStep(rhino_brep, str(filepath))


def rhino_from_step(filepath):
    """Import a Brep from a STEP file."""
    import Rhino.FileIO as rio

    model = rio.File3dm.ReadStep(str(filepath))
    for obj in model.Objects:
        geo = obj.Geometry
        if hasattr(geo, "Faces"):
            return rhino_to_brep(geo)
    raise RuntimeError(f"No Brep found in STEP file: {filepath}")
