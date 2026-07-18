"""Rhino ↔ compas_brep conversion functions.

All COMPAS↔Rhino conversion logic lives here:
- ``rhino_to_brep`` — Rhino.Geometry.Brep → canonical Brep
- ``brep_to_rhino`` — canonical Brep → Rhino.Geometry.Brep
- Private helpers used by both directions and shared with other modules.
"""

from __future__ import annotations

import math

import Rhino  # type: ignore
from compas.geometry import ConicalSurface
from compas.geometry import CylindricalSurface
from compas.geometry import Frame
from compas.geometry import Line
from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import SphericalSurface
from compas.geometry import ToroidalSurface
from compas.geometry import Vector
from compas.tolerance import TOL

from compas_brep.curves import NurbsCurve
from compas_brep.errors import BrepError
from compas_brep.exchange import EXCHANGE_VERSION
from compas_brep.exchange import LOOP_INNER
from compas_brep.exchange import LOOP_OUTER
from compas_brep.exchange import analytic_surface_params
from compas_brep.exchange import analytic_surface_point
from compas_brep.exchange import analytic_surface_v_is_periodic
from compas_brep.exchange import loop_to_data
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


# Fraction of a domain used as the probe step when recovering a parameter map.
_PARAM_PROBE = 1e-4

# Grid resolution the recovered map is checked against, per direction.
_PARAM_CHECK_SAMPLES = 5


