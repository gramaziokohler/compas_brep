"""Rhino ↔ compas_brep conversion functions.

All COMPAS↔Rhino conversion logic lives here:
- ``rhino_to_brep`` — Rhino.Geometry.Brep → canonical Brep
- ``brep_to_rhino`` — canonical Brep → Rhino.Geometry.Brep
- Private helpers used by both directions and shared with other modules.
"""

from __future__ import annotations

import Rhino  # type: ignore
from compas.geometry import Line, Plane, Point, Vector
from compas.tolerance import TOL

from compas_brep.curves.nurbs import NurbsCurve
from compas_brep.surfaces.nurbs import NurbsSurface

# =============================================================================
# Rhino → compas_brep conversion
# =============================================================================


def rhino_to_brep(rhino_brep):
    """Wrap a Rhino.Geometry.Brep in a compas_brep.Brep.

    Returns a thin Brep with ``_native_brep`` set but no topology extracted yet.
    Topology (vertices, edges, loops, faces) is populated lazily on first access
    via :func:`rhino_extract_topology`.

    Parameters
    ----------
    rhino_brep : Rhino.Geometry.Brep
        The native Rhino Brep to wrap.

    Returns
    -------
    :class:`compas_brep.Brep`

    """
    from compas_brep.brep import Brep

    brep = Brep()
    brep._native_brep = rhino_brep
    return brep


def rhino_extract_topology(brep) -> None:
    """Populate a Brep's topology lists in-place from its cached Rhino native shape.

    Produces native-handle wrapper objects (RhinoBrepVertex, RhinoBrepEdge, etc.)
    that hold references to their underlying Rhino.Geometry entities. Geometric
    properties (.point, .curve, .surface, .curve_2d) are deferred to first access.

    Parameters
    ----------
    brep : :class:`compas_brep.Brep`
        A Brep whose ``_native_brep`` is a Rhino.Geometry.Brep.

    """
    from compas_brep.backend.rhino.topology import (
        RhinoBrepEdge,
        RhinoBrepFace,
        RhinoBrepLoop,
        RhinoBrepTrim,
        RhinoBrepVertex,
    )

    rhino_brep = brep._native_brep

    # Build vertex wrappers keyed by Rhino vertex index
    vertex_map = {}
    for rhino_vertex in rhino_brep.Vertices:
        vertex_map[rhino_vertex.VertexIndex] = RhinoBrepVertex(rhino_vertex)

    # Build edge wrappers keyed by Rhino edge index (deduplication via index)
    edge_map = {}
    for rhino_edge in rhino_brep.Edges:
        sv_idx = rhino_edge.StartVertex.VertexIndex
        ev_idx = rhino_edge.EndVertex.VertexIndex
        edge_map[rhino_edge.EdgeIndex] = RhinoBrepEdge(
            rhino_edge,
            vertex_map[sv_idx],
            vertex_map[ev_idx],
        )

    all_faces = []
    all_loops = []

    for rhino_face in rhino_brep.Faces:
        face_reversed = rhino_face.OrientationIsReversed
        loop_pairs = []  # (rhino_loop, RhinoBrepLoop)

        for rhino_loop in rhino_face.Loops:
            trims = []
            for rhino_trim in rhino_loop.Trims:
                rhino_edge_obj = rhino_trim.Edge
                if rhino_edge_obj is None:
                    # Singular trim (e.g. at pole of sphere) — skip
                    continue
                edge_idx = rhino_edge_obj.EdgeIndex
                brep_edge = edge_map[edge_idx]
                is_reversed = rhino_trim.IsReversed()
                trims.append(RhinoBrepTrim(rhino_trim, brep_edge, is_reversed))

            if trims:
                loop = RhinoBrepLoop(rhino_loop, trims)
                all_loops.append(loop)
                loop_pairs.append((rhino_loop, loop))

        outer_loops = [lp for rl, lp in loop_pairs if rl.LoopType == Rhino.Geometry.BrepLoopType.Outer]
        inner_loops = [lp for rl, lp in loop_pairs if rl.LoopType != Rhino.Geometry.BrepLoopType.Outer]

        if outer_loops:
            brep_face = RhinoBrepFace(rhino_face, outer_loops[0], inner_loops, face_reversed)
            all_faces.append(brep_face)

    brep._vertices = list(vertex_map.values())
    brep._edges = list(edge_map.values())
    brep._loops = all_loops
    brep._faces = all_faces


