"""OCC primitive constructors and shape builders."""

from __future__ import annotations

from compas.geometry import Point
from warnings import warn

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
    BRepPrimAPI_MakeTorus,
)
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from compas_brep.backend.occ.conversion import (
    _frame_to_ax2,
    _loop_to_occ_wire,
    _nurbs_curve_to_occ,
    _nurbs_surface_to_occ,
    _points_to_occ_wire,
    brep_to_occ,
    occ_to_brep,
)


# =============================================================================
# Primitive constructors
# =============================================================================


def make_box(box):
    """Create a Brep from a COMPAS Box using OCC.

    COMPAS Box is centered at its frame. OCC's MakeBox builds from a corner point
    to (+xsize, +ysize, +zsize), so we offset the origin to the min corner.
    """
    frame = box.frame
    corner = frame.point + frame.xaxis * (-box.xsize / 2) + frame.yaxis * (-box.ysize / 2) + frame.zaxis * (-box.zsize / 2)
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

    if cap_ends:
        warn("cap_ends parameter is not implemented in OCC backend")

    vec = gp_Vec(vector.x, vector.y, vector.z)

    if hasattr(curve_or_profile, "points"):
        # Polygon or curve with .points
        wire = _points_to_occ_wire(list(curve_or_profile.points))
        face = BRepBuilderAPI_MakeFace(wire, True).Face()
    elif hasattr(curve_or_profile, "outer_loop"):
        # BrepFace — build an OCC face from its loop and extrude
        from compas_brep.brep import Brep as _Brep

        tmp = _Brep()
        tmp._faces = [curve_or_profile]
        tmp._edges = list(curve_or_profile.edges)
        tmp._vertices = list(curve_or_profile.vertices)
        tmp._loops = [curve_or_profile.outer_loop]
        occ_shape = brep_to_occ(tmp)
        face_exp = TopExp_Explorer(occ_shape, TopAbs_FACE)
        if not face_exp.More():
            raise ValueError("Could not extract face from BrepFace for extrusion")
        face = TopoDS.Face_s(face_exp.Current())
    else:
        raise NotImplementedError(f"Unsupported extrusion profile type: {type(curve_or_profile)}")

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
# Additional shape builders
# =============================================================================


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
