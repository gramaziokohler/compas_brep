"""Version compatibility shim for the OCP bindings.

Two things moved between OCP 7 and OCP 8. This module absorbs both, so the
rest of the backend can keep using one spelling.

**Collection arrays.** OCCT 8.0 replaced the hand-instantiated ``TColStd_*`` /
``TColgp_*`` array typedefs with templated ``NCollection`` instantiations, which
OCP 8 exposes under ``OCP.collections`` with mangled names (``Array1_double``,
``Array1_gp_Pnt``, ...). The underlying C++ types are unchanged; only the
binding location moved. They are re-exported here under their OCCT 7 names.

**TopoDS downcasts.** ``OCP.TopoDS.TopoDS`` is a pybind11 *class* in OCP 7.8,
exposing the static downcasts with a ``_s`` suffix (``TopoDS.Face_s``). In 7.9
it became a *module* exposing both ``Face`` and ``Face_s``, and in 8 only the
un-suffixed ``Face`` remains. ``TopoDS`` is re-exported here with the plain
names always present, so call sites read ``TopoDS.Face(shape)`` on any version.

Note that the ``_s`` suffix was *not* dropped wholesale in OCP 8 -- it is still
correct for every other static binding the backend calls (``BRep_Tool.Pnt_s``,
``BRepBndLib.Add_s``, ...). ``TopoDS`` is the exception, because it changed from
a class to a module.

Note that ``Standard_Real`` is a C++ ``double``: the real-valued arrays map to
``Array1_double`` / ``Array2_double``. ``OCP.collections`` also defines
``Array1_float`` (a ``Standard_ShortReal`` array), which is *not* the right
type and would silently lose precision.
"""

from __future__ import annotations

from types import SimpleNamespace

from OCP.TopoDS import TopoDS as _TopoDS

if hasattr(_TopoDS, "Face"):  # OCP >= 7.9
    TopoDS = _TopoDS
else:  # OCP 7.8: only the ``_s``-suffixed static methods exist
    _DOWNCASTS = ("Vertex", "Edge", "Wire", "Face", "Shell", "Solid", "CompSolid", "Compound")
    TopoDS = SimpleNamespace(**{n: getattr(_TopoDS, n + "_s") for n in _DOWNCASTS if hasattr(_TopoDS, n + "_s")})

try:  # OCP < 8 / OCCT < 8.0
    from OCP.TColgp import TColgp_Array1OfPnt as TColgp_Array1OfPnt
    from OCP.TColgp import TColgp_Array1OfPnt2d as TColgp_Array1OfPnt2d
    from OCP.TColgp import TColgp_Array2OfPnt as TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger as TColStd_Array1OfInteger
    from OCP.TColStd import TColStd_Array1OfReal as TColStd_Array1OfReal
    from OCP.TColStd import TColStd_Array2OfReal as TColStd_Array2OfReal
except ImportError:  # OCP >= 8 / OCCT >= 8.0
    from OCP.collections import Array1_double as TColStd_Array1OfReal
    from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
    from OCP.collections import Array1_gp_Pnt2d as TColgp_Array1OfPnt2d
    from OCP.collections import Array1_int as TColStd_Array1OfInteger
    from OCP.collections import Array2_double as TColStd_Array2OfReal
    from OCP.collections import Array2_gp_Pnt as TColgp_Array2OfPnt

__all__ = [
    "TopoDS",
    "TColStd_Array1OfInteger",
    "TColStd_Array1OfReal",
    "TColStd_Array2OfReal",
    "TColgp_Array1OfPnt",
    "TColgp_Array1OfPnt2d",
    "TColgp_Array2OfPnt",
]