def _wrap_to_pi(angle):
    """Fold an angle difference into (-pi, pi], so a probe step never reads as a full turn."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _compas_analytic_surface(rhino_surface):
    """Return the COMPAS analytic surface a Rhino surface *is*, or None.

    This answers only "what shape is this", not "can the document carry it" —
    :func:`_analytic_surface_and_param_map` decides that. Each ``TryGet*`` is
    asked at ``TOL.absolute``, so a face that is a cylinder only to a looser
    tolerance stays ``nurbs`` rather than being silently idealized.
    """
    success, cylinder = rhino_surface.TryGetCylinder(TOL.absolute)
    if success:
        return CylindricalSurface(cylinder.Radius, frame=_frame_from_rhino_plane(cylinder.BasePlane))

    success, sphere = rhino_surface.TryGetSphere(TOL.absolute)
    if success:
        return SphericalSurface(sphere.Radius, frame=_frame_from_rhino_plane(sphere.EquatorialPlane))

    success, torus = rhino_surface.TryGetTorus(TOL.absolute)
    if success:
        return ToroidalSurface(torus.MajorRadius, torus.MinorRadius, frame=_frame_from_rhino_plane(torus.Plane))

    success, cone = rhino_surface.TryGetCone(TOL.absolute)
    if success:
        return _compas_cone_from_rhino(cone)

    return None


def _compas_cone_from_rhino(cone):
    """Convert a Rhino cone to a COMPAS ``ConicalSurface``, or None if degenerate.

    The two conventions do not line up, and the issue asked for this to be
    confirmed rather than assumed. Measured: Rhino puts its plane's **origin at
    the apex** with the z-axis pointing towards the base. COMPAS is the other way
    up — the frame sits on the **base** circle, ``radius`` is the base radius, and
    the apex is at ``+height * z``. So the COMPAS frame's z-axis is the reverse of
    Rhino's, which also reverses the direction ``u`` is measured in; the parameter
    map recovers that rather than this function hard-coding it.
    """
    apex = cone.ApexPoint
    base = cone.BasePoint
    axis = apex - base
    height = axis.Length
    if height < TOL.absolute or cone.Radius < TOL.absolute:
        # A flat disc or a needle: no meaningful cone frame, and `atan(-r/h)` is
        # about to be a division by zero. OCC's extractor declines these too.
        return None

    axis.Unitize()
    zaxis = Vector(axis.X, axis.Y, axis.Z)
    # Rhino's plane x-axis is perpendicular to its own z-axis, which is +-this one,
    # so it is a valid x-axis for the COMPAS frame either way.
    xaxis = Vector(cone.Plane.XAxis.X, cone.Plane.XAxis.Y, cone.Plane.XAxis.Z)
    frame = Frame(Point(base.X, base.Y, base.Z), xaxis, zaxis.cross(xaxis))
    return ConicalSurface(cone.Radius, height, frame=frame)


def _analytic_surface_and_param_map(rhino_surface):
    """Return ``(compas_surface, param_map)`` for a surface the document can tag.

    The document parameterizes every analytic tag the way OCC does — ``u`` the
    angle about the frame's z-axis, ``v`` what the tag makes it (see
    ``compas_brep.exchange``). Rhino agrees with none of it: it parameterizes
    these surfaces by **arc length**, so a cylinder wall's native ``u`` is
    ``radius * angle`` and a sphere's ``v`` is ``radius * latitude``. A pcurve
    written straight out of Rhino would put every trim at the wrong place on any
    reader — a document worse than the ``nurbs`` tag it replaces, because it looks
    right. ``param_map`` converts native ``(u, v)`` into the document's.

    The map is recovered by probing and then checked across the whole domain,
    never assumed: only an affine map can be carried onto a pcurve's control
    points exactly, and not every analytically-shaped Rhino surface has one. A
    fillet face is the case that matters — exactly a cylinder to
    ``TryGetCylinder``, but stored as a rational NURBS whose angle is not linear
    in either parameter. Those return ``(None, None)`` and are tagged ``nurbs``,
    which is not a degradation: the face is natively a NURBS surface, so the
    ``nurbs`` tag reproduces it exactly.

    Returns
    -------
    tuple
        ``(COMPAS analytic surface, callable)``, or ``(None, None)``.

    """
    surface = _compas_analytic_surface(rhino_surface)
    if surface is None:
        return None, None

    param_map = _recover_param_map(rhino_surface, surface)
    if param_map is None:
        return None, None
    return surface, param_map


def _recover_param_map(rhino_surface, surface):
    """Recover the affine map from a Rhino surface's ``(u, v)`` to the document's.

    Probed from the middle of the domain rather than a corner: a corner of an
    analytic surface is where the degeneracies are — a sphere's pole is at both
    ends of ``v``, and the seam sits at the ends of ``u``.
    """
    u_domain = rhino_surface.Domain(0)
    v_domain = rhino_surface.Domain(1)
    du = (u_domain.Max - u_domain.Min) * _PARAM_PROBE
    dv = (v_domain.Max - v_domain.Min) * _PARAM_PROBE
    if du == 0.0 or dv == 0.0:
        return None

    v_periodic = analytic_surface_v_is_periodic(surface)

    def document_params(u, v):
        point = rhino_surface.PointAt(u, v)
        return analytic_surface_params(surface, Point(point.X, point.Y, point.Z))

    def delta(a, b, periodic):
        # Both document parameters that wrap do so every 2*pi, and a probe step is
        # far smaller than that -- so a "jump" is the branch cut, not motion.
        return _wrap_to_pi(b - a) if periodic else b - a

    u_0, v_0 = u_domain.Mid, v_domain.Mid
    doc_u_00, doc_v_00 = document_params(u_0, v_0)
    doc_u_u, doc_v_u = document_params(u_0 + du, v_0)
    doc_u_v, doc_v_v = document_params(u_0, v_0 + dv)

    d_doc_u_du = delta(doc_u_00, doc_u_u, True) / du
    d_doc_u_dv = delta(doc_u_00, doc_u_v, True) / dv
    d_doc_v_du = delta(doc_v_00, doc_v_u, v_periodic) / du
    d_doc_v_dv = delta(doc_v_00, doc_v_v, v_periodic) / dv

    doc_u_origin = doc_u_00 - d_doc_u_du * u_0 - d_doc_u_dv * v_0
    doc_v_origin = doc_v_00 - d_doc_v_du * u_0 - d_doc_v_dv * v_0

    def param_map(u, v):
        return (
            doc_u_origin + d_doc_u_du * u + d_doc_u_dv * v,
            doc_v_origin + d_doc_v_du * u + d_doc_v_dv * v,
        )

    if not _param_map_holds(rhino_surface, surface, param_map):
        return None
    return param_map


def _param_map_holds(rhino_surface, surface, param_map):
    """Check a recovered map reproduces the surface across its whole domain.

    The probe that recovers the map only sees one point of it. Evaluating the
    document's own parameterization here — rather than a formula rewritten in this
    module — is what makes this a check against the format instead of a check
    against what this backend believes the format to be.

    This is also what tells an arc-length-parameterized wall (affine, exact) apart
    from a rational NURBS one that merely happens to be cylindrical (not affine).
    """
    u_domain = rhino_surface.Domain(0)
    v_domain = rhino_surface.Domain(1)

    for i in range(_PARAM_CHECK_SAMPLES):
        for j in range(_PARAM_CHECK_SAMPLES):
            u = u_domain.ParameterAt(i / (_PARAM_CHECK_SAMPLES - 1))
            v = v_domain.ParameterAt(j / (_PARAM_CHECK_SAMPLES - 1))
            expected = analytic_surface_point(surface, *param_map(u, v))
            point = rhino_surface.PointAt(u, v)
            if point.DistanceTo(Rhino.Geometry.Point3d(expected.x, expected.y, expected.z)) > TOL.absolute:
                return False
    return True


def _canonical_pcurve(pcurve, rhino_face):
    """Re-express a native pcurve in the parameter space the document defines.

    Every analytic tag needs this — Rhino measures all of them by arc length —
    while ``plane`` has its pcurve re-derived on rebuild instead and ``nurbs``
    carries its own parameterization with it. The map is affine, and a NURBS curve
    — rational or not — is affine-invariant, so mapping the control points and
    leaving the knots, weights and degree alone is exact rather than a refit.
    """
    _, param_map = _analytic_surface_and_param_map(rhino_face.UnderlyingSurface())
    if param_map is None:
        return pcurve

    points = []
    for point in pcurve._points:
        angle, height = param_map(point.x, point.y)
        points.append(Point(angle, height, 0.0))

    return NurbsCurve.from_parameters(
        points=points,
        weights=pcurve._weights,
        knots=pcurve._knots,
        mults=pcurve._mults,
        degree=pcurve._degree,
    )


def _extract_surface(rhino_face):
    """Extract a Rhino face's surface as the COMPAS type the document tags it with.

    Analytic faces come back as their analytic type — the bar ADR-0001 sets is
    representational fidelity, so a cylinder must leave here as a
    ``CylindricalSurface`` and not as a NURBS approximation of one. Anything the
    document has no analytic tag for is a NURBS surface natively, so ``nurbs``
    reproduces it exactly.

    Parameters
    ----------
    rhino_face : Rhino.Geometry.BrepFace

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

    surface, _ = _analytic_surface_and_param_map(underlying)
    if surface is not None:
        return surface

    nurbs = underlying.ToNurbsSurface()
    if nurbs is None:
        # Every Rhino surface converts to NURBS, so this is not a known shape --
        # but the loss policy (ADR-0001) is to raise rather than to skip the face
        # or approximate it, which is what dropped every analytic face for a
        # release.
        raise BrepError(f"Rhino backend cannot represent a face on surface type {type(underlying).__name__}")
    return _rhino_nurbs_surface_to_compas(nurbs)


