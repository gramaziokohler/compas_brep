"""OCC ↔ compas_brep conversion functions.

All COMPAS↔OCC conversion logic lives here:
- ``occ_to_brep`` — OCC TopoDS_Shape → canonical Brep
- ``brep_to_occ`` — canonical Brep → OCC TopoDS_Shape
- Private helpers used by both directions and shared with other modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from compas.geometry import Line, Plane, Point, Vector
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.Geom import Geom_BSplineCurve, Geom_BSplineSurface, Geom_RectangularTrimmedSurface
from OCP.Geom2d import Geom2d_BSplineCurve
from OCP.Geom2dConvert import Geom2dConvert
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Plane
from OCP.GeomConvert import GeomConvert
from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt, gp_Pnt2d, gp_Vec  # noqa: F401
from OCP.ShapeConstruct import ShapeConstruct_Curve
from OCP.TColgp import TColgp_Array1OfPnt, TColgp_Array1OfPnt2d, TColgp_Array2OfPnt
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal, TColStd_Array2OfReal
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.TopoDS import TopoDS_Face as _TopoDS_Face
from OCP.TopoDS import TopoDS_Wire as _TopoDS_Wire

from compas_brep.backend.occ.topology import OccBrepEdge, OccBrepFace, OccBrepLoop, OccBrepTrim, OccBrepVertex
from compas_brep.curves.nurbs import NurbsCurve
from compas_brep.surfaces.nurbs import NurbsSurface

if TYPE_CHECKING:
    from OCP.TopoDS import TopoDS_Shape


# =============================================================================
# OCC → compas_brep conversion
# =============================================================================


def occ_to_brep(shape: TopoDS_Shape):
    """Wrap an OCC TopoDS_Shape in a compas_brep.Brep.

    Returns a thin Brep with ``_native_brep`` set but no topology extracted yet.
    Topology (vertices, edges, loops, faces) is populated lazily on first access
    via :func:`occ_extract_topology`.
    """
    from compas_brep.brep import Brep

    brep = Brep()
    brep._native_brep = shape
    return brep


def occ_extract_topology(brep) -> None:
    """Populate a Brep's topology lists in-place from its cached OCC native shape.

    Produces native-handle wrapper objects (OccBrepVertex, OccBrepEdge, etc.)
    that hold references to their underlying OCC entities. Geometric properties
    (.point, .curve, .surface, .curve_2d) are deferred to first access.

    Topology structure (which vertex is in which edge, which edge is in which
    loop, etc.) is fully determined here so that identity-based deduplication
    and traversal order are correct.
    """
    shape = brep._native_brep

    # Vertex deduplication: same OCC vertex hash → same OccBrepVertex instance
    vertex_map = {}  # hash(TopoDS_Vertex) -> OccBrepVertex

    def _get_vertex(occ_vertex):
        h = occ_vertex.__hash__()
        if h not in vertex_map:
            vertex_map[h] = OccBrepVertex(occ_vertex)
        return vertex_map[h]

    # Edge deduplication: same OCC edge (by IsSame) → same OccBrepEdge instance
    edge_registry = []  # list of (occ_edge, OccBrepEdge)

    all_faces = []
    all_edges = []
    all_loops = []

    # Iterate faces
    face_exp = TopExp_Explorer(shape, TopAbs_FACE)
    while face_exp.More():
        occ_face = TopoDS.Face_s(face_exp.Current())
        face_reversed = occ_face.Orientation() == TopAbs_REVERSED

        # Extract wire loops
        face_loops = []
        wire_exp = TopExp_Explorer(occ_face, TopAbs_WIRE)
        while wire_exp.More():
            occ_wire = TopoDS.Wire_s(wire_exp.Current())

            loop_trims = []
            wire_explorer = BRepTools_WireExplorer(occ_wire, occ_face)
            while wire_explorer.More():
                occ_edge = wire_explorer.Current()

                # Edge orientation: REVERSED means this usage traverses backward
                edge_reversed = occ_edge.Orientation() == TopAbs_REVERSED

                # Get the vertices in canonical (FORWARD) order using TopExp.
                # cumOri=False gives the underlying edge's natural direction,
                # independent of the orientation flag.
                try:
                    occ_first = TopExp.FirstVertex_s(occ_edge, False)
                    occ_last = TopExp.LastVertex_s(occ_edge, False)
                    start_v = _get_vertex(occ_first)
                    end_v = _get_vertex(occ_last)
                except Exception:
                    # Fallback for degenerate edges
                    v_exp = TopExp_Explorer(occ_edge, TopAbs_VERTEX)
                    edge_verts = []
                    while v_exp.More():
                        edge_verts.append(_get_vertex(TopoDS.Vertex_s(v_exp.Current())))
                        v_exp.Next()
                    if len(edge_verts) < 1:
                        wire_explorer.Next()
                        continue
                    elif len(edge_verts) < 2:
                        start_v = end_v = edge_verts[0]
                    else:
                        start_v, end_v = edge_verts[0], edge_verts[1]

                # Shared edge deduplication via IsSame
                brep_edge = None
                for reg_occ_edge, reg_brep_edge in edge_registry:
                    if occ_edge.IsSame(reg_occ_edge):
                        brep_edge = reg_brep_edge
                        break
                if brep_edge is None:
                    brep_edge = OccBrepEdge(occ_edge, start_v, end_v)
                    edge_registry.append((occ_edge, brep_edge))
                    all_edges.append(brep_edge)

                # Trim wraps oriented edge on this face; pcurve is deferred
                trim = OccBrepTrim(
                    occ_edge=occ_edge,
                    occ_face=occ_face,
                    brep_edge=brep_edge,
                    is_reversed=edge_reversed,
                )
                loop_trims.append(trim)

                wire_explorer.Next()

            if loop_trims:
                loop = OccBrepLoop(occ_wire=occ_wire, trims=loop_trims)
                face_loops.append(loop)
                all_loops.append(loop)

            wire_exp.Next()

        # First loop is outer, rest are inner; surface is deferred
        if face_loops:
            brep_face = OccBrepFace(
                occ_face=occ_face,
                outer_loop=face_loops[0],
                inner_loops=face_loops[1:],
                is_reversed=face_reversed,
            )
            all_faces.append(brep_face)

        face_exp.Next()

    brep._vertices = list(vertex_map.values())
    brep._edges = all_edges
    brep._loops = all_loops
    brep._faces = all_faces


def _extract_pcurve(occ_edge, occ_face):
    """Extract the 2D parametric curve (pcurve) of an edge on a face.

    Returns a NurbsCurve with 2D control points (z=0) representing the
    curve in the face surface's UV parameter space, or None if extraction fails.

    Handles both BSpline and Line 2D curves from OCC.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Curve as _BRepAdaptor_Curve
    from OCP.Geom2d import Geom2d_Line as _Geom2d_Line

    try:
        # Get parameter range from the 3D curve
        adaptor = _BRepAdaptor_Curve(occ_edge)
        first_param = adaptor.FirstParameter()
        last_param = adaptor.LastParameter()

        # Get the 2D pcurve
        curve_2d = BRep_Tool.CurveOnSurface_s(occ_edge, occ_face, first_param, last_param)
        if curve_2d is None:
            return None

        # Handle Geom2d_Line: create degree-1 NurbsCurve from endpoints.
        # Knots must match the 3D edge parameter range so OCC can reconstruct
        # the pcurve with correct parameterization.
        if isinstance(curve_2d, _Geom2d_Line):
            p0 = curve_2d.Value(first_param)
            p1 = curve_2d.Value(last_param)
            return NurbsCurve.from_parameters(
                points=[Point(p0.X(), p0.Y(), 0.0), Point(p1.X(), p1.Y(), 0.0)],
                weights=[1.0, 1.0],
                knots=[first_param, last_param],
                mults=[2, 2],
                degree=1,
            )

        # Convert other 2D curve types to BSpline
        try:
            bspline_2d = Geom2dConvert.CurveToBSplineCurve_s(curve_2d)
        except Exception:
            # Fallback: evaluate endpoints and make a line
            try:
                p0 = curve_2d.Value(first_param)
                p1 = curve_2d.Value(last_param)
                return NurbsCurve.from_parameters(
                    points=[Point(p0.X(), p0.Y(), 0.0), Point(p1.X(), p1.Y(), 0.0)],
                    weights=[1.0, 1.0],
                    knots=[first_param, last_param],
                    mults=[2, 2],
                    degree=1,
                )
            except Exception:
                return None

        if bspline_2d is None:
            return None

        # Handle periodic curves
        if bspline_2d.IsPeriodic():
            bspline_2d.SetNotPeriodic()

        # Trim to the edge's parameter range if needed
        knot_first = bspline_2d.Knot(1)
        knot_last = bspline_2d.Knot(bspline_2d.NbKnots())
        if first_param > knot_first + 1e-10 or last_param < knot_last - 1e-10:
            try:
                bspline_2d.Segment(first_param, last_param)
            except Exception:
                pass  # Use the full curve if segmentation fails

        # Extract as a NurbsCurve with 2D points (z=0)
        n_poles = bspline_2d.NbPoles()
        points = []
        weights = []
        for i in range(1, n_poles + 1):
            p = bspline_2d.Pole(i)
            points.append(Point(p.X(), p.Y(), 0.0))
            weights.append(bspline_2d.Weight(i))

        knots = []
        mults = []
        for i in range(1, bspline_2d.NbKnots() + 1):
            knots.append(bspline_2d.Knot(i))
            mults.append(bspline_2d.Multiplicity(i))

        return NurbsCurve.from_parameters(
            points=points,
            weights=weights,
            knots=knots,
            mults=mults,
            degree=bspline_2d.Degree(),
        )
    except Exception:
        return None


