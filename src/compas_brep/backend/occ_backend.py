"""OCC backend for compas_brep — converts between canonical Brep data and OCC shapes.

Uses cadquery-ocp-novtk for OCCT bindings. Provides:
- Primitive constructors (box, cylinder, sphere, cone, torus)
- Boolean operations (difference, union, intersection)
- Bidirectional conversion: brep_to_occ / occ_to_brep
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from compas.geometry import Frame, Line, Plane, Point, Vector

# OCC imports — this module is only loaded when OCP is available (via plugin requires=["OCP"])
from OCP.BRep import BRep_Tool  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepBuilderAPI import (  # noqa: E402
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepPrimAPI import (  # noqa: E402
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
    BRepPrimAPI_MakeTorus,
)
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer  # noqa: E402
from OCP.Geom import Geom_BSplineCurve, Geom_BSplineSurface, Geom_RectangularTrimmedSurface  # noqa: E402
from OCP.Geom2dConvert import Geom2dConvert  # noqa: E402
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Plane  # noqa: E402
from OCP.GeomConvert import GeomConvert  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt, gp_Vec  # noqa: E402
from OCP.ShapeConstruct import ShapeConstruct_Curve  # noqa: E402
from OCP.TColgp import TColgp_Array1OfPnt, TColgp_Array2OfPnt  # noqa: E402
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal, TColStd_Array2OfReal  # noqa: E402
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_VERTEX, TopAbs_WIRE  # noqa: E402
from OCP.TopExp import TopExp, TopExp_Explorer  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402

from compas_brep.curves.nurbs import NurbsCurve
from compas_brep.edge import BrepEdge
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.surfaces.nurbs import NurbsSurface
from compas_brep.trim import BrepTrim
from compas_brep.vertex import BrepVertex

if TYPE_CHECKING:
    from OCP.TopoDS import TopoDS_Shape


# =============================================================================
# OCC → compas_brep conversion
# =============================================================================


def occ_to_brep(shape: TopoDS_Shape):
    """Convert an OCC TopoDS_Shape to a canonical compas_brep.Brep.

    Extracts all NURBS surface data, edge curves, trim curves (pcurves),
    and topology from the OCC shape into Python-owned data structures.

    Inspired by STEP (ISO 10303-21): each edge usage in a loop becomes a
    BrepTrim (coedge) carrying an orientation flag and a 2D pcurve in the
    face surface's UV space. This allows kernel-independent tessellation
    and faithful round-trip serialization.
    """
    from compas_brep.brep import Brep

    # Collect all vertices with deduplication
    vertex_map = {}  # hash(TopoDS_Vertex) -> BrepVertex

    def _get_vertex(occ_vertex):
        h = occ_vertex.__hash__()
        if h not in vertex_map:
            pnt = BRep_Tool.Pnt_s(occ_vertex)
            vertex_map[h] = BrepVertex(Point(pnt.X(), pnt.Y(), pnt.Z()))
        return vertex_map[h]

    # Shared edge deduplication: same OCC edge (by IsSame) → same BrepEdge
    # Store as list of (occ_edge, BrepEdge) pairs and use IsSame for comparison
    edge_registry = []  # list of (occ_edge, BrepEdge)

    all_faces = []
    all_edges = []
    all_loops = []

    # Iterate faces
    face_exp = TopExp_Explorer(shape, TopAbs_FACE)
    while face_exp.More():
        occ_face = TopoDS.Face_s(face_exp.Current())
        face_reversed = occ_face.Orientation() == TopAbs_REVERSED

        # Extract surface
        surface = _extract_surface(occ_face)

        # Extract domain
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(occ_face)
        domain_u = (umin, umax)
        domain_v = (vmin, vmax)

        # Extract wire loops
        face_loops = []
        wire_exp = TopExp_Explorer(occ_face, TopAbs_WIRE)
        while wire_exp.More():
            occ_wire = TopoDS.Wire_s(wire_exp.Current())

            # Extract edges from wire in proper traversal order
            loop_trims = []
            wire_explorer = BRepTools_WireExplorer(occ_wire, occ_face)
            while wire_explorer.More():
                occ_edge = wire_explorer.Current()

                # Edge orientation: REVERSED means this usage traverses backward
                edge_reversed = occ_edge.Orientation() == TopAbs_REVERSED

                # Extract 3D edge curve (in the edge's canonical direction)
                curve = _extract_edge_curve(occ_edge)

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
                    brep_edge = BrepEdge(start_v, end_v, curve=curve)
                    edge_registry.append((occ_edge, brep_edge))
                    all_edges.append(brep_edge)

                # Extract pcurve (2D curve in face UV space)
                pcurve = _extract_pcurve(occ_edge, occ_face)

                trim = BrepTrim(
                    edge=brep_edge,
                    is_reversed=edge_reversed,
                    curve_2d=pcurve,
                )
                loop_trims.append(trim)

                wire_explorer.Next()

            if loop_trims:
                loop = BrepLoop(trims=loop_trims)
                face_loops.append(loop)
                all_loops.append(loop)

            wire_exp.Next()

        # First loop is outer, rest are inner
        if face_loops:
            brep_face = BrepFace(
                face_loops[0],
                surface=surface,
                is_reversed=face_reversed,
                domain_u=domain_u,
                domain_v=domain_v,
            )
            for inner_loop in face_loops[1:]:
                brep_face.add_loop(inner_loop)
            brep_face._native_face = occ_face  # cache for tessellation
            all_faces.append(brep_face)

        face_exp.Next()

    # Build Brep
    brep = Brep()
    brep._vertices = list(vertex_map.values())
    brep._edges = all_edges
    brep._loops = all_loops
    brep._faces = all_faces
    brep._native_brep = shape
    brep._native_dirty = False
    return brep


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

        # Handle Geom2d_Line: create degree-1 NurbsCurve from endpoints
        if isinstance(curve_2d, _Geom2d_Line):
            p0 = curve_2d.Value(first_param)
            p1 = curve_2d.Value(last_param)
            return NurbsCurve.from_parameters(
                points=[Point(p0.X(), p0.Y(), 0.0), Point(p1.X(), p1.Y(), 0.0)],
                weights=[1.0, 1.0],
                knots=[0.0, 1.0],
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
                    knots=[0.0, 1.0],
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
# compas_brep → OCC conversion
# =============================================================================


def brep_to_occ(brep) -> TopoDS_Shape:
    """Convert a canonical compas_brep.Brep to an OCC TopoDS_Shape.

    If the brep has a cached native shape that is not dirty, returns it directly.
    Reconstructs properly trimmed faces from edge curves for both planar and
    NURBS surfaces, and caches native faces on each BrepFace for tessellation.
    """
    if brep._native_brep is not None and not brep._native_dirty:
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

            # Build outer wire from edge curves (preserves trim information)
            outer_wire = _loop_to_occ_wire(face.outer_loop)
            if outer_wire is not None:
                maker = BRepBuilderAPI_MakeFace(occ_surface, outer_wire, True)
                # Add inner wires (holes)
                for inner_loop in face._inner_loops:
                    inner_wire = _loop_to_occ_wire(inner_loop)
                    if inner_wire is not None:
                        maker.Add(inner_wire)
                occ_face = maker.Face()
            else:
                # Fallback: untrimmed face (shouldn't happen for valid data)
                occ_face = BRepBuilderAPI_MakeFace(occ_surface, 1e-6).Face()
        else:
            continue

        face._native_face = occ_face
        sewing.Add(occ_face)

    sewing.Perform()
    shape = sewing.SewedShape()

    brep._native_brep = shape
    brep._native_dirty = False
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


# =============================================================================
# Primitive constructors
# =============================================================================


def _frame_to_ax2(frame: Frame):
    """Convert a COMPAS Frame to an OCC gp_Ax2."""
    origin = frame.point
    zaxis = frame.zaxis
    xaxis = frame.xaxis
    return gp_Ax2(
        gp_Pnt(origin.x, origin.y, origin.z),
        gp_Dir(zaxis.x, zaxis.y, zaxis.z),
        gp_Dir(xaxis.x, xaxis.y, xaxis.z),
    )


def make_box(box):
    """Create a Brep from a COMPAS Box using OCC.

    COMPAS Box is centered at its frame. OCC's MakeBox builds from a corner point
    to (+xsize, +ysize, +zsize), so we offset the origin to the min corner.
    """
    frame = box.frame
    corner = (
        frame.point + frame.xaxis * (-box.xsize / 2) + frame.yaxis * (-box.ysize / 2) + frame.zaxis * (-box.zsize / 2)
    )
    ax2 = gp_Ax2(
        gp_Pnt(corner.x, corner.y, corner.z),
        gp_Dir(frame.zaxis.x, frame.zaxis.y, frame.zaxis.z),
        gp_Dir(frame.xaxis.x, frame.xaxis.y, frame.xaxis.z),
    )
    shape = BRepPrimAPI_MakeBox(ax2, box.xsize, box.ysize, box.zsize).Shape()
    return occ_to_brep(shape)


def make_cylinder(cylinder):
    """Create a Brep from a COMPAS Cylinder using OCC.

    COMPAS Cylinder is centered at its frame. OCC's MakeCylinder builds from
    the ax2 origin upward along the z-axis, so we offset to the bottom.
    """
    frame = cylinder.frame
    bottom = frame.point + frame.zaxis * (-cylinder.height / 2)
    ax2 = gp_Ax2(
        gp_Pnt(bottom.x, bottom.y, bottom.z),
        gp_Dir(frame.zaxis.x, frame.zaxis.y, frame.zaxis.z),
        gp_Dir(frame.xaxis.x, frame.xaxis.y, frame.xaxis.z),
    )
    shape = BRepPrimAPI_MakeCylinder(ax2, cylinder.radius, cylinder.height).Shape()
    return occ_to_brep(shape)


def make_sphere(sphere):
    """Create a Brep from a COMPAS Sphere using OCC."""
    center = sphere.frame.point
    shape = BRepPrimAPI_MakeSphere(gp_Pnt(center.x, center.y, center.z), sphere.radius).Shape()
    return occ_to_brep(shape)


def make_cone(cone):
    """Create a Brep from a COMPAS Cone using OCC."""
    ax2 = _frame_to_ax2(cone.frame)
    shape = BRepPrimAPI_MakeCone(ax2, cone.radius, 0.0, cone.height).Shape()
    return occ_to_brep(shape)


def make_torus(torus):
    """Create a Brep from a COMPAS Torus using OCC."""
    ax2 = _frame_to_ax2(torus.frame)
    shape = BRepPrimAPI_MakeTorus(ax2, torus.radius_axis, torus.radius_pipe).Shape()
    return occ_to_brep(shape)


# =============================================================================
# Boolean operations
# =============================================================================


def boolean_difference(brep_a, brep_b):
    """Boolean subtraction: A - B."""
    shape_a = brep_to_occ(brep_a)
    shape_b = brep_to_occ(brep_b)
    op = BRepAlgoAPI_Cut(shape_a, shape_b)
    return occ_to_brep(op.Shape())


def boolean_union(brep_a, brep_b):
    """Boolean union: A + B."""
    shape_a = brep_to_occ(brep_a)
    shape_b = brep_to_occ(brep_b)
    op = BRepAlgoAPI_Fuse(shape_a, shape_b)
    return occ_to_brep(op.Shape())


def boolean_intersection(brep_a, brep_b):
    """Boolean intersection: A & B."""
    shape_a = brep_to_occ(brep_a)
    shape_b = brep_to_occ(brep_b)
    op = BRepAlgoAPI_Common(shape_a, shape_b)
    return occ_to_brep(op.Shape())


# =============================================================================
# Other constructors
# =============================================================================


def make_from_mesh(mesh):
    """Create a Brep from a COMPAS Mesh by sewing polygon faces."""
    sewing = BRepBuilderAPI_Sewing(1e-6)

    for fkey in mesh.faces():
        vertices = mesh.face_vertices(fkey)
        points = [mesh.vertex_coordinates(v) for v in vertices]
        wire = _points_to_occ_wire([Point(*p) for p in points])
        face = BRepBuilderAPI_MakeFace(wire, True).Face()
        sewing.Add(face)

    sewing.Perform()
    return occ_to_brep(sewing.SewedShape())


def make_extrusion(curve_or_profile, vector, cap_ends=True):
    """Create a Brep by extruding a curve/profile along a vector."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism

    if hasattr(curve_or_profile, "points"):
        points = list(curve_or_profile.points)
        wire = _points_to_occ_wire(points)
    else:
        raise NotImplementedError("Extrusion currently supports polygon profiles only")

    face = BRepBuilderAPI_MakeFace(wire, True).Face()
    vec = gp_Vec(vector.x, vector.y, vector.z)
    shape = BRepPrimAPI_MakePrism(face, vec).Shape()
    return occ_to_brep(shape)


