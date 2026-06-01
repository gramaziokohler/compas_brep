"""OCC boolean and geometric operations."""

from __future__ import annotations

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_Sewing
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

from compas_brep.backend.occ.conversion import brep_to_occ, occ_to_brep


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
# Instance operations
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
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace

    shape = brep_to_occ(brep)

    # Determine the cutting plane from the cutter's first face
    cutter_faces = cutter.faces
    if not cutter_faces:
        return [brep]
    cutting_surface = cutter_faces[0].surface

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

    def _shape_has_faces(brep_result):
        exp = TopExp_Explorer(brep_result._native_brep, TopAbs_EDGE)
        return exp.More()

    results = []
    if _shape_has_faces(result_a):
        results.append(result_a)
    if _shape_has_faces(result_b):
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


def occ_transform(brep, transformation):
    """Transform a Brep by a COMPAS Transformation."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf

    shape = brep_to_occ(brep)
    m = transformation.matrix
    trsf = gp_Trsf()
    trsf.SetValues(
        m[0][0],
        m[0][1],
        m[0][2],
        m[0][3],
        m[1][0],
        m[1][1],
        m[1][2],
        m[1][3],
        m[2][0],
        m[2][1],
        m[2][2],
        m[2][3],
    )
    return occ_to_brep(BRepBuilderAPI_Transform(shape, trsf, True).Shape())


def occ_flip(brep):
    """Reverse the orientation of a Brep."""
    shape = brep_to_occ(brep)
    return occ_to_brep(shape.Reversed())


def occ_copy(brep):
    """Create a deep copy of a Brep."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    shape = brep_to_occ(brep)
    return occ_to_brep(BRepBuilderAPI_Copy(shape).Shape())


def occ_rebuild(brep):
    """Rebuild the native OCC shape from canonical Python topology data.

    Sets ``brep._native_brep`` so subsequent operations and tessellation work.
    Does nothing if the native shape is already present.
    """
    brep_to_occ(brep)