def _extract_surface(occ_face):
    """Extract surface data from an OCC face, returning Plane or NurbsSurface."""
    adaptor = BRepAdaptor_Surface(occ_face)
    stype = adaptor.GetType()

    if stype == GeomAbs_Plane:
        pln = adaptor.Plane()
        loc = pln.Location()
        ax_dir = pln.Axis().Direction()
        return Plane(
            Point(loc.X(), loc.Y(), loc.Z()),
            Vector(ax_dir.X(), ax_dir.Y(), ax_dir.Z()),
        )

    # For non-planar surfaces, convert to BSpline
    surface_handle = BRep_Tool.Surface_s(occ_face)
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(occ_face)

    # Trim infinite surfaces to face bounds
    trimmed = Geom_RectangularTrimmedSurface(surface_handle, umin, umax, vmin, vmax)
    bspline = GeomConvert.SurfaceToBSplineSurface_s(trimmed)

    return _bspline_surface_to_nurbs(bspline)


def _bspline_surface_to_nurbs(bspline):
    """Convert an OCC Geom_BSplineSurface to a compas_brep NurbsSurface.

    Converts periodic B-splines to non-periodic open form first, so that
    the resulting NurbsSurface has a correct domain that covers the full range.
    """
    if bspline.IsUPeriodic():
        bspline.SetUNotPeriodic()
    if bspline.IsVPeriodic():
        bspline.SetVNotPeriodic()
    nu = bspline.NbUPoles()
    nv = bspline.NbVPoles()

    points = []
    weights = []
    for i in range(1, nu + 1):
        row_pts = []
        row_wts = []
        for j in range(1, nv + 1):
            p = bspline.Pole(i, j)
            row_pts.append(Point(p.X(), p.Y(), p.Z()))
            row_wts.append(bspline.Weight(i, j))
        points.append(row_pts)
        weights.append(row_wts)

    knots_u = []
    mults_u = []
    for i in range(1, bspline.NbUKnots() + 1):
        knots_u.append(bspline.UKnot(i))
        mults_u.append(bspline.UMultiplicity(i))

    knots_v = []
    mults_v = []
    for i in range(1, bspline.NbVKnots() + 1):
        knots_v.append(bspline.VKnot(i))
        mults_v.append(bspline.VMultiplicity(i))

    return NurbsSurface.from_parameters(
        points=points,
        weights=weights,
        knots_u=knots_u,
        knots_v=knots_v,
        mults_u=mults_u,
        mults_v=mults_v,
        degree_u=bspline.UDegree(),
        degree_v=bspline.VDegree(),
    )


