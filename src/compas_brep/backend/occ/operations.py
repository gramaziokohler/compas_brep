"""OCC boolean and geometric operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Polyline
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
from OCP.gp import gp_Dir
from OCP.gp import gp_GTrsf
from OCP.gp import gp_Pln
from OCP.gp import gp_Pnt
from OCP.gp import gp_Trsf
from OCP.ShapeFix import ShapeFix_Shape
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopAbs import TopAbs_IN
from OCP.TopAbs import TopAbs_ON
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from compas_brep.curves import edge_curve_from_data
from compas_brep.edge import BrepEdge
from compas_brep.errors import BrepError
from compas_brep.exchange import LOOP_OUTER
from compas_brep.exchange import document_version
from compas_brep.exchange import face_loops_from_data
from compas_brep.exchange import trim_pcurve_from_data
from compas_brep.face import BrepFace
from compas_brep.loop import BrepLoop
from compas_brep.surfaces import surface_from_data
from compas_brep.trim import BrepTrim
from compas_brep.vertex import BrepVertex

from .conversion import brep_to_occ
from .conversion import occ_to_brep

if TYPE_CHECKING:
    from compas.geometry import Transformation

    from compas_brep.brep import Brep

# =============================================================================
# Boolean operations
# =============================================================================


def boolean_difference(brep_a: Brep, brep_b: Brep) -> Brep:
    """Boolean subtraction: A - B."""
    shape_a = brep_to_occ(brep_a)
    shape_b = brep_to_occ(brep_b)
    op = BRepAlgoAPI_Cut(shape_a, shape_b)
    return occ_to_brep(op.Shape())


def boolean_union(brep_a: Brep, brep_b: Brep) -> Brep:
    """Boolean union: A + B."""
    shape_a = brep_to_occ(brep_a)
    shape_b = brep_to_occ(brep_b)
    op = BRepAlgoAPI_Fuse(shape_a, shape_b)
    return occ_to_brep(op.Shape())


def boolean_intersection(brep_a: Brep, brep_b: Brep) -> Brep:
    """Boolean intersection: A & B."""
    shape_a = brep_to_occ(brep_a)
    shape_b = brep_to_occ(brep_b)
    op = BRepAlgoAPI_Common(shape_a, shape_b)
    return occ_to_brep(op.Shape())


# =============================================================================
# Instance operations
# =============================================================================


def occ_trimmed(brep: Brep, plane: Plane) -> Brep:
    """OCC implementation of brep.trimmed(plane)."""

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


def occ_split(brep: Brep, cutter: Brep) -> list[Brep]:
    """OCC implementation of brep.split(cutter_brep).

    Splits a solid by a cutter Brep.  When the cutter is a planar face
    (open surface), the split is performed via two half-space cuts so that
    both sides of the cutting plane are returned.
    """

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


def occ_slice(brep: Brep, plane: Plane) -> list[Polyline]:
    """OCC implementation of brep.slice(plane) — returns intersection polylines."""

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
    edge_exp = TopExp_Explorer(result_shape, TopAbs_EDGE)
    while edge_exp.More():
        edge = TopoDS.Edge_s(edge_exp.Current())
        adaptor = BRepAdaptor_Curve(edge)
        t0, t1 = adaptor.FirstParameter(), adaptor.LastParameter()
        n_pts = 32
        pts = []
        for i in range(n_pts + 1):
            t = t0 + (t1 - t0) * i / n_pts
            p = adaptor.Value(t)
            pts.append(Point(p.X(), p.Y(), p.Z()))
        polylines.append(Polyline(pts))
        edge_exp.Next()
    return polylines


def occ_fillet(brep: Brep, radius: float, edges: list[int] | None = None) -> Brep:
    """Fillet edges of a Brep. If edges is None, fillet all edges."""

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


def occ_offset(brep: Brep, distance: float) -> Brep:
    """Offset a Brep by a distance."""

    shape = brep_to_occ(brep)
    offset = BRepOffsetAPI_MakeOffsetShape()
    offset.PerformBySimple(shape, distance)
    return occ_to_brep(offset.Shape())


def occ_contains(brep: Brep, point: Point) -> bool:
    """Check if a point is contained inside a solid Brep."""

    shape = brep_to_occ(brep)
    classifier = BRepClass3d_SolidClassifier(shape, gp_Pnt(point.x, point.y, point.z), 1e-6)
    state = classifier.State()
    return state == TopAbs_IN or state == TopAbs_ON


def occ_cap_planar_holes(brep: Brep) -> Brep:
    """Cap planar holes in a Brep."""

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


def occ_overlap(brep_a: Brep, brep_b: Brep, deflection: float | None = None, tolerance: float = 0.0) -> Brep:
    """Compute the overlap between two Breps, returning the common shape."""
    shape_a = brep_to_occ(brep_a)
    shape_b = brep_to_occ(brep_b)
    common = BRepAlgoAPI_Common(shape_a, shape_b)
    result = occ_to_brep(common.Shape())
    return result


def occ_fix(brep: Brep) -> Brep:
    """Fix a Brep shape using ShapeFix."""

    shape = brep_to_occ(brep)
    fixer = ShapeFix_Shape(shape)
    fixer.Perform()
    return occ_to_brep(fixer.Shape())


def occ_heal(brep: Brep) -> Brep:
    """Heal a Brep shape (fix + sew)."""

    shape = brep_to_occ(brep)
    fixer = ShapeFix_Shape(shape)
    fixer.Perform()
    fixed = fixer.Shape()

    sewing = BRepBuilderAPI_Sewing()
    sewing.Add(fixed)
    sewing.Perform()
    return occ_to_brep(sewing.SewedShape())


def occ_sew(brep: Brep) -> Brep:
    """Sew a Brep shape."""
    shape = brep_to_occ(brep)
    sewing = BRepBuilderAPI_Sewing()
    sewing.Add(shape)
    sewing.Perform()
    return occ_to_brep(sewing.SewedShape())


def occ_make_solid(brep: Brep) -> Brep:
    """Convert a shell Brep to a solid."""

    shape = brep_to_occ(brep)
    solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(shape))
    return occ_to_brep(solid.Shape())


def _is_similarity_transform(m: list[list[float]], tol: float = 1e-6) -> bool:
    """Return True if the linear part of a transform matrix is a pure rotation + uniform scale.

    gp_Trsf can only represent rigid motion plus a single uniform scale factor: it silently
    collapses anisotropic scale or shear into an averaged uniform factor instead of raising.
    Detect that case here so callers can route through gp_GTrsf instead.
    """
    cols = [[m[row][col] for row in range(3)] for col in range(3)]
    lengths_sq = [sum(v * v for v in col) for col in cols]
    k2 = lengths_sq[0]
    if any(abs(length_sq - k2) > tol * max(1.0, k2) for length_sq in lengths_sq):
        return False
    for i in range(3):
        for j in range(i + 1, 3):
            dot = sum(cols[i][k] * cols[j][k] for k in range(3))
            if abs(dot) > tol * max(1.0, k2):
                return False
    return True


def occ_transform(brep: Brep, transformation: Transformation) -> Brep:
    """Transform a Brep by a COMPAS Transformation."""

    shape = brep_to_occ(brep)
    m = transformation.matrix

    if _is_similarity_transform(m):
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

    # Anisotropic scale or shear: gp_Trsf can't represent this, use the general affine transform.
    gtrsf = gp_GTrsf()
    for i in range(3):
        for j in range(4):
            gtrsf.SetValue(i + 1, j + 1, m[i][j])
    return occ_to_brep(BRepBuilderAPI_GTransform(shape, gtrsf, True).Shape())


def occ_flip(brep: Brep) -> Brep:
    """Reverse the orientation of a Brep."""
    shape = brep_to_occ(brep)
    return occ_to_brep(shape.Reversed())


def occ_copy(brep: Brep) -> Brep:
    """Create a deep copy of a Brep."""

    shape = brep_to_occ(brep)
    return occ_to_brep(BRepBuilderAPI_Copy(shape).Shape())


def occ_rebuild(brep: Brep, data: dict) -> None:
    """Rebuild native OCC shape from a STEP-inspired JSON data dict.

    Constructs Python topology from the data, then calls brep_to_occ to build
    the native OCC shape, which is cached on brep._native_brep.
    """

    vertices = [BrepVertex(Point(*xyz)) for xyz in data["vertices"]]

    edges = []
    for ed in data["edges"]:
        start = vertices[ed["start"]]
        end = vertices[ed["end"]]
        curve, domain = edge_curve_from_data(ed["curve"])
        edges.append(BrepEdge(start, end, curve=curve, domain=domain))

    version = document_version(data)

    all_loops = []
    faces = []
    for fd in data["faces"]:
        surface = surface_from_data(fd["surface"])

        outer_loop = None
        inner_loops = []
        for role, loop_data in face_loops_from_data(fd, version):
            trims = []
            for td in loop_data:
                edge_id = td["edge"]
                if edge_id == -1:
                    # Singular trim (a Rhino writer emits these at e.g. a sphere's
                    # pole). It contributes no edge to the wire, and OCC derives its
                    # own degenerate edges when building the face — so drop it here
                    # rather than let ``edges[-1]`` silently bind the last edge.
                    continue
                trims.append(
                    BrepTrim(
                        edge=edges[edge_id],
                        is_reversed=td.get("is_reversed", False),
                        curve_2d=trim_pcurve_from_data(td, version),
                    )
                )
            loop = BrepLoop(trims=trims)
            all_loops.append(loop)
            if role == LOOP_OUTER:
                if outer_loop is not None:
                    raise BrepError("Face has more than one outer loop")
                outer_loop = loop
            else:
                inner_loops.append(loop)

        if outer_loop is None:
            raise BrepError("Face has no outer loop")

        face = BrepFace(
            outer_loop,
            surface=surface,
            is_reversed=fd.get("is_reversed", False),
        )
        for inner_loop in inner_loops:
            face.add_loop(inner_loop)
        faces.append(face)

    brep._vertices = vertices
    brep._edges = edges
    brep._loops = all_loops
    brep._faces = faces
    brep._topology_loaded = True
    brep_to_occ(brep)

    # Attempt to promote a closed shell to a solid so that boolean operations
    # and solid queries work on the reconstructed shape.

    shape = brep._native_brep
    if shape.ShapeType() == TopAbs_SHELL:
        try:
            solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(shape))
            if solid.IsDone():
                brep._native_brep = solid.Shape()
        except Exception:
            pass