def _frame_from_rhino_plane(rhino_plane):
    """Convert a Rhino.Geometry.Plane to a COMPAS Frame."""
    origin = rhino_plane.Origin
    xaxis = rhino_plane.XAxis
    yaxis = rhino_plane.YAxis
    return Frame(
        Point(origin.X, origin.Y, origin.Z),
        Vector(xaxis.X, xaxis.Y, xaxis.Z),
        Vector(yaxis.X, yaxis.Y, yaxis.Z),
    )


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


def _face_boundary_points(face):
    """Every 3D point that must sit inside a rebuilt planar face's surface patch.

    The edge *curves'* control points, not just the vertices: a circular cap loop
    has a single vertex on its rim, so sizing a patch from vertices leaves most of
    the disc off the surface — the whole circle then trims to a smaller one. A
    rational circle's control polygon bounds the circle, so its control points size
    the patch correctly. Falls back to a vertex where a trim has no edge curve.
    """
    for loop in face.loops:
        for trim in loop.trims:
            curve = trim.edge.curve if trim.edge is not None else None
            if isinstance(curve, Line):
                yield curve.start
                yield curve.end
            elif isinstance(curve, NurbsCurve):
                yield from curve._points
            elif trim.vertex is not None:
                yield trim.vertex.point


def _plane_surface_for_face(plane, face):
    """Build a bounded Rhino PlaneSurface large enough to contain a face's boundary."""
    rhino_plane = _rhino_plane_from_compas(plane)

    us = []
    vs = []
    for point in _face_boundary_points(face):
        success, u, v = rhino_plane.ClosestParameter(Rhino.Geometry.Point3d(point.x, point.y, point.z))
        if success:
            us.append(u)
            vs.append(v)

    if not us:
        raise BrepError("Cannot rebuild a planar face with no boundary curves")

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