def _extract_edge_curve(occ_edge):
    """Extract 3D curve from an OCC edge, returning Line or NurbsCurve."""
    adaptor = BRepAdaptor_Curve(occ_edge)
    ctype = adaptor.GetType()

    if ctype == GeomAbs_Line:
        first = adaptor.Value(adaptor.FirstParameter())
        last = adaptor.Value(adaptor.LastParameter())
        return Line(
            Point(first.X(), first.Y(), first.Z()),
            Point(last.X(), last.Y(), last.Z()),
        )

    # For circles, BSplines, and other curve types, convert to BSpline
    first_param = adaptor.FirstParameter()
    last_param = adaptor.LastParameter()

    curve_handle = BRep_Tool.Curve_s(occ_edge, first_param, last_param)
    if curve_handle is None:
        first = adaptor.Value(first_param)
        last = adaptor.Value(last_param)
        return Line(
            Point(first.X(), first.Y(), first.Z()),
            Point(last.X(), last.Y(), last.Z()),
        )

    try:
        sc = ShapeConstruct_Curve()
        bspline = sc.ConvertToBSpline(curve_handle, first_param, last_param, 1e-6)
        if bspline is not None:
            return _bspline_curve_to_nurbs(bspline)
    except Exception:
        pass

    try:
        bspline = GeomConvert.CurveToBSplineCurve_s(curve_handle)
        return _bspline_curve_to_nurbs(bspline)
    except Exception:
        pass

    # Fallback to line approximation
    first = adaptor.Value(first_param)
    last = adaptor.Value(last_param)
    return Line(
        Point(first.X(), first.Y(), first.Z()),
        Point(last.X(), last.Y(), last.Z()),
    )