def make_loft(curves):
    """Create a Brep by lofting through curves."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections

    loft = BRepOffsetAPI_ThruSections(True)  # isSolid=True

    for curve in curves:
        if hasattr(curve, "points") and hasattr(curve, "_knots"):
            occ_curve = _nurbs_curve_to_occ(curve)
            edge = BRepBuilderAPI_MakeEdge(occ_curve).Edge()
            wire = BRepBuilderAPI_MakeWire(edge).Wire()
        elif hasattr(curve, "points"):
            points = list(curve.points)
            wire = _points_to_occ_wire(points)
        else:
            raise NotImplementedError(f"Unsupported curve type: {type(curve)}")
        loft.AddWire(wire)

    loft.Build()
    return occ_to_brep(loft.Shape())


def from_native(native_shape):
    """Create a Brep from a native OCC TopoDS_Shape."""
    return occ_to_brep(native_shape)


# =============================================================================
# Pluggable instance operations
# =============================================================================


def occ_trimmed(brep, plane):
    """OCC implementation of brep.trimmed(plane)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace

    shape = brep_to_occ(brep)
    occ_pln = gp_Pln(
        gp_Pnt(plane.point.x, plane.point.y, plane.point.z),
        gp_Dir(plane.normal.x, plane.normal.y, plane.normal.z),
    )
    face = BRepBuilderAPI_MakeFace(occ_pln).Face()
    ref_pt = gp_Pnt(
        plane.point.x + plane.normal.x * 1000,
        plane.point.y + plane.normal.y * 1000,
        plane.point.z + plane.normal.z * 1000,
    )
    halfspace = BRepPrimAPI_MakeHalfSpace(face, ref_pt).Solid()
    result = BRepAlgoAPI_Cut(shape, halfspace).Shape()
    return occ_to_brep(result)