def _face_pcurve_points(face):
    """Every control point of every pcurve on a face, in the document's parameter space."""
    return [point for loop in face.loops for trim in loop.trims if trim.curve_2d for point in trim.curve_2d._points]


def _is_analytic(surface):
    return isinstance(surface, (CylindricalSurface, SphericalSurface, ToroidalSurface, ConicalSurface))


def _seam_shift(values):
    """Where a periodic direction must start so the rebuilt surface's seam clears the trims.

    A Rhino surface of revolution spans exactly one period, while the document's
    analytic surfaces are unbounded and periodic — so a writer is free to place
    trims outside ``[0, 2pi]``. Moving the seam moves nothing but the seam;
    clipping the trims would move the geometry.
    """
    if not values:
        return 0.0
    if min(values) < -TOL.absolute or max(values) > 2 * math.pi + TOL.absolute:
        return min(values)
    return 0.0


def _parameter_shift(surface, face):
    """How far the rebuilt surface's parameter origin must move to clear the trims.

    Returned in the document's parameter space, so the same pair both places the
    surface and follows the pcurves onto it.
    """
    if not _is_analytic(surface):
        return 0.0, 0.0

    points = _face_pcurve_points(face)
    u_shift = _seam_shift([point.x for point in points])
    v_shift = _seam_shift([point.y for point in points]) if analytic_surface_v_is_periodic(surface) else 0.0
    return u_shift, v_shift


def _document_v_range(surface, face, v_shift):
    """The span of ``v`` a rebuilt analytic surface must cover.

    Three cases, and they are the tag's own geometry rather than a policy: a
    sphere's ``v`` is a latitude, so it is already bounded and the surface is the
    whole of it; a torus's ``v`` runs around the pipe, so it closes after one
    period; a cylinder's and a cone's are unbounded, so the extent has to come
    from the trims — which is exactly the extent the face occupies.
    """
    if isinstance(surface, SphericalSurface):
        return -math.pi / 2, math.pi / 2
    if analytic_surface_v_is_periodic(surface):
        return v_shift, v_shift + 2 * math.pi

    vs = [point.y for point in _face_pcurve_points(face)]
    if not vs:
        raise BrepError(f"Cannot rebuild a {type(surface).__name__} face with no pcurves")
    return min(vs), max(vs)


def _rhino_point(point):
    return Rhino.Geometry.Point3d(point.x, point.y, point.z)


def _rhino_vector(vector):
    return Rhino.Geometry.Vector3d(vector.x, vector.y, vector.z)