def _bspline_curve_to_nurbs(bspline):
    """Convert an OCC Geom_BSplineCurve to a compas_brep NurbsCurve.

    Converts periodic B-splines to non-periodic open form first.
    """
    if bspline.IsPeriodic():
        bspline.SetNotPeriodic()
    n_poles = bspline.NbPoles()

    points = []
    weights = []
    for i in range(1, n_poles + 1):
        p = bspline.Pole(i)
        points.append(Point(p.X(), p.Y(), p.Z()))
        weights.append(bspline.Weight(i))

    knots = []
    mults = []
    for i in range(1, bspline.NbKnots() + 1):
        knots.append(bspline.Knot(i))
        mults.append(bspline.Multiplicity(i))

    return NurbsCurve.from_parameters(
        points=points,
        weights=weights,
        knots=knots,
        mults=mults,
        degree=bspline.Degree(),
    )


# =============================================================================
# compas_brep ↔ STEP-inspired JSON serialization
# =============================================================================


def occ_brep_to_data(brep) -> dict:
    """Extract a STEP-inspired JSON dict from a native OCC shape.

    Entity types mirror STEP semantics: vertices (CARTESIAN_POINT), edges
    (EDGE_CURVE with 3D curve + vertex refs), faces (FACE_SURFACE with surface +
    oriented loops + pcurves).
    """
    from compas.geometry import Line, Plane

    shape = brep._native_brep

    # --- Vertices ---
    vertex_list = []
    vertex_id_map = {}  # occ_hash -> list index

    def _vertex_id(occ_vertex):
        h = occ_vertex.__hash__()
        if h not in vertex_id_map:
            pnt = BRep_Tool.Pnt_s(occ_vertex)
            vertex_list.append([pnt.X(), pnt.Y(), pnt.Z()])
            vertex_id_map[h] = len(vertex_list) - 1
        return vertex_id_map[h]

    # Pre-populate all vertices so isolated ones are also captured
    v_exp = TopExp_Explorer(shape, TopAbs_VERTEX)
    while v_exp.More():
        _vertex_id(TopoDS.Vertex_s(v_exp.Current()))
        v_exp.Next()

    # --- Edges ---
    edge_list = []
    edge_registry = []  # (occ_edge, index) for IsSame deduplication

    def _edge_id(occ_edge):
        for reg_edge, idx in edge_registry:
            if occ_edge.IsSame(reg_edge):
                return idx

        try:
            occ_first = TopExp.FirstVertex_s(occ_edge, False)
            occ_last = TopExp.LastVertex_s(occ_edge, False)
            start_id = _vertex_id(occ_first)
            end_id = _vertex_id(occ_last)
        except Exception:
            exp = TopExp_Explorer(occ_edge, TopAbs_VERTEX)
            verts = []
            while exp.More():
                verts.append(TopoDS.Vertex_s(exp.Current()))
                exp.Next()
            if not verts:
                start_id = end_id = 0
            elif len(verts) < 2:
                start_id = end_id = _vertex_id(verts[0])
            else:
                start_id = _vertex_id(verts[0])
                end_id = _vertex_id(verts[1])

        curve = _extract_edge_curve(occ_edge)
        if isinstance(curve, Line):
            curve_data = {
                "type": "line",
                "data": [
                    [curve.start.x, curve.start.y, curve.start.z],
                    [curve.end.x, curve.end.y, curve.end.z],
                ],
            }
        else:
            curve_data = {"type": "nurbs", "data": curve.__data__}

        idx = len(edge_list)
        edge_list.append({"start": start_id, "end": end_id, "curve": curve_data})
        edge_registry.append((occ_edge, idx))
        return idx

    # --- Faces ---
    face_list = []

    face_exp = TopExp_Explorer(shape, TopAbs_FACE)
    while face_exp.More():
        occ_face = TopoDS.Face_s(face_exp.Current())
        is_reversed = occ_face.Orientation() == TopAbs_REVERSED

        surface = _extract_surface(occ_face)
        if isinstance(surface, Plane):
            surface_data = {
                "type": "plane",
                "data": {
                    "point": [surface.point.x, surface.point.y, surface.point.z],
                    "normal": [surface.normal.x, surface.normal.y, surface.normal.z],
                },
            }
        else:
            surface_data = {"type": "nurbs", "data": surface.__data__}

        loops = []
        wire_exp = TopExp_Explorer(occ_face, TopAbs_WIRE)
        while wire_exp.More():
            occ_wire = TopoDS.Wire_s(wire_exp.Current())
            trims = []
            wire_explorer = BRepTools_WireExplorer(occ_wire, occ_face)
            while wire_explorer.More():
                occ_edge = wire_explorer.Current()
                edge_reversed = occ_edge.Orientation() == TopAbs_REVERSED
                edge_idx = _edge_id(occ_edge)

                pcurve = _extract_pcurve(occ_edge, occ_face)
                trims.append(
                    {
                        "edge": edge_idx,
                        "is_reversed": edge_reversed,
                        "curve_2d": pcurve.__data__ if pcurve is not None else None,
                    }
                )
                wire_explorer.Next()

            if trims:
                loops.append(trims)
            wire_exp.Next()

        if loops:
            face_list.append(
                {
                    "surface": surface_data,
                    "is_reversed": is_reversed,
                    "loops": loops,
                }
            )

        face_exp.Next()

    return {
        "version": 4,
        "vertices": vertex_list,
        "edges": edge_list,
        "faces": face_list,
    }