def _extract_surface(rhino_face):
    """Extract surface data from a Rhino face, returning Plane or NurbsSurface.

    Parameters
    ----------
    rhino_face : Rhino.Geometry.BrepFace

    Returns
    -------
    :class:`compas.geometry.Plane` or :class:`compas_brep.NurbsSurface`

    """
    underlying = rhino_face.UnderlyingSurface()

    # Check if planar
    if underlying.IsPlanar():
        success, plane = underlying.FrameAt(
            underlying.Domain(0).Mid,
            underlying.Domain(1).Mid,
        )
        if success:
            normal = plane.Normal
            origin = plane.Origin
            return Plane(
                Point(origin.X, origin.Y, origin.Z),
                Vector(normal.X, normal.Y, normal.Z),
            )

    # Convert to NURBS surface for non-planar
    nurbs = underlying.ToNurbsSurface()
    return _rhino_nurbs_surface_to_compas(nurbs)


def _rhino_nurbs_surface_to_compas(rhino_nurbs):
    """Convert a Rhino.Geometry.NurbsSurface to a compas_brep NurbsSurface.

    Parameters
    ----------
    rhino_nurbs : Rhino.Geometry.NurbsSurface

    Returns
    -------
    :class:`compas_brep.NurbsSurface`

    """
    nu = rhino_nurbs.Points.CountU
    nv = rhino_nurbs.Points.CountV

    points = []
    weights = []
    for i in range(nu):
        row_pts = []
        row_wts = []
        for j in range(nv):
            cp = rhino_nurbs.Points.GetControlPoint(i, j)
            row_pts.append(Point(cp.Location.X, cp.Location.Y, cp.Location.Z))
            row_wts.append(cp.Weight)
        points.append(row_pts)
        weights.append(row_wts)

    knots_u = []
    mults_u = []
    _extract_knots_mults(rhino_nurbs.KnotsU, rhino_nurbs.OrderU, knots_u, mults_u)

    knots_v = []
    mults_v = []
    _extract_knots_mults(rhino_nurbs.KnotsV, rhino_nurbs.OrderV, knots_v, mults_v)

    return NurbsSurface.from_parameters(
        points=points,
        weights=weights,
        knots_u=knots_u,
        knots_v=knots_v,
        mults_u=mults_u,
        mults_v=mults_v,
        degree_u=rhino_nurbs.Degree(0),
        degree_v=rhino_nurbs.Degree(1),
    )


def _extract_edge_curve(rhino_edge):
    """Extract 3D curve from a Rhino BrepEdge, returning Line or NurbsCurve.

    Parameters
    ----------
    rhino_edge : Rhino.Geometry.BrepEdge

    Returns
    -------
    :class:`compas.geometry.Line` or :class:`compas_brep.NurbsCurve`

    """
    edge_curve = rhino_edge.EdgeCurve
    if edge_curve is None:
        sp = rhino_edge.PointAtStart
        ep = rhino_edge.PointAtEnd
        return Line(Point(sp.X, sp.Y, sp.Z), Point(ep.X, ep.Y, ep.Z))

    if edge_curve.IsLinear():
        sp = edge_curve.PointAtStart
        ep = edge_curve.PointAtEnd
        return Line(Point(sp.X, sp.Y, sp.Z), Point(ep.X, ep.Y, ep.Z))

    # Convert to NURBS curve for arcs, circles, ellipses, and general curves
    nurbs = edge_curve.ToNurbsCurve()
    if nurbs is not None:
        return _rhino_nurbs_curve_to_compas(nurbs)

    # Fallback: straight line approximation
    sp = edge_curve.PointAtStart
    ep = edge_curve.PointAtEnd
    return Line(Point(sp.X, sp.Y, sp.Z), Point(ep.X, ep.Y, ep.Z))