def _analytic_profile(surface, u, v_min, v_max):
    """The ``u = const`` generating curve of an analytic surface, parameterized by the document's ``v``.

    Every point of it comes from the document's own evaluator, so the profile is
    exact by construction rather than by a formula this module restates: a
    cylinder's and a cone's generating lines are affine in ``v``, and a sphere's
    and a torus's are circles swept by ``v`` as an angle.
    """
    frame = surface.frame
    radial = frame.xaxis * math.cos(u) + frame.yaxis * math.sin(u)

    if isinstance(surface, (CylindricalSurface, ConicalSurface)):
        start = analytic_surface_point(surface, u, v_min)
        end = analytic_surface_point(surface, u, v_max)
        return Rhino.Geometry.LineCurve(Rhino.Geometry.Line(_rhino_point(start), _rhino_point(end)), v_min, v_max)

    if isinstance(surface, SphericalSurface):
        centre, radius = frame.point, surface.radius
    else:
        centre, radius = frame.point + radial * surface.radius_axis, surface.radius_pipe

    # In this plane the angle from the x-axis is the document's v exactly: a
    # latitude for the sphere, the angle about the pipe for the torus.
    plane = Rhino.Geometry.Plane(_rhino_point(centre), _rhino_vector(radial), _rhino_vector(frame.zaxis))
    arc = Rhino.Geometry.Arc(Rhino.Geometry.Circle(plane, radius), Rhino.Geometry.Interval(v_min, v_max))
    return Rhino.Geometry.ArcCurve(arc, v_min, v_max)


def _analytic_surface_for_face(surface, face):
    """Build a Rhino surface for an analytic face, parameterized as the document is.

    This is the one place the rebuilt parameterization is pinned, and it is why
    the trims land without conversion. It cannot be delegated to Rhino's own
    constructors: measured, ``Sphere.ToRevSurface`` happens to agree with the
    document, but ``Torus.ToRevSurface`` is arc-length in *both* directions and
    ``Cone.ToRevSurface`` measures ``v`` as a height from the apex where the
    document measures a distance along the generating line from the base. Any of
    those puts every trim in the wrong place. Revolving the document's own
    generating curve agrees with the document by construction, for all four.
    """
    u_shift, v_shift = _parameter_shift(surface, face)
    v_min, v_max = _document_v_range(surface, face, v_shift)

    frame = surface.frame
    axis = Rhino.Geometry.Line(_rhino_point(frame.point), _rhino_point(frame.point + frame.zaxis))
    profile = _analytic_profile(surface, u_shift, v_min, v_max)

    revolved = Rhino.Geometry.RevSurface.Create(profile, axis)
    if revolved is None:
        raise BrepError(f"Failed to rebuild a Rhino surface for a {type(surface).__name__} face")
    return revolved


def _surface_to_rhino(surface, face):
    """Build the Rhino surface a face sits on."""
    if isinstance(surface, Plane):
        return _plane_surface_for_face(surface, face)
    if _is_analytic(surface):
        return _analytic_surface_for_face(surface, face)
    if isinstance(surface, NurbsSurface):
        return nurbs_surface_to_rhino(surface)
    raise BrepError(f"Rhino backend cannot rebuild a face on surface type {type(surface).__name__}")


def _trim_pcurve_to_rhino(trim, shift):
    """Convert a trim's serialized pcurve to a Rhino curve, following any seam shift."""
    pcurve = nurbs_curve_to_rhino(trim.curve_2d)
    u_shift, v_shift = shift
    if u_shift or v_shift:
        pcurve.Translate(Rhino.Geometry.Vector3d(-u_shift, -v_shift, 0.0))
    return pcurve


def _is_degenerate(rhino_curve):
    """Whether an edge curve has no extent — a boundary collapsed to a point.

    Measured by length, not by whether the endpoints coincide: a full circular
    seam starts and ends at the same point too, and is not degenerate. OCC writes
    a sphere's pole as a zero-length line of exactly this kind.
    """
    return rhino_curve.GetLength() <= TOL.absolute