# =============================================================================
# compas_brep → OCC conversion
# =============================================================================


def brep_to_occ(brep) -> TopoDS_Shape:
    """Convert a canonical compas_brep.Brep to an OCC TopoDS_Shape.

    If the brep has a cached native shape that is not dirty, returns it directly.
    Reconstructs properly trimmed faces from edge curves for both planar and
    NURBS surfaces, and caches native faces on each BrepFace for tessellation.
    """
    if brep._native_brep is not None:
        return brep._native_brep

    sewing = BRepBuilderAPI_Sewing(1e-6)

    for face in brep._faces:
        surface = face.surface

        if isinstance(surface, Plane):
            pln = gp_Pln(
                gp_Pnt(surface.point.x, surface.point.y, surface.point.z),
                gp_Dir(surface.normal.x, surface.normal.y, surface.normal.z),
            )

            # Build outer wire from edge curves (handles both polygon and curved boundaries)
            outer_wire = _loop_to_occ_wire(face.outer_loop)
            if outer_wire is None:
                # Fallback to vertex-based wire for simple polygons
                points = [v.point for v in face.outer_loop.vertices]
                outer_wire = _points_to_occ_wire(points)
            occ_face = BRepBuilderAPI_MakeFace(pln, outer_wire).Face()

            for inner_loop in face._inner_loops:
                inner_wire = _loop_to_occ_wire(inner_loop)
                if inner_wire is None:
                    inner_points = [v.point for v in inner_loop.vertices]
                    inner_wire = _points_to_occ_wire(inner_points)
                occ_face = BRepBuilderAPI_MakeFace(occ_face, inner_wire).Face()

        elif isinstance(surface, NurbsSurface):
            occ_surface = _nurbs_surface_to_occ(surface)
            occ_face = _build_nurbs_face(occ_surface, face)
        else:
            continue

        sewing.Add(occ_face)

    sewing.Perform()
    shape = sewing.SewedShape()

    brep._native_brep = shape
    return shape


