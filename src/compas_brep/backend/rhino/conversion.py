"""Rhino ↔ compas_brep conversion functions.

All COMPAS↔Rhino conversion logic lives here:
- ``rhino_to_brep`` — Rhino.Geometry.Brep → canonical Brep
- ``brep_to_rhino`` — canonical Brep → Rhino.Geometry.Brep
- Private helpers used by both directions and shared with other modules.
"""

from __future__ import annotations

import Rhino  # type: ignore
from compas.geometry import Line
from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Vector
from compas.tolerance import TOL

from compas_brep.curves import NurbsCurve
from compas_brep.errors import BrepError
from compas_brep.surfaces import NurbsSurface
from compas_brep.surfaces import surface_to_data

from .builder import _RhinoBrepBuilder
from .topology import RhinoBrepEdge
from .topology import RhinoBrepFace
from .topology import RhinoBrepLoop
from .topology import RhinoBrepTrim
from .topology import RhinoBrepVertex

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
                    # Singular trim (e.g. at the pole of a sphere): no edge, but it
                    # collapses to a vertex and must survive the round-trip.
                    trims.append(
                        RhinoBrepTrim(
                            rhino_trim,
                            None,
                            False,
                            vertex=vertex_map[rhino_trim.StartVertex.VertexIndex],
                        )
                    )
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


def _extract_knots_mults(rhino_knots, order, knots_out, mults_out):  # noqa: ARG001 (order unused — kept for API compat)
    """Extract unique knots and multiplicities from Rhino's knot list.

    Rhino stores knots WITHOUT the first and last element of the full clamped
    knot vector (one element stripped from each end).  Restore the full vector
    by prepending/appending exactly one copy, then compress to unique values
    with their multiplicities.

    Parameters
    ----------
    rhino_knots : Rhino.Geometry.NurbsCurveKnotList or NurbsSurfaceKnotList
        The Rhino knot collection (length = n_points + degree - 1).
    order : int
        Unused.  Kept for API compatibility with callers.
    knots_out : list
        Output list for unique knot values.
    mults_out : list
        Output list for multiplicities.

    """
    # Rhino stores n_points+degree-1 knots — the full vector with first and last
    # element stripped (Rhino omits one copy at each clamped end).
    # Restore the full vector by prepending/appending exactly one copy.
    raw_knots = [rhino_knots[i] for i in range(rhino_knots.Count)]

    first = raw_knots[0] if raw_knots else 0.0
    last = raw_knots[-1] if raw_knots else 1.0
    full_kv = [first] + raw_knots + [last]

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


def _edge_curve_to_rhino(curve):
    """Convert a canonical edge curve (Line or NurbsCurve) to a Rhino Curve."""
    if isinstance(curve, Line):
        return Rhino.Geometry.LineCurve(
            Rhino.Geometry.Point3d(curve.start.x, curve.start.y, curve.start.z),
            Rhino.Geometry.Point3d(curve.end.x, curve.end.y, curve.end.z),
        )
    if isinstance(curve, NurbsCurve):
        return nurbs_curve_to_rhino(curve)
    raise BrepError(f"Cannot rebuild a Rhino edge from curve of type {type(curve).__name__}")


def _rhino_plane_from_compas(plane):
    """Build a Rhino.Geometry.Plane from a COMPAS Plane.

    The exchange document pins a plane by point and normal only — it carries no
    x-axis and no domain — so the in-plane axes are whatever Rhino derives from
    the normal. This is deterministic, but it is *not* the parameterization the
    writer's pcurves were measured in, which is why planar faces re-derive their
    pcurves in :func:`_project_curve_to_plane` instead of reusing the serialized
    ones.
    """
    return Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(plane.point.x, plane.point.y, plane.point.z),
        Rhino.Geometry.Vector3d(plane.normal.x, plane.normal.y, plane.normal.z),
    )