def occ_split(brep, cutter):
    """OCC implementation of brep.split(cutter_brep).

    Splits a solid by a cutter Brep.  When the cutter is a planar face
    (open surface), the split is performed via two half-space cuts so that
    both sides of the cutting plane are returned.
    """
    from compas.geometry import Plane
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace

    shape = brep_to_occ(brep)

    # Determine the cutting plane from the cutter's first face
    if not cutter._faces:
        return [brep]
    cutting_surface = cutter._faces[0].surface

    if isinstance(cutting_surface, Plane):
        plane = cutting_surface
        occ_pln = gp_Pln(
            gp_Pnt(plane.point.x, plane.point.y, plane.point.z),
            gp_Dir(plane.normal.x, plane.normal.y, plane.normal.z),
        )
        plane_face = BRepBuilderAPI_MakeFace(occ_pln).Face()

        # Half-space on the normal side (positive side)
        ref_pt_pos = gp_Pnt(
            plane.point.x + plane.normal.x * 1000,
            plane.point.y + plane.normal.y * 1000,
            plane.point.z + plane.normal.z * 1000,
        )
        # Half-space on the opposite side (negative side)
        ref_pt_neg = gp_Pnt(
            plane.point.x - plane.normal.x * 1000,
            plane.point.y - plane.normal.y * 1000,
            plane.point.z - plane.normal.z * 1000,
        )

        halfspace_pos = BRepPrimAPI_MakeHalfSpace(plane_face, ref_pt_pos).Solid()
        halfspace_neg = BRepPrimAPI_MakeHalfSpace(plane_face, ref_pt_neg).Solid()

        result_a = occ_to_brep(BRepAlgoAPI_Cut(shape, halfspace_pos).Shape())
        result_b = occ_to_brep(BRepAlgoAPI_Cut(shape, halfspace_neg).Shape())
    else:
        # Generic case: cut by the cutter shape in both directions
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

        cutter_shape = brep_to_occ(cutter)
        result_a = occ_to_brep(BRepAlgoAPI_Cut(shape, cutter_shape).Shape())
        result_b = occ_to_brep(BRepAlgoAPI_Common(shape, cutter_shape).Shape())

    results = []
    if result_a._faces:
        results.append(result_a)
    if result_b._faces:
        results.append(result_b)
    return results


