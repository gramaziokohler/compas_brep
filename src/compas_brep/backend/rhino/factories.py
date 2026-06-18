"""Rhino primitive constructors and shape builders."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

import Rhino  # type: ignore
import Rhino.Geometry as rg  # type: ignore
from compas.geometry import Curve
from compas.geometry import Polygon
from compas.geometry import Polyline
from compas.geometry import Vector
from compas.tolerance import TOL
from compas_rhino.conversions import box_to_rhino
from compas_rhino.conversions import cone_to_rhino
from compas_rhino.conversions import curve_to_rhino
from compas_rhino.conversions import cylinder_to_rhino
from compas_rhino.conversions import mesh_to_rhino
from compas_rhino.conversions import polyline_to_rhino_curve
from compas_rhino.conversions import sphere_to_rhino
from compas_rhino.conversions import torus_to_rhino
from compas_rhino.conversions import vector_to_rhino

from compas_brep.curves import NurbsCurve

from .conversion import brep_to_rhino
from .conversion import nurbs_curve_to_rhino
from .conversion import rhino_to_brep

if TYPE_CHECKING:
    from compas.datastructures import Mesh
    from compas.geometry import Box
    from compas.geometry import Cone
    from compas.geometry import Cylinder
    from compas.geometry import Sphere
    from compas.geometry import Torus

    from compas_brep.brep import Brep

# =============================================================================
# Primitive constructors
# =============================================================================


def make_box(box: Box) -> Brep:
    """Create a Brep from a COMPAS Box using Rhino."""
    rhino_box = box_to_rhino(box)
    return rhino_to_brep(rhino_box.ToBrep())


def make_cylinder(cylinder: Cylinder) -> Brep:
    """Create a Brep from a COMPAS Cylinder using Rhino."""
    rhino_cylinder = cylinder_to_rhino(cylinder)
    return rhino_to_brep(rhino_cylinder.ToBrep(True, True))


def make_sphere(sphere: Sphere) -> Brep:
    """Create a Brep from a COMPAS Sphere using Rhino."""
    rhino_sphere = sphere_to_rhino(sphere)
    return rhino_to_brep(rhino_sphere.ToBrep())


def make_cone(cone: Cone) -> Brep:
    """Create a Brep from a COMPAS Cone using Rhino."""
    rhino_cone = cone_to_rhino(cone)
    return rhino_to_brep(rhino_cone.ToBrep(True))


def make_torus(torus: Torus) -> Brep:
    """Create a Brep from a COMPAS Torus using Rhino."""
    rhino_torus = torus_to_rhino(torus)
    return rhino_to_brep(rhino_torus.ToBrep())


def make_from_mesh(mesh: Mesh) -> Brep:
    """Create a Brep from a COMPAS Mesh using Rhino."""
    rhino_mesh = mesh_to_rhino(mesh)
    return rhino_to_brep(Rhino.Geometry.Brep.CreateFromMesh(rhino_mesh, True))


def _to_rhino_curve(curve_or_profile: Polyline | Polygon | Curve) -> Any:
    if isinstance(curve_or_profile, (Polyline, Polygon)):
        points = curve_or_profile.points  # type: ignore
        polyline = Polyline(points + [points[0]])
        return polyline_to_rhino_curve(polyline)
    elif hasattr(curve_or_profile, "native_curve"):
        return curve_or_profile.native_curve  # type: ignore

    raise TypeError(f"No idea what to do with a: {type(curve_or_profile)}")


def make_extrusion(curve_or_profile: Polyline | Polygon | Curve, vector: Vector, cap_ends: bool = True) -> Brep:
    """Create a Brep by extruding a curve/profile along a vector."""

    rhino_curve = _to_rhino_curve(curve_or_profile)
    extrusion = Rhino.Geometry.Surface.CreateExtrusion(
        rhino_curve,
        vector_to_rhino(vector),
    )
    if extrusion is None:
        raise RuntimeError("Failed to create extrusion")

    rhino_brep = extrusion.ToBrep()
    if cap_ends:
        capped = rhino_brep.CapPlanarHoles(TOL.absolute)
        if capped:
            rhino_brep = capped

    return rhino_to_brep(rhino_brep)


def make_loft(profiles: list[Any]) -> Brep:
    """Create a Brep by lofting through curves."""
    rhino_curves = []
    for profile in profiles:
        if hasattr(profile, "_knots"):
            rhino_curves.append(nurbs_curve_to_rhino(profile))
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


def from_native(native_brep: Any) -> Brep:
    """Create a Brep from a native Rhino.Geometry.Brep."""
    return rhino_to_brep(native_brep)


# =============================================================================
# Additional shape builders
# =============================================================================


def rhino_sweep(profile: Brep, path: Brep) -> Brep:
    """Create a Brep by sweeping a profile along a path."""
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


def rhino_pipe(path: Brep, radius: float) -> Brep:
    """Create a pipe by sweeping a circle along a path."""
    path_brep = brep_to_rhino(path)
    path_curves = [path_brep.Edges[i].EdgeCurve for i in range(path_brep.Edges.Count)]
    path_curve = path_curves[0] if len(path_curves) == 1 else rg.Curve.JoinCurves(path_curves)[0]

    pipes = rg.Brep.CreatePipe(path_curve, radius, False, rg.PipeCapMode.Flat, True, 0.001, 0.01)
    if pipes and len(pipes) > 0:
        return rhino_to_brep(pipes[0])
    raise RuntimeError("Pipe operation failed")


def rhino_from_curves(curves: list[Any]) -> Brep:
    """Create a Brep from planar boundary curves."""
    rhino_curves = []
    for curve in curves:
        if isinstance(curve, NurbsCurve):
            rhino_curves.append(nurbs_curve_to_rhino(curve))
        else:
            # Line
            p0 = rg.Point3d(curve.start.x, curve.start.y, curve.start.z)
            p1 = rg.Point3d(curve.end.x, curve.end.y, curve.end.z)
            rhino_curves.append(rg.LineCurve(p0, p1))

    breps = rg.Brep.CreatePlanarBreps(rhino_curves, 0.001)
    if breps and len(breps) > 0:
        return rhino_to_brep(breps[0])
    raise RuntimeError("Failed to create Brep from curves")


def rhino_from_breps(breps: list[Brep]) -> Brep:
    """Join multiple Breps into one by sewing overlapping edges."""
    rhino_breps = [brep_to_rhino(b) for b in breps]
    joined = rg.Brep.JoinBreps(rhino_breps, 0.001)
    if joined and len(joined) > 0:
        return rhino_to_brep(joined[0])
    raise RuntimeError("Failed to join Breps")