def _rhino_nurbs_curve_to_compas(rhino_nurbs):
    """Convert a Rhino.Geometry.NurbsCurve to a compas_brep NurbsCurve.

    Parameters
    ----------
    rhino_nurbs : Rhino.Geometry.NurbsCurve

    Returns
    -------
    :class:`compas_brep.NurbsCurve`

    """
    n_poles = rhino_nurbs.Points.Count
    points = []
    weights = []
    for i in range(n_poles):
        cp = rhino_nurbs.Points[i]
        points.append(Point(cp.Location.X, cp.Location.Y, cp.Location.Z))
        weights.append(cp.Weight)

    knots = []
    mults = []
    _extract_knots_mults(rhino_nurbs.Knots, rhino_nurbs.Order, knots, mults)

    return NurbsCurve.from_parameters(
        points=points,
        weights=weights,
        knots=knots,
        mults=mults,
        degree=rhino_nurbs.Degree,
    )


def _extract_knots_mults(rhino_knots, order, knots_out, mults_out):
    """Extract unique knots and multiplicities from Rhino's knot list.

    Rhino stores knots WITHOUT the end multiplicities (missing degree+1 end knots).
    We reconstruct the full knot vector by adding the clamped end knots, then
    compress to unique knots + multiplicities.

    Parameters
    ----------
    rhino_knots : Rhino.Geometry.NurbsCurveKnotList or NurbsSurfaceKnotList
        The Rhino knot collection.
    order : int
        The order (degree + 1) of the curve/surface in this direction.
    knots_out : list
        Output list for unique knot values.
    mults_out : list
        Output list for multiplicities.

    """
    # Rhino stores n_points - 2 knots (without the end clamping).
    # Build the full knot vector by adding clamped ends.
    degree = order - 1
    raw_knots = [rhino_knots[i] for i in range(rhino_knots.Count)]

    # Build full knot vector with end clamping
    first = raw_knots[0] if raw_knots else 0.0
    last = raw_knots[-1] if raw_knots else 1.0
    full_kv = [first] * degree + raw_knots + [last] * degree

    # Compress to unique knots + multiplicities
    if not full_kv:
        return
    knots_out.append(full_kv[0])
    mults_out.append(1)
    for v in full_kv[1:]:
        if abs(v - knots_out[-1]) < 1e-14:
            mults_out[-1] += 1
        else:
            knots_out.append(v)
            mults_out.append(1)


# =============================================================================
# compas_brep → Rhino conversion
# =============================================================================


def _rhino_curve_from_loop(loop):
    """Build a single joined Rhino Curve from a BrepLoop's trims or edges.

    Returns None if no curves can be built (e.g. all degenerate edges).
    """
    curves = []
    if loop.trims:
        for trim in loop.trims:
            edge = trim.edge
            curve = edge.curve
            sp = edge.first_vertex.point
            ep = edge.last_vertex.point
            if isinstance(curve, NurbsCurve):
                rc = _compas_nurbs_curve_to_rhino(curve)
                if trim.is_reversed:
                    rc.Reverse()
                curves.append(rc)
            else:
                if trim.is_reversed:
                    p0 = Rhino.Geometry.Point3d(ep.x, ep.y, ep.z)
                    p1 = Rhino.Geometry.Point3d(sp.x, sp.y, sp.z)
                else:
                    p0 = Rhino.Geometry.Point3d(sp.x, sp.y, sp.z)
                    p1 = Rhino.Geometry.Point3d(ep.x, ep.y, ep.z)
                dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5
                if dist > 1e-9:
                    curves.append(Rhino.Geometry.LineCurve(p0, p1))
    else:
        for edge in loop.edges:
            curve = edge.curve
            sp = edge.first_vertex.point
            ep = edge.last_vertex.point
            if isinstance(curve, NurbsCurve):
                curves.append(_compas_nurbs_curve_to_rhino(curve))
            else:
                p0 = Rhino.Geometry.Point3d(sp.x, sp.y, sp.z)
                p1 = Rhino.Geometry.Point3d(ep.x, ep.y, ep.z)
                dist = ((sp.x - ep.x) ** 2 + (sp.y - ep.y) ** 2 + (sp.z - ep.z) ** 2) ** 0.5
                if dist > 1e-9:
                    curves.append(Rhino.Geometry.LineCurve(p0, p1))
    if not curves:
        return None
    joined = Rhino.Geometry.Curve.JoinCurves(curves, TOL.absolute)
    return joined[0] if joined else None