def _points_to_occ_wire(points):
    """Create an OCC wire from a list of 3D points (closed polygon)."""
    wire_builder = BRepBuilderAPI_MakeWire()
    n = len(points)
    for i in range(n):
        p0 = points[i]
        p1 = points[(i + 1) % n]
        edge = BRepBuilderAPI_MakeEdge(
            gp_Pnt(p0.x, p0.y, p0.z),
            gp_Pnt(p1.x, p1.y, p1.z),
        ).Edge()
        wire_builder.Add(edge)
    return wire_builder.Wire()


def _pcurve_to_geom2d(pcurve):
    """Convert a compas_brep NurbsCurve (2D, z=0) to an OCC Geom2d_BSplineCurve."""
    pts = pcurve._points
    wts = pcurve._weights
    n = len(pts)
    poles = TColgp_Array1OfPnt2d(1, n)
    weights = TColStd_Array1OfReal(1, n)
    for i in range(n):
        poles.SetValue(i + 1, gp_Pnt2d(pts[i].x, pts[i].y))
        weights.SetValue(i + 1, wts[i])
    knots = TColStd_Array1OfReal(1, len(pcurve._knots))
    mults = TColStd_Array1OfInteger(1, len(pcurve._mults))
    for i, k in enumerate(pcurve._knots):
        knots.SetValue(i + 1, k)
    for i, m in enumerate(pcurve._mults):
        mults.SetValue(i + 1, m)
    return Geom2d_BSplineCurve(poles, weights, knots, mults, pcurve._degree)