def _singular_trim_vertex(trim, vertex_index, collapsed_edges):
    """The index of the vertex a trim collapses to, or None if it runs along an edge.

    Covers both of the document's spellings: a trim with no edge (Rhino's) and a
    trim along a degenerate edge (OCC's).
    """
    if trim.edge is None:
        return vertex_index[id(trim.vertex)]
    return collapsed_edges.get(id(trim.edge))


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
    collapsed_edges = {}
    for edge in brep._edges:
        curve = _edge_curve_to_rhino(edge.curve)
        if _is_degenerate(curve):
            # The document has two spellings for "this boundary collapses to a
            # point", and this is the one Rhino does not use: OCC writes a pole or
            # an apex as a zero-length edge, while Rhino writes a trim with no edge
            # at all. Rhino cannot hold a degenerate edge -- it rejects the whole
            # Brep -- so the trims along it become singular trims, which is Rhino's
            # spelling of the same thing.
            collapsed_edges[id(edge)] = vertex_index[id(edge.first_vertex)]
            continue
        edge_index[id(edge)] = len(edge_index)
        builder.add_edge(
            curve,
            vertex_index[id(edge.first_vertex)],
            vertex_index[id(edge.last_vertex)],
        )

    for face in brep._faces:
        surface = face.surface
        rhino_surface = _surface_to_rhino(surface, face)
        face_builder = builder.add_face(rhino_surface, face.is_reversed)

        is_planar = isinstance(surface, Plane)
        rhino_plane = _rhino_plane_from_compas(surface) if is_planar else None
        # A moved seam moves the rebuilt surface's parameter origin; the pcurves follow it.
        shift = _parameter_shift(surface, face)

        loops = [(face.outer_loop, Rhino.Geometry.BrepLoopType.Outer)]
        loops += [(loop, Rhino.Geometry.BrepLoopType.Inner) for loop in face._inner_loops]

        for loop, loop_type in loops:
            loop_builder = face_builder.add_loop(loop_type)
            for trim in loop.trims:
                singular_vertex = _singular_trim_vertex(trim, vertex_index, collapsed_edges)

                if singular_vertex is None and is_planar:
                    # A plane's parameterization is not pinned by the document
                    # (point and normal fix no x-axis), so the serialized pcurve
                    # cannot be trusted here — re-derive it against the rebuilt plane.
                    pcurve = _project_curve_to_plane(trim.edge.curve, rhino_plane)
                else:
                    # A singular trim (a sphere's pole, a cone's apex) collapses to a
                    # vertex and has no edge curve to project, so its serialized
                    # pcurve is the only description of it.
                    pcurve = _trim_pcurve_to_rhino(trim, shift)

                # Every pcurve above runs in its edge's direction, as the document
                # defines; Rhino wants the trim's. This applies to a singular trim
                # too — OCC reverses the one along a pole, and a loop whose trims do
                # not run head to tail in parameter space is not a loop.
                if trim.is_reversed:
                    pcurve.Reverse()

                if singular_vertex is not None:
                    loop_builder.add_trim(
                        pcurve,
                        -1,
                        False,
                        _iso_status_for_pcurve(pcurve, rhino_surface),
                        singular_vertex,
                    )
                    continue

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
    """Extract the 2D parametric curve from a Rhino BrepTrim, returning NurbsCurve or None.

    Two things about the native curve are Rhino's convention rather than the
    document's, and both are undone here.

    It comes out in Rhino's parameter space, which is not the document's for every
    surface — see :func:`_canonical_pcurve`.

    It also runs in the *trim's* direction, while the document's ``curve_2d`` runs in
    its **edge's**, with ``is_reversed`` saying how the trim uses it. That is what OCC
    writes and reads, and what this backend's own planar rebuild already assumes when
    it projects an edge curve and reverses it. Emitting the trim's direction instead
    made ``curve_2d`` mean one thing in a Rhino document and the opposite in an OCC
    one — a reversed trim's pcurve started at the far end of its edge — so an
    OCC-authored face could not close its loop here.
    """
    curve = rhino_trim.TrimCurve
    if curve is None:
        return None
    nurbs = curve.ToNurbsCurve()
    if nurbs is None:
        return None

    # A singular trim has no edge, so there is neither a direction nor a domain to
    # align to; its pcurve stands alone.
    edge = rhino_trim.Edge
    if edge is None:
        return _canonical_pcurve(_rhino_nurbs_curve_to_compas(nurbs), rhino_trim.Face)

    if rhino_trim.IsReversed():
        nurbs.Reverse()
    pcurve = _canonical_pcurve(_rhino_nurbs_curve_to_compas(nurbs), rhino_trim.Face)
    return _align_pcurve_to_edge(pcurve, _extract_edge_curve(edge))