def occ_slice(brep, plane):
    """OCC implementation of brep.slice(plane) — returns intersection polylines."""
    from compas.geometry import Point as _Point
    from compas.geometry import Polyline
    from OCP.BRepAdaptor import BRepAdaptor_Curve as _BRepAdaptor_Curve
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.TopExp import TopExp_Explorer as _TopExp_Explorer
    from OCP.TopoDS import TopoDS as _TopoDS

    shape = brep_to_occ(brep)
    pln = gp_Pln(
        gp_Pnt(plane.point.x, plane.point.y, plane.point.z),
        gp_Dir(plane.normal.x, plane.normal.y, plane.normal.z),
    )
    plane_face = BRepBuilderAPI_MakeFace(pln).Face()
    section = BRepAlgoAPI_Section(shape, plane_face)
    section.Build()
    result_shape = section.Shape()

    polylines = []
    edge_exp = _TopExp_Explorer(result_shape, TopAbs_EDGE)
    while edge_exp.More():
        edge = _TopoDS.Edge_s(edge_exp.Current())
        adaptor = _BRepAdaptor_Curve(edge)
        t0, t1 = adaptor.FirstParameter(), adaptor.LastParameter()
        n_pts = 32
        pts = []
        for i in range(n_pts + 1):
            t = t0 + (t1 - t0) * i / n_pts
            p = adaptor.Value(t)
            pts.append(_Point(p.X(), p.Y(), p.Z()))
        polylines.append(Polyline(pts))
        edge_exp.Next()
    return polylines