def _build_nurbs_face(occ_surface, face):
    """Build an OCC face from a NURBS surface with pcurve-based trimming.

    Constructs edges with pcurves attached so that OCC correctly handles
    periodic surfaces (e.g. cylinders) where 3D wire-only reconstruction
    is ambiguous.

    Falls back to domain-bounded or wire-based construction when pcurves
    are not available.
    """
    from OCP.BRep import BRep_Builder as _BRep_Builder

    builder = _BRep_Builder()

    # Check if all trims have pcurves
    all_have_pcurves = (
        all(t.curve_2d is not None for loop in face.loops for t in loop.trims) if face.outer_loop.trims else False
    )

    if all_have_pcurves:
        # Build face with explicit pcurve-based trimming
        occ_face = _TopoDS_Face()
        builder.MakeFace(occ_face, occ_surface, 1e-6)

        for loop_idx, loop in enumerate(face.loops):
            wire = _TopoDS_Wire()
            builder.MakeWire(wire)

            for trim in loop.trims:
                edge = trim.edge
                curve = edge.curve
                sp = edge.first_vertex.point
                ep = edge.last_vertex.point
                p0 = gp_Pnt(sp.x, sp.y, sp.z)
                p1 = gp_Pnt(ep.x, ep.y, ep.z)
                dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5

                if isinstance(curve, NurbsCurve):
                    occ_curve = _nurbs_curve_to_occ(curve)
                    occ_edge = BRepBuilderAPI_MakeEdge(occ_curve).Edge()
                elif dist < 1e-9:
                    continue
                else:
                    occ_edge = BRepBuilderAPI_MakeEdge(p0, p1).Edge()

                # Attach pcurve to this face
                geom2d = _pcurve_to_geom2d(trim.curve_2d)
                builder.UpdateEdge(occ_edge, geom2d, occ_face, 1e-6)

                if trim.is_reversed:
                    occ_edge.Reverse()

                builder.Add(wire, occ_edge)

            builder.Add(occ_face, wire)

        return occ_face

    # Fallback: use domain bounds for untrimmed faces
    du = face.domain_u or face.surface.domain_u
    dv = face.domain_v or face.surface.domain_v
    if du is not None and dv is not None:
        return BRepBuilderAPI_MakeFace(occ_surface, du[0], du[1], dv[0], dv[1], 1e-6).Face()

    # Last resort: untrimmed face from surface
    return BRepBuilderAPI_MakeFace(occ_surface, 1e-6).Face()


def _loop_to_occ_wire(loop):
    """Create an OCC wire from a BrepLoop's trims or edge curves.

    When trims are present, respects edge orientation (is_reversed).
    Converts each edge's curve (NurbsCurve or Line) to an OCC edge and
    assembles them into a wire. Returns None if the wire cannot be built.
    """
    wire_builder = BRepBuilderAPI_MakeWire()

    if loop.trims:
        for trim in loop.trims:
            edge = trim.edge
            curve = edge.curve
            sp = edge.first_vertex.point
            ep = edge.last_vertex.point
            p0 = gp_Pnt(sp.x, sp.y, sp.z)
            p1 = gp_Pnt(ep.x, ep.y, ep.z)
            dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5

            if isinstance(curve, NurbsCurve):
                occ_curve = _nurbs_curve_to_occ(curve)
                occ_edge = BRepBuilderAPI_MakeEdge(occ_curve).Edge()
            elif dist < 1e-9:
                continue  # Degenerate edge
            elif isinstance(curve, Line):
                occ_edge = BRepBuilderAPI_MakeEdge(p0, p1).Edge()
            else:
                occ_edge = BRepBuilderAPI_MakeEdge(p0, p1).Edge()

            # Apply orientation from trim
            if trim.is_reversed:
                occ_edge.Reverse()

            wire_builder.Add(occ_edge)
    else:
        # Legacy path: direct edges
        for edge in loop.edges:
            curve = edge.curve
            sp = edge.first_vertex.point
            ep = edge.last_vertex.point
            p0 = gp_Pnt(sp.x, sp.y, sp.z)
            p1 = gp_Pnt(ep.x, ep.y, ep.z)
            dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5

            if isinstance(curve, NurbsCurve):
                occ_curve = _nurbs_curve_to_occ(curve)
                occ_edge = BRepBuilderAPI_MakeEdge(occ_curve).Edge()
            elif dist < 1e-9:
                continue
            elif isinstance(curve, Line):
                occ_edge = BRepBuilderAPI_MakeEdge(p0, p1).Edge()
            else:
                occ_edge = BRepBuilderAPI_MakeEdge(p0, p1).Edge()

            wire_builder.Add(occ_edge)

    if not wire_builder.IsDone():
        return None
    return wire_builder.Wire()