def _edge_curve_domain(curve):
    """The parameter range a reader will give this edge curve once it rebuilds it.

    A line is written as two points, so both backends rebuild it over ``[0, length]``.
    A NURBS curve carries its own knots.
    """
    if isinstance(curve, Line):
        return 0.0, curve.length
    return curve._knots[0], curve._knots[-1]


def _align_pcurve_to_edge(pcurve, edge_curve):
    """Reparameterize a pcurve onto its edge curve's domain.

    A pcurve and the 3D curve of the edge it runs along describe the same curve in
    two spaces, so a reader must be able to evaluate both at the same parameter.
    Rhino does not guarantee that: a trim's domain is its own, unrelated to the edge
    curve's, so Rhino's pcurve for a circular seam came out over ``(0, pi)`` while
    the edge curve it belongs to ran over ``(-pi, 0)``. OCC treats the mismatch as an
    edge with no range and fails to sew the face at all, which is why an
    OCC-authored document reads here but a Rhino-authored one did not.

    Only the knots move — the control points, weights and degree are untouched — so
    the pcurve's geometry is unchanged and this is exact rather than a refit.
    """
    start, end = _edge_curve_domain(edge_curve)
    knots = pcurve._knots
    span = knots[-1] - knots[0]
    if span == 0.0 or (knots[0] == start and knots[-1] == end):
        return pcurve

    scale = (end - start) / span
    return NurbsCurve.from_parameters(
        points=pcurve._points,
        weights=pcurve._weights,
        knots=[start + (knot - knots[0]) * scale for knot in knots],
        mults=pcurve._mults,
        degree=pcurve._degree,
    )


def _loop_role(rhino_loop) -> str:
    """Map a Rhino BrepLoopType onto the exchange document's loop role.

    Rhino's other loop types (Slit, Curveonsurface, Ptonsurface, Unknown) have no
    role in this format, and the loss policy is to raise rather than guess one.
    """
    loop_type = rhino_loop.LoopType
    if loop_type == Rhino.Geometry.BrepLoopType.Outer:
        return LOOP_OUTER
    if loop_type == Rhino.Geometry.BrepLoopType.Inner:
        return LOOP_INNER
    raise BrepError(f"Cannot serialize a loop of type {loop_type}; expected Outer or Inner")


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
        outer_count = 0
        for rl in rf.Loops:
            role = _loop_role(rl)
            trims = []
            for rt in rl.Trims:
                pcurve = _extract_trim_pcurve(rt)
                if pcurve is None:
                    raise BrepError("Cannot serialize a trim without a pcurve")
                re_obj = rt.Edge
                if re_obj is None:
                    # Singular trim (e.g. the pole of a sphere). It has no edge, so
                    # it is pinned by its pcurve plus the vertex it collapses to.
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
                        "curve_2d": pcurve.__data__,
                    }
                )
            if trims:
                outer_count += role == LOOP_OUTER
                loops.append(loop_to_data(role, trims))

        if loops:
            if outer_count != 1:
                raise BrepError(f"Cannot serialize a face with {outer_count} outer loops; expected exactly 1")
            face_list.append(
                {
                    "surface": surface_data,
                    "is_reversed": rf.OrientationIsReversed,
                    "loops": loops,
                }
            )

    return {
        "version": EXCHANGE_VERSION,
        "vertices": vertex_list,
        "edges": edge_list,
        "faces": face_list,
    }
