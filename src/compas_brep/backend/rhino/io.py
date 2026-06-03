"""Rhino file import/export."""

from __future__ import annotations

from compas_brep.backend.rhino.conversion import brep_to_rhino, rhino_to_brep


def rhino_to_step(brep, filepath, **kwargs):
    """Export a Brep to a STEP file.

    Uses RhinoDoc.WriteFile with dialog suppression.  Must be called from
    the Rhino/GH main thread — will not work from a background HTTP thread
    (e.g. the LAMCP bridge's run_python_script).
    """
    import Rhino
    import Rhino.FileIO as rio

    doc = Rhino.RhinoDoc.ActiveDoc
    rhino_brep = brep_to_rhino(brep)
    obj_id = doc.Objects.AddBrep(rhino_brep)
    doc.Objects.UnselectAll()
    doc.Objects.Select(obj_id)
    try:
        opts = rio.FileWriteOptions()
        opts.SuppressDialogBoxes = True
        opts.SuppressAllInput = True
        opts.WriteSelectedObjectsOnly = True
        ok = doc.WriteFile(str(filepath), opts)
        if not ok:
            raise RuntimeError(f"Failed to write STEP file: {filepath}")
    finally:
        doc.Objects.Delete(obj_id, True)


def rhino_from_step(filepath):
    """Import a Brep from a STEP file.

    Uses RhinoDoc file reading with dialog suppression.  Must be called from
    the Rhino/GH main thread.
    """
    import Rhino
    import Rhino.FileIO as rio

    doc = Rhino.RhinoDoc.ActiveDoc
    existing_ids = set(obj.Id for obj in doc.Objects)

    opts = rio.FileReadOptions()
    ok = doc.ReadFile(str(filepath), opts)
    if not ok:
        raise RuntimeError(f"Failed to read STEP file: {filepath}")

    new_ids = [obj.Id for obj in doc.Objects if obj.Id not in existing_ids]
    breps = []
    for oid in new_ids:
        obj = doc.Objects.Find(oid)
        if obj and hasattr(obj.Geometry, "Faces"):
            breps.append(rhino_to_brep(obj.Geometry))
        doc.Objects.Delete(oid, True)

    if not breps:
        raise RuntimeError(f"No Brep found in STEP file: {filepath}")
    return breps[0]