def _nurbs_surface_to_occ(surface: NurbsSurface):
    """Convert a compas_brep NurbsSurface to an OCC Geom_BSplineSurface."""
    points = surface._points
    weights_data = surface._weights
    nu = len(points)
    nv = len(points[0])

    poles = TColgp_Array2OfPnt(1, nu, 1, nv)
    for i in range(nu):
        for j in range(nv):
            p = points[i][j]
            poles.SetValue(i + 1, j + 1, gp_Pnt(p.x, p.y, p.z))

    occ_weights = TColStd_Array2OfReal(1, nu, 1, nv)
    for i in range(nu):
        for j in range(nv):
            occ_weights.SetValue(i + 1, j + 1, weights_data[i][j])

    knots_u = surface._knots_u
    mults_u = surface._mults_u
    occ_uknots = TColStd_Array1OfReal(1, len(knots_u))
    occ_umults = TColStd_Array1OfInteger(1, len(mults_u))
    for i, k in enumerate(knots_u):
        occ_uknots.SetValue(i + 1, k)
    for i, m in enumerate(mults_u):
        occ_umults.SetValue(i + 1, m)

    knots_v = surface._knots_v
    mults_v = surface._mults_v
    occ_vknots = TColStd_Array1OfReal(1, len(knots_v))
    occ_vmults = TColStd_Array1OfInteger(1, len(mults_v))
    for i, k in enumerate(knots_v):
        occ_vknots.SetValue(i + 1, k)
    for i, m in enumerate(mults_v):
        occ_vmults.SetValue(i + 1, m)

    return Geom_BSplineSurface(
        poles,
        occ_weights,
        occ_uknots,
        occ_vknots,
        occ_umults,
        occ_vmults,
        surface._degree_u,
        surface._degree_v,
    )


def _nurbs_curve_to_occ(curve: NurbsCurve):
    """Convert a compas_brep NurbsCurve to an OCC Geom_BSplineCurve."""
    points = curve._points
    weights_data = curve._weights
    n = len(points)

    poles = TColgp_Array1OfPnt(1, n)
    occ_weights = TColStd_Array1OfReal(1, n)
    for i in range(n):
        p = points[i]
        poles.SetValue(i + 1, gp_Pnt(p.x, p.y, p.z))
        occ_weights.SetValue(i + 1, weights_data[i])

    knots = curve._knots
    mults = curve._mults
    occ_knots = TColStd_Array1OfReal(1, len(knots))
    occ_mults = TColStd_Array1OfInteger(1, len(mults))
    for i, k in enumerate(knots):
        occ_knots.SetValue(i + 1, k)
    for i, m in enumerate(mults):
        occ_mults.SetValue(i + 1, m)

    return Geom_BSplineCurve(
        poles,
        occ_weights,
        occ_knots,
        occ_mults,
        curve._degree,
    )


def _frame_to_ax2(frame):
    """Convert a COMPAS Frame to an OCC gp_Ax2."""
    origin = frame.point
    zaxis = frame.zaxis
    xaxis = frame.xaxis
    return gp_Ax2(
        gp_Pnt(origin.x, origin.y, origin.z),
        gp_Dir(zaxis.x, zaxis.y, zaxis.z),
        gp_Dir(xaxis.x, xaxis.y, xaxis.z),
    )