# =============================================================================
# Additional operations
# =============================================================================


def occ_fillet(brep, radius, edges=None):
    """Fillet edges of a Brep. If edges is None, fillet all edges."""
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet

    shape = brep_to_occ(brep)
    fillet = BRepFilletAPI_MakeFillet(shape)

    if edges is not None:
        # Fillet specific edges by index
        all_edges = []
        exp = TopExp_Explorer(shape, TopAbs_EDGE)
        while exp.More():
            all_edges.append(TopoDS.Edge_s(exp.Current()))
            exp.Next()
        for edge_idx in edges:
            if 0 <= edge_idx < len(all_edges):
                fillet.Add(radius, all_edges[edge_idx])
    else:
        # Fillet all edges
        exp = TopExp_Explorer(shape, TopAbs_EDGE)
        while exp.More():
            fillet.Add(radius, TopoDS.Edge_s(exp.Current()))
            exp.Next()

    fillet.Build()
    return occ_to_brep(fillet.Shape())


def occ_offset(brep, distance):
    """Offset a Brep by a distance."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape

    shape = brep_to_occ(brep)
    offset = BRepOffsetAPI_MakeOffsetShape()
    offset.PerformBySimple(shape, distance)
    return occ_to_brep(offset.Shape())


def occ_contains(brep, point):
    """Check if a point is contained inside a solid Brep."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    shape = brep_to_occ(brep)
    classifier = BRepClass3d_SolidClassifier(shape, gp_Pnt(point.x, point.y, point.z), 1e-6)
    state = classifier.State()
    return state == TopAbs_IN or state == TopAbs_ON