def _plane_surface_for_face(plane, face):
    """Build a bounded Rhino PlaneSurface large enough to contain a face's boundary."""
    rhino_plane = _rhino_plane_from_compas(plane)

    us = []
    vs = []
    for loop in face.loops:
        for vertex in loop.vertices:
            p = vertex.point
            success, u, v = rhino_plane.ClosestParameter(Rhino.Geometry.Point3d(p.x, p.y, p.z))
            if success:
                us.append(u)
                vs.append(v)

    if not us:
        raise BrepError("Cannot rebuild a planar face with no boundary vertices")

    # Pad so the trimmed boundary sits strictly inside the surface domain.
    pad = max(max(us) - min(us), max(vs) - min(vs)) * 0.1 + 1.0
    u_interval = Rhino.Geometry.Interval(min(us) - pad, max(us) + pad)
    v_interval = Rhino.Geometry.Interval(min(vs) - pad, max(vs) + pad)
    return Rhino.Geometry.PlaneSurface(rhino_plane, u_interval, v_interval)


def _project_curve_to_plane(curve, rhino_plane):
    """Project a canonical edge curve into a Rhino plane's (u, v) parameter space.

    A plane maps 3D to (u, v) affinely, so control points can be mapped directly
    while knots, weights, and degree carry over unchanged — the resulting pcurve
    is exact, not an approximation.
    """

    def to_uv(point):
        success, u, v = rhino_plane.ClosestParameter(Rhino.Geometry.Point3d(point.x, point.y, point.z))
        if not success:
            raise BrepError("Failed to project a curve onto the face plane")
        return u, v

    if isinstance(curve, Line):
        u0, v0 = to_uv(curve.start)
        u1, v1 = to_uv(curve.end)
        return Rhino.Geometry.LineCurve(
            Rhino.Geometry.Point3d(u0, v0, 0.0),
            Rhino.Geometry.Point3d(u1, v1, 0.0),
        )

    if isinstance(curve, NurbsCurve):
        n = len(curve._points)
        pcurve = Rhino.Geometry.NurbsCurve(3, True, curve._degree + 1, n)
        for i, (point, weight) in enumerate(zip(curve._points, curve._weights)):
            u, v = to_uv(point)
            pcurve.Points.SetPoint(i, Rhino.Geometry.Point3d(u, v, 0.0), weight)
        for i, k in enumerate(_expand_knots(curve._knots, curve._mults)[1:-1]):
            pcurve.Knots[i] = k
        return pcurve

    raise BrepError(f"Cannot project curve of type {type(curve).__name__} onto a plane")


def _iso_status_for_pcurve(pcurve, rhino_surface):
    """Classify a pcurve's iso direction, as ``Trims.AddSingularTrim`` requires.

    A singular trim runs along one edge of the surface's parameter rectangle —
    the pole of a sphere collapses to the whole u-range at v = min or v = max.
    """
    iso = Rhino.Geometry.IsoStatus
    start = pcurve.PointAtStart
    end = pcurve.PointAtEnd
    u_domain = rhino_surface.Domain(0)
    v_domain = rhino_surface.Domain(1)

    if TOL.is_close(start.X, end.X):
        if TOL.is_close(start.X, u_domain.Min):
            return iso.West
        if TOL.is_close(start.X, u_domain.Max):
            return iso.East
    if TOL.is_close(start.Y, end.Y):
        if TOL.is_close(start.Y, v_domain.Min):
            return iso.South
        if TOL.is_close(start.Y, v_domain.Max):
            return iso.North
    return iso.NONE


def _surface_to_rhino(surface, face):
    """Build the Rhino surface a face sits on."""
    if isinstance(surface, Plane):
        return _plane_surface_for_face(surface, face)
    if isinstance(surface, NurbsSurface):
        return nurbs_surface_to_rhino(surface)
    raise BrepError(f"Rhino backend cannot rebuild a face on surface type {type(surface).__name__}")


