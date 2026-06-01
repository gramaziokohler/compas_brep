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
from compas_rhino.conversions import (
    box_to_rhino,
    cone_to_rhino,
    cylinder_to_rhino,
    mesh_to_rhino,
    plane_to_rhino,
    sphere_to_rhino,
    torus_to_rhino,
    vector_to_rhino,
)

from compas_brep.curves.nurbs import NurbsCurve
from compas_brep.edge import BrepEdge
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.surfaces.nurbs import NurbsSurface
from compas_brep.vertex import BrepVertex


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

    Extracts all NURBS surface data, edge curves, and topology from
    the Rhino Brep into Python-owned COMPAS data structures.

    Parameters
    ----------
    brep : :class:`compas_brep.Brep`
        A Brep whose ``_native_brep`` is a Rhino.Geometry.Brep.

    """
    rhino_brep = brep._native_brep

    # Build a vertex map keyed by Rhino vertex index
    vertex_map = {}
    for rhino_vertex in rhino_brep.Vertices:
        pt = rhino_vertex.Location
        vertex_map[rhino_vertex.VertexIndex] = BrepVertex(Point(pt.X, pt.Y, pt.Z))

    all_faces = []
    all_edges_set = set()
    all_edges = []
    all_loops = []

    for rhino_face in rhino_brep.Faces:
        face_reversed = rhino_face.OrientationIsReversed

        # Extract surface
        surface = _extract_surface(rhino_face)

        # Extract UV domain
        u_domain = (rhino_face.Domain(0)[0], rhino_face.Domain(0)[1])
        v_domain = (rhino_face.Domain(1)[0], rhino_face.Domain(1)[1])

        # Extract wire loops
        face_loops = []
        for rhino_loop in rhino_face.Loops:
            loop_edges = []
            for rhino_trim in rhino_loop.Trims:
                rhino_edge_obj = rhino_trim.Edge
                if rhino_edge_obj is None:
                    # Singular trim (e.g. at pole of sphere) — skip
                    continue

                # Extract 3D edge curve
                curve = _extract_edge_curve(rhino_edge_obj)

                # Determine start/end vertex based on trim direction
                sv_idx = rhino_trim.Edge.StartVertex.VertexIndex
                ev_idx = rhino_trim.Edge.EndVertex.VertexIndex
                if rhino_trim.IsReversed():
                    sv_idx, ev_idx = ev_idx, sv_idx
                start_v = vertex_map[sv_idx]
                end_v = vertex_map[ev_idx]

                edge = BrepEdge(start_v, end_v, curve=curve)
                loop_edges.append(edge)

                # Track unique edges by Rhino edge index
                edge_idx = rhino_edge_obj.EdgeIndex
                if edge_idx not in all_edges_set:
                    all_edges_set.add(edge_idx)
                    all_edges.append(edge)

            if loop_edges:
                loop = BrepLoop(loop_edges)
                face_loops.append(loop)
                all_loops.append(loop)

        # Rhino BrepLoop.LoopType: Outer = 0, Inner = 1
        # Sort so that the outer loop comes first
        outer_loops = []
        inner_loops = []
        for i, rhino_loop in enumerate(rhino_face.Loops):
            if i < len(face_loops):
                if rhino_loop.LoopType == Rhino.Geometry.BrepLoopType.Outer:
                    outer_loops.append(face_loops[i])
                else:
                    inner_loops.append(face_loops[i])

        if outer_loops:
            brep_face = BrepFace(
                outer_loops[0],
                surface=surface,
                is_reversed=face_reversed,
                domain_u=u_domain,
                domain_v=v_domain,
            )
            for inner_loop in inner_loops:
                brep_face.add_loop(inner_loop)
            all_faces.append(brep_face)

    brep._vertices = list(vertex_map.values())
    brep._edges = all_edges
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
            # Build a planar face from polygon vertices
            points = [v.point for v in face.outer_loop.vertices]
            rhino_points = [Rhino.Geometry.Point3d(p.x, p.y, p.z) for p in points]
            # Close the polyline
            rhino_points.append(rhino_points[0])
            polyline = Rhino.Geometry.Polyline(rhino_points)
            curve = polyline.ToNurbsCurve()
            planar_breps = Rhino.Geometry.Brep.CreatePlanarBreps(curve, TOL.absolute)
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
