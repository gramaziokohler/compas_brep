"""Rhino boolean and geometric operations."""

from __future__ import annotations

import Rhino  # type: ignore
from compas.geometry import Point, Polyline
from compas.tolerance import TOL
from compas_rhino.conversions import plane_to_rhino

from compas_brep.backend.rhino.conversion import brep_to_rhino, rhino_to_brep


# =============================================================================
# Boolean operations
# =============================================================================


def boolean_difference(brep_a, brep_b):
    """Boolean subtraction: A - B."""
    shape_a = brep_to_rhino(brep_a)
    shape_b = brep_to_rhino(brep_b)
    results = Rhino.Geometry.Brep.CreateBooleanDifference(
        [shape_a],
        [shape_b],
        TOL.absolute,
    )
    if not results:
        raise RuntimeError("Boolean difference ended with no result")
    return rhino_to_brep(results[0])


def boolean_union(brep_a, brep_b):
    """Boolean union: A + B."""
    shape_a = brep_to_rhino(brep_a)
    shape_b = brep_to_rhino(brep_b)
    results = Rhino.Geometry.Brep.CreateBooleanUnion(
        [shape_a, shape_b],
        TOL.absolute,
    )
    if not results:
        raise RuntimeError("Boolean union ended with no result")
    return rhino_to_brep(results[0])


def boolean_intersection(brep_a, brep_b):
    """Boolean intersection: A & B."""
    shape_a = brep_to_rhino(brep_a)
    shape_b = brep_to_rhino(brep_b)
    results = Rhino.Geometry.Brep.CreateBooleanIntersection(
        [shape_a],
        [shape_b],
        TOL.absolute,
    )
    if not results:
        raise RuntimeError("Boolean intersection ended with no result")
    return rhino_to_brep(results[0])


# =============================================================================
# Instance operations
# =============================================================================


def rhino_trimmed(brep, plane):
    """Rhino implementation of brep.trimmed(plane)."""
    shape = brep_to_rhino(brep)
    rhino_plane = plane_to_rhino(plane)
    results = shape.Trim(rhino_plane, TOL.absolute)
    if not results:
        raise RuntimeError("Trim operation ended with no result")
    result = results[0]
    capped = result.CapPlanarHoles(TOL.absolute)
    if capped:
        result = capped
    return rhino_to_brep(result)


def rhino_split(brep, cutter):
    """Rhino implementation of brep.split(cutter_brep)."""
    shape = brep_to_rhino(brep)
    cutter_shape = brep_to_rhino(cutter)
    results = shape.Split(cutter_shape, TOL.absolute)
    return [rhino_to_brep(r) for r in results]


def rhino_slice(brep, plane):
    """Rhino implementation of brep.slice(plane) — returns intersection polylines."""
    shape = brep_to_rhino(brep)
    rhino_plane = plane_to_rhino(plane)
    curves = Rhino.Geometry.Brep.CreateContourCurves(shape, rhino_plane)
    polylines = []
    for crv in curves:
        # Sample the curve to produce a polyline
        nurbs = crv.ToNurbsCurve()
        if nurbs is None:
            continue
        t0 = nurbs.Domain[0]
        t1 = nurbs.Domain[1]
        n_pts = 32
        pts = []
        for i in range(n_pts + 1):
            t = t0 + (t1 - t0) * i / n_pts
            p = nurbs.PointAt(t)
            pts.append(Point(p.X, p.Y, p.Z))
        polylines.append(Polyline(pts))
    return polylines


def rhino_fillet(brep, radius, edges=None):
    """Fillet edges of a Brep."""
    import Rhino.Geometry as rg

    rhino_brep = brep_to_rhino(brep)
    if edges is not None:
        edge_indices = edges
    else:
        edge_indices = list(range(rhino_brep.Edges.Count))

    fillets = rg.Brep.CreateFilletEdges(
        rhino_brep,
        edge_indices,
        [radius] * len(edge_indices),
        [radius] * len(edge_indices),
        rg.BlendType.Fillet,
        rg.RailType.DistanceFromEdge,
        0.001,
    )
    if fillets and len(fillets) > 0:
        return rhino_to_brep(fillets[0])
    raise RuntimeError("Fillet operation failed")


def rhino_cap_planar_holes(brep):
    """Cap planar holes in a Brep."""
    rhino_brep = brep_to_rhino(brep)
    capped = rhino_brep.CapPlanarHoles(0.001)
    if capped is not None:
        return rhino_to_brep(capped)
    return brep


def rhino_contains(brep, point):
    """Check if a point is contained inside a solid Brep."""
    import Rhino.Geometry as rg

    rhino_brep = brep_to_rhino(brep)
    if not rhino_brep.IsSolid:
        return False
    pt = rg.Point3d(point.x, point.y, point.z)
    return rhino_brep.IsPointInside(pt, 0.001, False)


def rhino_flip(brep):
    """Flip face orientations of a Brep."""
    rhino_brep = brep_to_rhino(brep)
    rhino_brep.Flip()
    return rhino_to_brep(rhino_brep)


def rhino_fix(brep):
    """Repair a Brep."""
    rhino_brep = brep_to_rhino(brep)
    rhino_brep.Repair(0.001)
    return rhino_to_brep(rhino_brep)


def rhino_tessellate(brep, linear_deflection=0.1, n=16, n_curves=64):
    """Tessellate a Brep via Rhino.Geometry — returns (Mesh, list[Polyline])."""
    raise NotImplementedError("tessellate not yet implemented for Rhino backend")


def rhino_rebuild(brep):
    """Rebuild the native Rhino Brep from canonical Python topology data."""
    brep_to_rhino(brep)
