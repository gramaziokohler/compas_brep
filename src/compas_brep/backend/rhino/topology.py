"""Rhino native-handle wrappers for Brep topology sub-objects.

Each class holds a reference to a native Rhino.Geometry entity as primary state.
Geometric properties (.point, .curve, .surface, .curve_2d) are computed lazily
on first access and cached on the instance. No Rhino types are exposed through
the public interface — all return values are COMPAS types.
"""

from __future__ import annotations

from typing import Any

from compas.geometry import Point

from compas_brep.curves import NurbsCurve
from compas_brep.edge import BrepEdge
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.trim import BrepTrim
from compas_brep.vertex import BrepVertex


class RhinoBrepVertex(BrepVertex):
    """BrepVertex backed by a native Rhino.Geometry.BrepVertex handle."""

    def __init__(self, rhino_vertex: Any) -> None:
        self._rhino_vertex = rhino_vertex
        self._point: Point | None = None

    @property
    def native_vertex(self) -> Any:
        return self._rhino_vertex

    @property
    def point(self) -> Point:
        if self._point is None:
            pt = self._rhino_vertex.Location
            self._point = Point(pt.X, pt.Y, pt.Z)
        return self._point

    def __repr__(self) -> str:
        return f"RhinoBrepVertex({self._point})"


class RhinoBrepEdge(BrepEdge):
    """BrepEdge backed by a native Rhino.Geometry.BrepEdge handle."""

    def __init__(self, rhino_edge: Any, start_vertex: RhinoBrepVertex, end_vertex: RhinoBrepVertex) -> None:
        self._rhino_edge = rhino_edge
        self._start = start_vertex
        self._end = end_vertex
        self._curve: Any = None

    @property
    def native_edge(self) -> Any:
        return self._rhino_edge

    @property
    def curve(self) -> Any:
        if self._curve is None:
            from .conversion import _extract_edge_curve

            self._curve = _extract_edge_curve(self._rhino_edge)
        return self._curve

    @curve.setter
    def curve(self, value: Any) -> None:
        self._curve = value

    def __repr__(self) -> str:
        curve_type = "line" if self.is_line else "nurbs"
        return f"RhinoBrepEdge({self._start} -> {self._end}, {curve_type})"


class RhinoBrepTrim(BrepTrim):
    """BrepTrim backed by a native Rhino.Geometry.BrepTrim handle."""

    def __init__(self, rhino_trim: Any, brep_edge: RhinoBrepEdge, is_reversed: bool) -> None:
        self._rhino_trim = rhino_trim
        self._edge = brep_edge
        self._is_reversed = is_reversed
        self._curve_2d: NurbsCurve | None = None

    @property
    def native_trim(self) -> Any:
        return self._rhino_trim

    @property
    def curve_2d(self) -> NurbsCurve | None:
        if self._curve_2d is None:
            self._curve_2d = _extract_trim_curve_2d(self._rhino_trim)
        return self._curve_2d

    @curve_2d.setter
    def curve_2d(self, value: NurbsCurve | None) -> None:
        self._curve_2d = value

    @property
    def curve(self) -> NurbsCurve | None:
        return self.curve_2d

    @curve.setter
    def curve(self, value: NurbsCurve | None) -> None:
        self._curve_2d = value

    @property
    def curve_3d(self) -> Any:
        return self._edge.curve

    def __repr__(self) -> str:
        rev = " reversed" if self._is_reversed else ""
        pcurve = " +pcurve" if self._curve_2d is not None else ""
        return f"RhinoBrepTrim({self.start_vertex.point} -> {self.end_vertex.point}{rev}{pcurve})"


class RhinoBrepLoop(BrepLoop):
    """BrepLoop backed by a native Rhino.Geometry.BrepLoop handle."""

    def __init__(self, rhino_loop: Any, trims: list[RhinoBrepTrim]) -> None:
        self._rhino_loop = rhino_loop
        self._trims = list(trims)
        self._edges: list[BrepEdge] = []

    @property
    def native_loop(self) -> Any:
        return self._rhino_loop

    def __repr__(self) -> str:
        return f"RhinoBrepLoop({len(self._trims)} trims)"


class RhinoBrepFace(BrepFace):
    """BrepFace backed by a native Rhino.Geometry.BrepFace handle."""

    def __init__(
        self,
        rhino_face: Any,
        outer_loop: RhinoBrepLoop,
        inner_loops: list[RhinoBrepLoop],
        is_reversed: bool,
    ) -> None:
        self._rhino_face = rhino_face
        self._outer_loop = outer_loop
        self._inner_loops = list(inner_loops)
        self._is_reversed = is_reversed
        self._surface: Any = None
        self._domain_u: tuple[float, float] | None = None
        self._domain_v: tuple[float, float] | None = None

    @property
    def native_face(self) -> Any:
        return self._rhino_face

    @property
    def surface(self) -> Any:
        if self._surface is None:
            from .conversion import _extract_surface

            self._surface = _extract_surface(self._rhino_face)
        return self._surface

    @surface.setter
    def surface(self, value: Any) -> None:
        self._surface = value

    @property
    def domain_u(self) -> tuple[float, float] | None:
        if self._domain_u is None:
            self._load_domain()
        return self._domain_u

    @property
    def domain_v(self) -> tuple[float, float] | None:
        if self._domain_v is None:
            self._load_domain()
        return self._domain_v

    def _load_domain(self) -> None:
        self._domain_u = (self._rhino_face.Domain(0)[0], self._rhino_face.Domain(0)[1])
        self._domain_v = (self._rhino_face.Domain(1)[0], self._rhino_face.Domain(1)[1])

    def __repr__(self) -> str:
        surface_type = "plane" if self.is_planar else "nurbs"
        return f"RhinoBrepFace({len(self.vertices)} vertices, {surface_type})"


def _extract_trim_curve_2d(rhino_trim: Any) -> NurbsCurve | None:
    """Extract the 2D parametric curve from a Rhino BrepTrim, returning NurbsCurve or None."""
    from .conversion import _rhino_nurbs_curve_to_compas

    curve = rhino_trim.TrimCurve
    if curve is None:
        return None
    nurbs = curve.ToNurbsCurve()
    if nurbs is None:
        return None
    return _rhino_nurbs_curve_to_compas(nurbs)
