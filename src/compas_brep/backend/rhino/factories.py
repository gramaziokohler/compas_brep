"""Rhino primitive constructors and shape builders."""

from __future__ import annotations

import Rhino  # type: ignore
from compas.geometry import Polyline
from compas.tolerance import TOL
from compas_rhino.conversions import (
    box_to_rhino,
    cone_to_rhino,
    cylinder_to_rhino,
    mesh_to_rhino,
    sphere_to_rhino,
    torus_to_rhino,
    vector_to_rhino,
)

from compas_brep.backend.rhino.conversion import (
    _compas_nurbs_curve_to_rhino,
    brep_to_rhino,
    rhino_to_brep,
)

# =============================================================================
# Primitive constructors
# =============================================================================


def make_box(box):
    """Create a Brep from a COMPAS Box using Rhino."""
    rhino_box = box_to_rhino(box)
    return rhino_to_brep(rhino_box.ToBrep())


def make_cylinder(cylinder):
    """Create a Brep from a COMPAS Cylinder using Rhino."""
    rhino_cylinder = cylinder_to_rhino(cylinder)
    return rhino_to_brep(rhino_cylinder.ToBrep(True, True))


def make_sphere(sphere):
    """Create a Brep from a COMPAS Sphere using Rhino."""
    rhino_sphere = sphere_to_rhino(sphere)
    return rhino_to_brep(rhino_sphere.ToBrep())


def make_cone(cone):
    """Create a Brep from a COMPAS Cone using Rhino."""
    rhino_cone = cone_to_rhino(cone)
    return rhino_to_brep(rhino_cone.ToBrep(True))


def make_torus(torus):
    """Create a Brep from a COMPAS Torus using Rhino."""
    rhino_torus = torus_to_rhino(torus)
    return rhino_to_brep(rhino_torus.ToBrep())


def make_from_mesh(mesh):
    """Create a Brep from a COMPAS Mesh using Rhino."""
    rhino_mesh = mesh_to_rhino(mesh)
    return rhino_to_brep(Rhino.Geometry.Brep.CreateFromMesh(rhino_mesh, True))


def make_extrusion(curve_or_profile, vector):
    """Create a Brep by extruding a curve/profile along a vector."""
    from compas_rhino.conversions import polyline_to_rhino_curve

    if hasattr(curve_or_profile, "points"):
        points = list(curve_or_profile.points)
        polyline = Polyline(points + [points[0]])
        rhino_curve = polyline_to_rhino_curve(polyline)
    else:
        raise NotImplementedError("Extrusion currently supports polygon profiles only")

    extrusion = Rhino.Geometry.Surface.CreateExtrusion(
        rhino_curve,
        vector_to_rhino(vector),
    )
    if extrusion is None:
        raise RuntimeError("Failed to create extrusion")

    rhino_brep = extrusion.ToBrep()
    capped = rhino_brep.CapPlanarHoles(TOL.absolute)
    if capped:
        rhino_brep = capped

    return rhino_to_brep(rhino_brep)


def make_loft(profiles):
    """Create a Brep by lofting through curves."""
    from compas_rhino.conversions import curve_to_rhino

    rhino_curves = []
    for profile in profiles:
        if hasattr(profile, "_knots"):
            rhino_curves.append(_compas_nurbs_curve_to_rhino(profile))
        else:
            rhino_curves.append(curve_to_rhino(profile))

    start = Rhino.Geometry.Point3d.Unset
    end = Rhino.Geometry.Point3d.Unset
    loft_type = Rhino.Geometry.LoftType.Normal

    results = Rhino.Geometry.Brep.CreateFromLoft(
        rhino_curves,
        start,
        end,
        loft_type,
        closed=False,
    )
    if not results:
        raise RuntimeError("Loft operation ended with no result")

    return rhino_to_brep(results[0])


def from_native(native_brep):
    """Create a Brep from a native Rhino.Geometry.Brep."""
    return rhino_to_brep(native_brep)


# =============================================================================
# Additional shape builders
# =============================================================================


def rhino_sweep(profile, path):
    """Create a Brep by sweeping a profile along a path."""
    import Rhino.Geometry as rg

    profile_brep = brep_to_rhino(profile)
    path_brep = brep_to_rhino(path)

    # Extract curves from path
    path_curves = [path_brep.Edges[i].EdgeCurve for i in range(path_brep.Edges.Count)]
    path_curve = path_curves[0] if len(path_curves) == 1 else rg.Curve.JoinCurves(path_curves)[0]

    # Extract profile curve (first edge loop)
    profile_curves = [profile_brep.Edges[i].EdgeCurve for i in range(profile_brep.Edges.Count)]

    sweep = rg.SweepOneRail()
    results = sweep.PerformSweep(path_curve, profile_curves)
    if results and len(results) > 0:
        return rhino_to_brep(results[0])
    raise RuntimeError("Sweep operation failed")


def rhino_pipe(path, radius):
    """Create a pipe by sweeping a circle along a path."""
    import Rhino.Geometry as rg

    path_brep = brep_to_rhino(path)
    path_curves = [path_brep.Edges[i].EdgeCurve for i in range(path_brep.Edges.Count)]
    path_curve = path_curves[0] if len(path_curves) == 1 else rg.Curve.JoinCurves(path_curves)[0]

    pipes = rg.Brep.CreatePipe(path_curve, radius, False, rg.PipeCapMode.Flat, True, 0.001, 0.01)
    if pipes and len(pipes) > 0:
        return rhino_to_brep(pipes[0])
    raise RuntimeError("Pipe operation failed")


def rhino_from_curves(curves):
    """Create a Brep from planar boundary curves."""
    import Rhino.Geometry as rg

    rhino_curves = []
    for curve in curves:
        from compas_brep.curves.nurbs import NurbsCurve as _NC

        if isinstance(curve, _NC):
            rhino_curves.append(_compas_nurbs_curve_to_rhino(curve))
        else:
            # Line
            p0 = rg.Point3d(curve.start.x, curve.start.y, curve.start.z)
            p1 = rg.Point3d(curve.end.x, curve.end.y, curve.end.z)
            rhino_curves.append(rg.LineCurve(p0, p1))

    breps = rg.Brep.CreatePlanarBreps(rhino_curves, 0.001)
    if breps and len(breps) > 0:
        return rhino_to_brep(breps[0])
    raise RuntimeError("Failed to create Brep from curves")


def rhino_from_breps(breps):
    """Join multiple Breps into one by sewing overlapping edges."""
    import Rhino.Geometry as rg

    rhino_breps = [brep_to_rhino(b) for b in breps]
    joined = rg.Brep.JoinBreps(rhino_breps, 0.001)
    if joined and len(joined) > 0:
        return rhino_to_brep(joined[0])
    raise RuntimeError("Failed to join Breps")
