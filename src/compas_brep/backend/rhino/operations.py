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


def rhino_copy(brep):
    """Return a deep copy of a Brep."""
    return rhino_to_brep(brep_to_rhino(brep).Duplicate())


def rhino_transform(brep, transformation):
    """Apply a COMPAS Transformation to a Brep and return the result."""
    rhino_brep = brep_to_rhino(brep).Duplicate()
    m = transformation.matrix
    xform = Rhino.Geometry.Transform(1.0)
    xform.M00 = m[0][0]; xform.M01 = m[0][1]; xform.M02 = m[0][2]; xform.M03 = m[0][3]  # noqa: E702
    xform.M10 = m[1][0]; xform.M11 = m[1][1]; xform.M12 = m[1][2]; xform.M13 = m[1][3]  # noqa: E702
    xform.M20 = m[2][0]; xform.M21 = m[2][1]; xform.M22 = m[2][2]; xform.M23 = m[2][3]  # noqa: E702
    xform.M30 = m[3][0]; xform.M31 = m[3][1]; xform.M32 = m[3][2]; xform.M33 = m[3][3]  # noqa: E702
    rhino_brep.Transform(xform)
    return rhino_to_brep(rhino_brep)


def rhino_area(brep):
    """Return the surface area of a Brep."""
    mp = Rhino.Geometry.AreaMassProperties.Compute(brep_to_rhino(brep))
    return mp.Area if mp is not None else 0.0


def rhino_volume(brep):
    """Return the enclosed volume of a solid Brep."""
    mp = Rhino.Geometry.VolumeMassProperties.Compute(brep_to_rhino(brep))
    return mp.Volume if mp is not None else 0.0


def rhino_centroid(brep):
    """Return the area centroid of a Brep as a COMPAS Point."""
    mp = Rhino.Geometry.AreaMassProperties.Compute(brep_to_rhino(brep))
    if mp is None:
        return Point(0, 0, 0)
    c = mp.Centroid
    return Point(c.X, c.Y, c.Z)


def rhino_aabb(brep):
    """Return the axis-aligned bounding box of a Brep as a COMPAS Box."""
    from compas.geometry import Box, Frame

    bbox = brep_to_rhino(brep).GetBoundingBox(True)
    mn, mx = bbox.Min, bbox.Max
    cx, cy, cz = (mn.X + mx.X) / 2, (mn.Y + mx.Y) / 2, (mn.Z + mx.Z) / 2
    return Box(Frame(Point(cx, cy, cz)), mx.X - mn.X, mx.Y - mn.Y, mx.Z - mn.Z)


def rhino_is_solid(brep):
    """Return True if the Brep is a closed solid."""
    return brep_to_rhino(brep).IsSolid


def rhino_is_valid(brep):
    """Return True if the Brep passes Rhino's validity check."""
    return brep_to_rhino(brep).IsValid


def rhino_rebuild(brep, data: dict) -> None:
    """Rebuild native Rhino.Geometry.Brep from a STEP-inspired JSON data dict.

    Constructs Python topology from the data dict (same intermediate objects as
    occ_rebuild), then calls brep_to_rhino to build the native Rhino shape which
    is cached on brep._native_brep.
    """
    from compas.geometry import Line, Plane, Point, Vector

    from compas_brep.curves.nurbs import NurbsCurve
    from compas_brep.edge import BrepEdge
    from compas_brep.face import BrepFace
    from compas_brep.loop import BrepLoop
    from compas_brep.surfaces.nurbs import NurbsSurface
    from compas_brep.trim import BrepTrim
    from compas_brep.vertex import BrepVertex

    vertices = [BrepVertex(Point(*xyz)) for xyz in data["vertices"]]

    edges = []
    for ed in data["edges"]:
        start = vertices[ed["start"]]
        end = vertices[ed["end"]]
        cd = ed["curve"]
        if cd["type"] == "line":
            pts = cd["data"]
            curve = Line(Point(*pts[0]), Point(*pts[1]))
        else:
            curve = NurbsCurve.__from_data__(cd["data"])
        edges.append(BrepEdge(start, end, curve=curve))

    all_loops = []
    faces = []
    for fd in data["faces"]:
        sd = fd["surface"]
        if sd["type"] == "plane":
            pd = sd["data"]
            surface = Plane(Point(*pd["point"]), Vector(*pd["normal"]))
        else:
            surface = NurbsSurface.__from_data__(sd["data"])

        face_loops = []
        for loop_data in fd["loops"]:
            trims = [
                BrepTrim(
                    edge=edges[td["edge"]],
                    is_reversed=td.get("is_reversed", False),
                    curve_2d=NurbsCurve.__from_data__(td["curve_2d"]) if td.get("curve_2d") else None,
                )
                for td in loop_data
            ]
            loop = BrepLoop(trims=trims)
            face_loops.append(loop)
            all_loops.append(loop)

        if face_loops:
            face = BrepFace(
                face_loops[0],
                surface=surface,
                is_reversed=fd.get("is_reversed", False),
            )
            for inner_loop in face_loops[1:]:
                face.add_loop(inner_loop)
            faces.append(face)

    brep._vertices = vertices
    brep._edges = edges
    brep._loops = all_loops
    brep._faces = faces
    brep._topology_loaded = True
    brep_to_rhino(brep)
