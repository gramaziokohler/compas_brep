"""Rhino file import/export."""

from __future__ import annotations

from compas_brep.backend.rhino.conversion import brep_to_rhino, rhino_to_brep


def _invoke_on_ui(fn):
    """Run fn on the Rhino UI thread and return its result (or raise its exception)."""
    import System
    import Rhino

    result = [None]
    error = [None]

    def wrapper():
        try:
            result[0] = fn()
        except Exception as exc:
            error[0] = exc

    Rhino.RhinoApp.InvokeOnUiThread(System.Action(wrapper))
    if error[0] is not None:
        raise error[0]
    return result[0]


def rhino_to_step(brep, filepath, **kwargs):
    """Export a Brep to a STEP file.

    Safe to call from any thread (GH solve thread, LAMCP bridge, etc.) —
    the actual Rhino document write is marshalled to the UI thread via
    InvokeOnUiThread.
    """
    import Rhino
    import Rhino.FileIO as rio

    rhino_brep = brep_to_rhino(brep)

    def _write():
        doc = Rhino.RhinoDoc.ActiveDoc
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

    _invoke_on_ui(_write)


def rhino_from_step(filepath):
    """Import a Brep from a STEP file.

    Safe to call from any thread — the doc read is marshalled to the UI thread.
    """
    import Rhino
    import Rhino.FileIO as rio

    result_breps = []

    def _read():
        doc = Rhino.RhinoDoc.ActiveDoc
        existing_ids = set(obj.Id for obj in doc.Objects)

        opts = rio.FileReadOptions()
        ok = doc.ReadFile(str(filepath), opts)
        if not ok:
            raise RuntimeError(f"Failed to read STEP file: {filepath}")

        new_ids = [obj.Id for obj in doc.Objects if obj.Id not in existing_ids]
        for oid in new_ids:
            obj = doc.Objects.Find(oid)
            if obj and hasattr(obj.Geometry, "Faces"):
                result_breps.append(rhino_to_brep(obj.Geometry))
            doc.Objects.Delete(oid, True)

    _invoke_on_ui(_read)

    if not result_breps:
        raise RuntimeError(f"No Brep found in STEP file: {filepath}")
    return result_breps[0]