def brep_to_rhino(brep):
    """Convert a canonical compas_brep.Brep to a Rhino.Geometry.Brep.

    If the brep has a cached native shape that is not dirty, returns it directly.

    Parameters
    ----------
    brep : :class:`compas_brep.Brep`

    Returns
    -------
    Rhino.Geometry.Brep

    """
    if brep._native_brep is not None:
        return brep._native_brep

    rhino_brep = Rhino.Geometry.Brep()

    for face in brep._faces:
        surface = face.surface

        if isinstance(surface, Plane):
            # Build boundary curves from loop trim edges (handles inner loops/holes).
            outer_curve = _rhino_curve_from_loop(face.outer_loop)
            if outer_curve is None:
                # Fallback: closed polygon from vertex positions
                points = [v.point for v in face.outer_loop.vertices]
                if not points:
                    continue
                rhino_points = [Rhino.Geometry.Point3d(p.x, p.y, p.z) for p in points]
                rhino_points.append(rhino_points[0])
                polyline = Rhino.Geometry.Polyline(rhino_points)
                outer_curve = polyline.ToNurbsCurve()

            all_curves = [outer_curve]
            for inner_loop in face._inner_loops:
                inner_curve = _rhino_curve_from_loop(inner_loop)
                if inner_curve is not None:
                    all_curves.append(inner_curve)

            planar_breps = Rhino.Geometry.Brep.CreatePlanarBreps(all_curves, TOL.absolute)
            if planar_breps and len(planar_breps) > 0:
                for pb in planar_breps:
                    for pf in pb.Faces:
                        rhino_brep.Append(pf.DuplicateFace(False))

        elif isinstance(surface, NurbsSurface):
            rhino_surface = _compas_nurbs_surface_to_rhino(surface)
            face_brep = rhino_surface.ToBrep()
            if face_brep:
                for f in face_brep.Faces:
                    rhino_brep.Append(f.DuplicateFace(False))

    # Join the individual face breps
    joined = Rhino.Geometry.Brep.JoinBreps(
        [rhino_brep],
        TOL.absolute,
    )
    if joined and len(joined) > 0:
        result = joined[0]
    else:
        result = rhino_brep

    brep._native_brep = result
    return result


def _compas_nurbs_surface_to_rhino(surface):
    """Convert a compas_brep NurbsSurface to a Rhino.Geometry.NurbsSurface.

    Parameters
    ----------
    surface : :class:`compas_brep.NurbsSurface`

    Returns
    -------
    Rhino.Geometry.NurbsSurface

    """
    points = surface._points
    weights = surface._weights
    nu = len(points)
    nv = len(points[0])

    rhino_surface = Rhino.Geometry.NurbsSurface.Create(
        3,  # dimension
        True,  # isRational
        surface._degree_u + 1,  # orderU
        surface._degree_v + 1,  # orderV
        nu,  # control point count U
        nv,  # control point count V
    )

    # Set control points and weights
    for i in range(nu):
        for j in range(nv):
            p = points[i][j]
            w = weights[i][j]
            rhino_surface.Points.SetPoint(
                i,
                j,
                Rhino.Geometry.Point3d(p.x, p.y, p.z),
                w,
            )

    # Set knot vectors
    # Rhino stores knots WITHOUT end clamping (n_points - 2 knots)
    full_kv_u = _expand_knots(surface._knots_u, surface._mults_u)
    full_kv_v = _expand_knots(surface._knots_v, surface._mults_v)
    # Strip the first and last knot (Rhino convention)
    rhino_kv_u = full_kv_u[1:-1]
    rhino_kv_v = full_kv_v[1:-1]
    for i, k in enumerate(rhino_kv_u):
        rhino_surface.KnotsU[i] = k
    for i, k in enumerate(rhino_kv_v):
        rhino_surface.KnotsV[i] = k

    return rhino_surface


