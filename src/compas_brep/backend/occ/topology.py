"""OCC native-handle wrappers for Brep topology sub-objects.

Each class holds a reference to a native OCC entity as primary state.
Geometric properties (.point, .curve, .surface, .curve_2d) are computed
lazily on first access and cached on the instance. No OCC types are
exposed through the public interface — all return values are COMPAS types.
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


class OccBrepVertex(BrepVertex):
    """BrepVertex backed by a native TopoDS_Vertex handle."""

    def __init__(self, occ_vertex: Any) -> None:
        self._occ_vertex = occ_vertex
        self._point: Point | None = None

    @property
    def native_vertex(self) -> Any:
        return self._occ_vertex

    @property
    def point(self) -> Point:
        if self._point is None:
            from OCP.BRep import BRep_Tool

            pnt = BRep_Tool.Pnt_s(self._occ_vertex)
            self._point = Point(pnt.X(), pnt.Y(), pnt.Z())
        return self._point

    def __repr__(self) -> str:
        return f"OccBrepVertex({self._point})"


class OccBrepEdge(BrepEdge):
    """BrepEdge backed by a native TopoDS_Edge handle."""

    def __init__(self, occ_edge: Any, start_vertex: OccBrepVertex, end_vertex: OccBrepVertex) -> None:
        self._occ_edge = occ_edge
        self._start = start_vertex
        self._end = end_vertex
        self._curve: Any = None

    @property
    def native_edge(self) -> Any:
        return self._occ_edge

    @property
    def curve(self) -> Any:
        if self._curve is None:
            from .conversion import _extract_edge_curve

            self._curve = _extract_edge_curve(self._occ_edge)
        return self._curve

    @curve.setter
    def curve(self, value: Any) -> None:
        self._curve = value

    def __repr__(self) -> str:
        curve_type = "line" if self.is_line else "nurbs"
        return f"OccBrepEdge({self._start} -> {self._end}, {curve_type})"


class OccBrepTrim(BrepTrim):
    """BrepTrim backed by a native oriented TopoDS_Edge on a TopoDS_Face."""

    def __init__(
        self,
        occ_edge: Any,
        occ_face: Any,
        brep_edge: OccBrepEdge,
        is_reversed: bool,
    ) -> None:
        self._occ_edge = occ_edge
        self._occ_face = occ_face
        self._edge = brep_edge
        self._is_reversed = is_reversed
        self._curve_2d: NurbsCurve | None = None

    @property
    def native_trim(self) -> Any:
        return self._occ_edge

    @property
    def curve_2d(self) -> NurbsCurve | None:
        if self._curve_2d is None:
            from .conversion import _extract_pcurve

            self._curve_2d = _extract_pcurve(self._occ_edge, self._occ_face)
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
        return f"OccBrepTrim({self.start_vertex.point} -> {self.end_vertex.point}{rev}{pcurve})"


class OccBrepLoop(BrepLoop):
    """BrepLoop backed by a native TopoDS_Wire handle."""

    def __init__(self, occ_wire: Any, trims: list[OccBrepTrim]) -> None:
        self._occ_wire = occ_wire
        self._trims = list(trims)
        self._edges: list[BrepEdge] = []

    @property
    def native_loop(self) -> Any:
        return self._occ_wire

    def __repr__(self) -> str:
        return f"OccBrepLoop({len(self._trims)} trims)"


class OccBrepFace(BrepFace):
    """BrepFace backed by a native TopoDS_Face handle."""

    def __init__(
        self,
        occ_face: Any,
        outer_loop: OccBrepLoop,
        inner_loops: list[OccBrepLoop],
        is_reversed: bool,
    ) -> None:
        self._occ_face = occ_face
        self._outer_loop = outer_loop
        self._inner_loops = list(inner_loops)
        self._is_reversed = is_reversed
        self._surface: Any = None
        self._domain_u: tuple[float, float] | None = None
        self._domain_v: tuple[float, float] | None = None

    @property
    def native_face(self) -> Any:
        return self._occ_face

    @property
    def surface(self) -> Any:
        if self._surface is None:
            from .conversion import _extract_surface

            self._surface = _extract_surface(self._occ_face)
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
        from OCP.BRepTools import BRepTools

        umin, umax, vmin, vmax = BRepTools.UVBounds_s(self._occ_face)
        self._domain_u = (umin, umax)
        self._domain_v = (vmin, vmax)

    def __repr__(self) -> str:
        surface_type = "plane" if self.is_planar else "nurbs"
        return f"OccBrepFace({len(self.vertices)} vertices, {surface_type})"