def brep_to_rhino(brep):
    """Convert a canonical compas_brep.Brep to a Rhino.Geometry.Brep.

    If the brep has a cached native shape, returns it directly. Otherwise the
    shape is reconstructed through the low-level Rhino Brep builder, which shares
    edges by index and carries every trim's pcurve across — so a genuinely
    trimmed face rebuilds as a trimmed face. See ADR-0002.

    Parameters
    ----------
    brep : :class:`compas_brep.Brep`

    Returns
    -------
    Rhino.Geometry.Brep

    """
    if brep._native_brep is not None:
        return brep._native_brep

    builder = _RhinoBrepBuilder()

    vertex_index = {}
    for vertex in brep._vertices:
        vertex_index[id(vertex)] = len(vertex_index)
        builder.add_vertex(vertex.point)

    edge_index = {}
    for edge in brep._edges:
        edge_index[id(edge)] = len(edge_index)
        builder.add_edge(
            _edge_curve_to_rhino(edge.curve),
            vertex_index[id(edge.first_vertex)],
            vertex_index[id(edge.last_vertex)],
        )

    for face in brep._faces:
        surface = face.surface
        rhino_surface = _surface_to_rhino(surface, face)
        face_builder = builder.add_face(rhino_surface, face.is_reversed)

        is_planar = isinstance(surface, Plane)
        rhino_plane = _rhino_plane_from_compas(surface) if is_planar else None

        loops = [(face.outer_loop, Rhino.Geometry.BrepLoopType.Outer)]
        loops += [(loop, Rhino.Geometry.BrepLoopType.Inner) for loop in face._inner_loops]

        for loop, loop_type in loops:
            loop_builder = face_builder.add_loop(loop_type)
            for trim in loop.trims:
                if trim.edge is None:
                    # Singular trim (e.g. at the pole of a sphere): it collapses to
                    # a vertex, so it has no edge curve to project — the serialized
                    # pcurve is the only description of it.
                    if trim.curve_2d is None:
                        raise BrepError("Cannot rebuild a singular trim without a pcurve")
                    pcurve = nurbs_curve_to_rhino(trim.curve_2d)
                    loop_builder.add_trim(
                        pcurve,
                        -1,
                        False,
                        _iso_status_for_pcurve(pcurve, rhino_surface),
                        vertex_index[id(trim.vertex)],
                    )
                    continue

                if is_planar:
                    # A plane's parameterization is not pinned by the document
                    # (point and normal fix no x-axis), so the serialized pcurve
                    # cannot be trusted here — re-derive it against the rebuilt plane.
                    pcurve = _project_curve_to_plane(trim.edge.curve, rhino_plane)
                    if trim.is_reversed:
                        pcurve.Reverse()
                else:
                    if trim.curve_2d is None:
                        raise BrepError("Cannot rebuild a trim without a pcurve")
                    pcurve = nurbs_curve_to_rhino(trim.curve_2d)

                loop_builder.add_trim(
                    pcurve,
                    edge_index[id(trim.edge)],
                    trim.is_reversed,
                    Rhino.Geometry.IsoStatus.NONE,
                    -1,
                )

    brep._native_brep = builder.result
    return brep._native_brep


def nurbs_surface_to_rhino(surface):
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


def nurbs_curve_to_rhino(curve):
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
        surface_data = surface_to_data(surface)

        loops = []
        for rl in rf.Loops:
            trims = []
            for rt in rl.Trims:
                pcurve = _extract_trim_pcurve(rt)
                re_obj = rt.Edge
                if re_obj is None:
                    # Singular trim (e.g. the pole of a sphere). It has no edge, so
                    # it is pinned by its pcurve plus the vertex it collapses to.
                    if pcurve is None:
                        raise BrepError("Cannot serialize a singular trim without a pcurve")
                    trims.append(
                        {
                            "edge": -1,
                            "vertex": vertex_id_map[rt.StartVertex.VertexIndex],
                            "is_reversed": False,
                            "curve_2d": pcurve.__data__,
                        }
                    )
                    continue
                eidx = re_obj.EdgeIndex
                if eidx not in edge_id_map:
                    continue
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
        "version": 5,
        "vertices": vertex_list,
        "edges": edge_list,
        "faces": face_list,
    }