def _compas_nurbs_curve_to_rhino(curve):
    """Convert a compas_brep NurbsCurve to a Rhino.Geometry.NurbsCurve.

    Parameters
    ----------
    curve : :class:`compas_brep.NurbsCurve`

    Returns
    -------
    Rhino.Geometry.NurbsCurve

    """
    points = curve._points
    weights = curve._weights
    n = len(points)

    rhino_curve = Rhino.Geometry.NurbsCurve(3, True, curve._degree + 1, n)

    for i in range(n):
        p = points[i]
        w = weights[i]
        rhino_curve.Points.SetPoint(i, Rhino.Geometry.Point3d(p.x, p.y, p.z), w)

    # Set knot vector (Rhino convention: strip first and last knot)
    full_kv = _expand_knots(curve._knots, curve._mults)
    rhino_kv = full_kv[1:-1]
    for i, k in enumerate(rhino_kv):
        rhino_curve.Knots[i] = k

    return rhino_curve


def _expand_knots(knots, mults):
    """Expand unique knots + multiplicities into a full knot vector."""
    kv = []
    for k, m in zip(knots, mults):
        kv.extend([k] * m)
    return kv


# =============================================================================
# STEP-inspired JSON serialization (Rhino backend)
# =============================================================================


def _extract_trim_pcurve(rhino_trim):
    """Extract the 2D parametric curve from a Rhino BrepTrim, returning NurbsCurve or None."""
    curve = rhino_trim.TrimCurve
    if curve is None:
        return None
    nurbs = curve.ToNurbsCurve()
    if nurbs is None:
        return None
    return _rhino_nurbs_curve_to_compas(nurbs)


def rhino_brep_to_data(brep) -> dict:
    """Extract a STEP-inspired JSON dict from a native Rhino.Geometry.Brep.

    Mirrors the OCC version (``occ_brep_to_data``) using Rhino's topology API
    instead of OCC's TopExp traversal. Entity types follow the same STEP-inspired
    model: CARTESIAN_POINT vertices, EDGE_CURVE edges with 3D curves, and
    FACE_SURFACE faces with surface + oriented loops + pcurves.
    """
    rhino_brep = brep._native_brep

    # --- Vertices ---
    vertex_list = []
    vertex_id_map = {}  # VertexIndex -> list index
    for rv in rhino_brep.Vertices:
        p = rv.Location
        vertex_id_map[rv.VertexIndex] = len(vertex_list)
        vertex_list.append([p.X, p.Y, p.Z])

    # --- Edges ---
    edge_list = []
    edge_id_map = {}  # EdgeIndex -> list index
    for re in rhino_brep.Edges:
        sv = re.StartVertex
        ev = re.EndVertex
        start_id = vertex_id_map.get(sv.VertexIndex, 0) if sv is not None else 0
        end_id = vertex_id_map.get(ev.VertexIndex, 0) if ev is not None else 0

        curve = _extract_edge_curve(re)
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

        edge_id_map[re.EdgeIndex] = len(edge_list)
        edge_list.append({"start": start_id, "end": end_id, "curve": curve_data})

    # --- Faces ---
    face_list = []
    for rf in rhino_brep.Faces:
        surface = _extract_surface(rf)
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
        for rl in rf.Loops:
            trims = []
            for rt in rl.Trims:
                re_obj = rt.Edge
                if re_obj is None:
                    continue  # Singular trim (e.g. pole of sphere)
                eidx = re_obj.EdgeIndex
                if eidx not in edge_id_map:
                    continue
                pcurve = _extract_trim_pcurve(rt)
                trims.append(
                    {
                        "edge": edge_id_map[eidx],
                        "is_reversed": rt.IsReversed(),
                        "curve_2d": pcurve.__data__ if pcurve is not None else None,
                    }
                )
            if trims:
                loops.append(trims)

        if loops:
            face_list.append(
                {
                    "surface": surface_data,
                    "is_reversed": rf.OrientationIsReversed,
                    "loops": loops,
                }
            )

    return {
        "version": 4,
        "vertices": vertex_list,
        "edges": edge_list,
        "faces": face_list,
    }