def occ_cap_planar_holes(brep):
    """Cap planar holes in a Brep."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid

    shape = brep_to_occ(brep)
    sewing = BRepBuilderAPI_Sewing()
    sewing.Add(shape)
    sewing.Perform()
    sewn = sewing.SewedShape()
    try:
        solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(sewn))
        return occ_to_brep(solid.Shape())
    except Exception:
        return occ_to_brep(sewn)


def occ_overlap(brep_a, brep_b, deflection=None, tolerance=0.0):
    """Compute the overlap between two Breps, returning the common shape."""
    shape_a = brep_to_occ(brep_a)
    shape_b = brep_to_occ(brep_b)
    common = BRepAlgoAPI_Common(shape_a, shape_b)
    result = occ_to_brep(common.Shape())
    return result


def occ_fix(brep):
    """Fix a Brep shape using ShapeFix."""
    from OCP.ShapeFix import ShapeFix_Shape

    shape = brep_to_occ(brep)
    fixer = ShapeFix_Shape(shape)
    fixer.Perform()
    return occ_to_brep(fixer.Shape())


def occ_heal(brep):
    """Heal a Brep shape (fix + sew)."""
    from OCP.ShapeFix import ShapeFix_Shape

    shape = brep_to_occ(brep)
    fixer = ShapeFix_Shape(shape)
    fixer.Perform()
    fixed = fixer.Shape()

    sewing = BRepBuilderAPI_Sewing()
    sewing.Add(fixed)
    sewing.Perform()
    return occ_to_brep(sewing.SewedShape())


def occ_sew(brep):
    """Sew a Brep shape."""
    shape = brep_to_occ(brep)
    sewing = BRepBuilderAPI_Sewing()
    sewing.Add(shape)
    sewing.Perform()
    return occ_to_brep(sewing.SewedShape())


def occ_make_solid(brep):
    """Convert a shell Brep to a solid."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid

    shape = brep_to_occ(brep)
    solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(shape))
    return occ_to_brep(solid.Shape())


