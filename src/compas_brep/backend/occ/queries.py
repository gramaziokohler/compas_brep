"""OCC property queries and tessellation."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from compas.datastructures import Mesh
from compas.geometry import Box
from compas.geometry import Frame
from compas.geometry import Point
from compas.geometry import Polyline
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.gp import gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_COMPSOLID
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopAbs import TopAbs_FACE
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

from .conversion import brep_to_occ

if TYPE_CHECKING:
    from compas_brep.brep import Brep


def occ_area(brep: Brep) -> float:
    """Compute the surface area of a Brep."""
    shape = brep_to_occ(brep)
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.Mass()


def occ_volume(brep: Brep) -> float:
    """Compute the volume of a Brep."""
    shape = brep_to_occ(brep)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def occ_centroid(brep: Brep) -> Point:
    """Compute the centroid of a Brep."""
    shape = brep_to_occ(brep)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    c = props.CentreOfMass()
    return Point(c.X(), c.Y(), c.Z())


def occ_aabb(brep: Brep) -> Box:
    """Compute the axis-aligned bounding box of a Brep."""
    shape = brep_to_occ(brep)
    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    cz = (zmin + zmax) / 2
    dx = max(xmax - xmin, 1e-10)
    dy = max(ymax - ymin, 1e-10)
    dz = max(zmax - zmin, 1e-10)
    return Box(dx, dy, dz, Frame(Point(cx, cy, cz), [1, 0, 0], [0, 1, 0]))


def occ_is_solid(brep: Brep) -> bool:
    """Check if the Brep is a solid."""
    shape = brep_to_occ(brep)
    t = shape.ShapeType()
    if t in (TopAbs_SOLID, TopAbs_COMPSOLID):
        return True
    solid_exp = TopExp_Explorer(shape, TopAbs_SOLID)
    return solid_exp.More()


def occ_is_valid(brep: Brep) -> bool:
    """Check if the Brep is geometrically valid."""
    shape = brep_to_occ(brep)
    return BRepCheck_Analyzer(shape).IsValid()


def occ_tessellate(brep: Brep, linear_deflection: float = 0.1, n: int = 16, n_curves: int = 64) -> tuple[Mesh, list[Polyline]]:
    """Tessellate a Brep into a mesh and edge polylines using OCC.

    Parameters
    ----------
    brep
        The Brep to tessellate.
    linear_deflection
        Linear deflection for BRepMesh.
    n
        Angular resolution parameter.
    n_curves
        Number of segments per curved edge for boundary polylines.
    """
    shape = brep_to_occ(brep)
    ang_def = math.pi / max(n * 4, 16)
    BRepMesh_IncrementalMesh(shape, linear_deflection, True, ang_def).Perform()

    all_verts = []
    all_faces = []
    offset = 0

    face_exp = TopExp_Explorer(shape, TopAbs_FACE)
    while face_exp.More():
        occ_face = TopoDS.Face_s(face_exp.Current())
        is_rev = occ_face.Orientation() == TopAbs_REVERSED
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(occ_face, loc)
        if tri is not None and tri.NbTriangles() > 0:
            trsf = loc.Transformation() if not loc.IsIdentity() else None
            for i in range(1, tri.NbNodes() + 1):
                node = tri.Node(i)
                if trsf is not None:
                    pnt = gp_Pnt(node.X(), node.Y(), node.Z())
                    pnt.Transform(trsf)
                    all_verts.append([pnt.X(), pnt.Y(), pnt.Z()])
                else:
                    all_verts.append([node.X(), node.Y(), node.Z()])
            for i in range(1, tri.NbTriangles() + 1):
                n1, n2, n3 = tri.Triangle(i).Get()
                if is_rev:
                    all_faces.append([offset + n1 - 1, offset + n3 - 1, offset + n2 - 1])
                else:
                    all_faces.append([offset + n1 - 1, offset + n2 - 1, offset + n3 - 1])
            offset += tri.NbNodes()
        face_exp.Next()

    mesh = Mesh.from_vertices_and_faces(all_verts, all_faces) if all_verts else Mesh()

    boundaries = []
    edge_exp = TopExp_Explorer(shape, TopAbs_EDGE)
    while edge_exp.More():
        occ_edge = TopoDS.Edge_s(edge_exp.Current())
        try:
            adaptor = BRepAdaptor_Curve(occ_edge)
            t0 = adaptor.FirstParameter()
            t1 = adaptor.LastParameter()
            pts = []
            for i in range(n_curves + 1):
                t = t0 + (t1 - t0) * i / n_curves
                p = adaptor.Value(t)
                pts.append(Point(p.X(), p.Y(), p.Z()))
            if len(pts) >= 2:
                boundaries.append(Polyline(pts))
        except Exception:
            pass
        edge_exp.Next()

    return mesh, boundaries