def occ_sweep(profile, path):
    """Create a Brep by sweeping a profile along a path."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe

    profile_shape = brep_to_occ(profile)
    path_shape = brep_to_occ(path)
    # Extract the wire from the path
    wire_exp = TopExp_Explorer(path_shape, TopAbs_WIRE)
    if wire_exp.More():
        wire = TopoDS.Wire_s(wire_exp.Current())
    else:
        # Build wire from edges
        builder = BRepBuilderAPI_MakeWire()
        edge_exp = TopExp_Explorer(path_shape, TopAbs_EDGE)
        while edge_exp.More():
            builder.Add(TopoDS.Edge_s(edge_exp.Current()))
            edge_exp.Next()
        wire = builder.Wire()

    # Get profile shape (first face or first wire)
    face_exp = TopExp_Explorer(profile_shape, TopAbs_FACE)
    if face_exp.More():
        profile_topo = TopoDS.Face_s(face_exp.Current())
    else:
        wire_exp2 = TopExp_Explorer(profile_shape, TopAbs_WIRE)
        profile_topo = TopoDS.Wire_s(wire_exp2.Current())

    pipe = BRepOffsetAPI_MakePipe(wire, profile_topo)
    pipe.Build()
    return occ_to_brep(pipe.Shape())


def occ_pipe(path, radius):
    """Create a pipe by sweeping a circle along a path."""

    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
    from OCP.GC import GC_MakeCircle

    path_shape = brep_to_occ(path)
    # Extract wire from path
    wire_exp = TopExp_Explorer(path_shape, TopAbs_WIRE)
    if wire_exp.More():
        wire = TopoDS.Wire_s(wire_exp.Current())
    else:
        builder = BRepBuilderAPI_MakeWire()
        edge_exp = TopExp_Explorer(path_shape, TopAbs_EDGE)
        while edge_exp.More():
            builder.Add(TopoDS.Edge_s(edge_exp.Current()))
            edge_exp.Next()
        wire = builder.Wire()

    # Get starting point and tangent of path
    edge_exp = TopExp_Explorer(wire, TopAbs_EDGE)
    first_edge = TopoDS.Edge_s(edge_exp.Current())
    adaptor = BRepAdaptor_Curve(first_edge)
    start_pt = adaptor.Value(adaptor.FirstParameter())
    d1 = gp_Vec()
    p_tmp = gp_Pnt()
    adaptor.D1(adaptor.FirstParameter(), p_tmp, d1)
    direction = gp_Dir(d1)

    ax2 = gp_Ax2(start_pt, direction)
    circle_edge = BRepBuilderAPI_MakeEdge(GC_MakeCircle(ax2, radius).Value())
    circle_wire = BRepBuilderAPI_MakeWire(circle_edge.Edge()).Wire()
    circle_face = BRepBuilderAPI_MakeFace(circle_wire)

    pipe = BRepOffsetAPI_MakePipe(wire, circle_face.Face())
    pipe.Build()
    return occ_to_brep(pipe.Shape())


def occ_from_curves(curves):
    """Create a Brep from planar boundary curves."""
    from compas_brep.curves.nurbs import NurbsCurve as _NC

    wire_builder = BRepBuilderAPI_MakeWire()
    for curve in curves:
        if isinstance(curve, _NC):
            occ_curve = _nurbs_curve_to_occ(curve)
            edge = BRepBuilderAPI_MakeEdge(occ_curve).Edge()
        else:
            # Line
            p0 = gp_Pnt(curve.start.x, curve.start.y, curve.start.z)
            p1 = gp_Pnt(curve.end.x, curve.end.y, curve.end.z)
            edge = BRepBuilderAPI_MakeEdge(p0, p1).Edge()
        wire_builder.Add(edge)

    wire = wire_builder.Wire()
    face = BRepBuilderAPI_MakeFace(wire)
    return occ_to_brep(face.Shape())


def occ_from_breps(breps):
    """Join multiple Breps into one by sewing overlapping edges."""
    sewing = BRepBuilderAPI_Sewing()
    for b in breps:
        sewing.Add(brep_to_occ(b))
    sewing.Perform()
    return occ_to_brep(sewing.SewedShape())


def occ_from_surface(surface, domain_u=None, domain_v=None):
    """Create a Brep from a NurbsSurface."""
    occ_surface = _nurbs_surface_to_occ(surface)
    if domain_u and domain_v:
        face = BRepBuilderAPI_MakeFace(occ_surface, domain_u[0], domain_u[1], domain_v[0], domain_v[1], 1e-6)
    else:
        face = BRepBuilderAPI_MakeFace(occ_surface, 1e-6)
    return occ_to_brep(face.Shape())


def occ_to_step(brep, filepath, **kwargs):
    """Export a Brep to a STEP file."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    shape = brep_to_occ(brep)
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(filepath))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Failed to write STEP file: {filepath}")


def occ_from_step(filepath):
    """Import a Brep from a STEP file."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(filepath))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Failed to read STEP file: {filepath}")
    reader.TransferRoots()
    shape = reader.OneShape()
    return occ_to_brep(shape)


def occ_to_stl(brep, filepath, linear_deflection=1e-3, angular_deflection=0.5):
    """Export a Brep to an STL file."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.StlAPI import StlAPI_Writer

    shape = brep_to_occ(brep)
    BRepMesh_IncrementalMesh(shape, linear_deflection, True, angular_deflection)
    writer = StlAPI_Writer()
    writer.Write(shape, str(filepath))


def occ_to_iges(brep, filepath):
    """Export a Brep to an IGES file."""
    from OCP.IGESControl import IGESControl_Writer

    shape = brep_to_occ(brep)
    writer = IGESControl_Writer()
    writer.AddShape(shape)
    writer.Write(str(filepath))


def occ_from_iges(filepath):
    """Import a Brep from an IGES file."""
    from OCP.IGESControl import IGESControl_Reader

    reader = IGESControl_Reader()
    reader.ReadFile(str(filepath))
    reader.TransferRoots()
    shape = reader.OneShape()
    return occ_to_brep(shape)
