"""Tests for Rhino native-handle topology sub-object wrappers (issue 05)."""

import pytest
from compas.geometry import Plane
from compas.geometry import Point

from compas_brep import Brep
from compas_brep.backend import RhinoBrepEdge
from compas_brep.backend import RhinoBrepFace
from compas_brep.backend import RhinoBrepLoop
from compas_brep.backend import RhinoBrepTrim
from compas_brep.backend import RhinoBrepVertex
from compas_brep.curves import NurbsCurve
from compas_brep.surfaces import NurbsSurface

pytestmark = pytest.mark.rhino


@pytest.fixture
def box_brep():
    from compas.geometry import Box

    return Brep.from_box(Box(1.0, 1.0, 1.0))


@pytest.fixture
def cylinder_brep():
    from compas.geometry import Cylinder

    return Brep.from_cylinder(Cylinder(0.5, 2.0))


# =============================================================================
# 1. Sub-objects are Rhino wrapper instances
# =============================================================================


def test_sub_object_types_vertices_are_rhino_wrappers(box_brep):
    for v in box_brep.vertices:
        assert isinstance(v, RhinoBrepVertex)


def test_sub_object_types_edges_are_rhino_wrappers(box_brep):
    for e in box_brep.edges:
        assert isinstance(e, RhinoBrepEdge)


def test_sub_object_types_faces_are_rhino_wrappers(box_brep):
    for f in box_brep.faces:
        assert isinstance(f, RhinoBrepFace)


def test_sub_object_types_loops_are_rhino_wrappers(box_brep):
    for loop in box_brep.loops:
        assert isinstance(loop, RhinoBrepLoop)


def test_sub_object_types_trims_are_rhino_wrappers(box_brep):
    for trim in box_brep.trims:
        assert isinstance(trim, RhinoBrepTrim)


# =============================================================================
# 2. Native handle is accessible and not a COMPAS type
# =============================================================================


def test_native_handles_vertex_native_is_not_compas(box_brep):
    v = box_brep.vertices[0]
    native = v.native_vertex
    assert native is not v
    assert not isinstance(native, Point)


def test_native_handles_edge_native_is_not_compas(box_brep):
    e = box_brep.edges[0]
    native = e.native_edge
    assert native is not e
    assert not isinstance(native, RhinoBrepEdge)


def test_native_handles_face_native_is_not_compas(box_brep):
    f = box_brep.faces[0]
    native = f.native_face
    assert native is not f
    assert not isinstance(native, RhinoBrepFace)


def test_native_handles_loop_native_is_not_compas(box_brep):
    loop = box_brep.loops[0]
    native = loop.native_loop
    assert native is not loop
    assert not isinstance(native, RhinoBrepLoop)


def test_native_handles_trim_native_is_not_compas(box_brep):
    trim = box_brep.trims[0]
    native = trim.native_trim
    assert native is not trim
    assert not isinstance(native, RhinoBrepTrim)


# =============================================================================
# 3. Property values are COMPAS types
# =============================================================================


def test_property_types_vertex_point_is_point(box_brep):
    v = box_brep.vertices[0]
    assert isinstance(v.point, Point)


def test_property_types_edge_curve_is_compas_type(box_brep):
    from compas.geometry import Line

    for e in box_brep.edges:
        assert isinstance(e.curve, (Line, NurbsCurve))


def test_property_types_face_surface_is_compas_type(box_brep):
    for f in box_brep.faces:
        assert isinstance(f.surface, (Plane, NurbsSurface))


def test_property_types_face_surface_nurbs_on_cylinder(cylinder_brep):
    surfaces = [f.surface for f in cylinder_brep.faces]
    nurbs_surfaces = [s for s in surfaces if isinstance(s, NurbsSurface)]
    assert len(nurbs_surfaces) >= 1


def test_property_types_trim_curve_2d_is_nurbs_or_none(cylinder_brep):
    for trim in cylinder_brep.trims:
        c = trim.curve_2d
        assert c is None or isinstance(c, NurbsCurve)


# =============================================================================
# 4. Property caching (identity check)
# =============================================================================


def test_property_caching_vertex_point_cached(box_brep):
    v = box_brep.vertices[0]
    p1 = v.point
    p2 = v.point
    assert p1 is p2


def test_property_caching_edge_curve_cached(box_brep):
    e = box_brep.edges[0]
    c1 = e.curve
    c2 = e.curve
    assert c1 is c2


def test_property_caching_face_surface_cached(box_brep):
    f = box_brep.faces[0]
    s1 = f.surface
    s2 = f.surface
    assert s1 is s2


def test_property_caching_trim_curve_2d_cached(cylinder_brep):
    nurbs_face = next(f for f in cylinder_brep.faces if f.is_nurbs)
    trim = nurbs_face.outer_loop.trims[0]
    c1 = trim.curve_2d
    c2 = trim.curve_2d
    assert c1 is c2


# =============================================================================
# 5. Topology counts
# =============================================================================


def test_topology_preservation_box_vertex_count(box_brep):
    assert len(box_brep.vertices) == 8


def test_topology_preservation_box_edge_count(box_brep):
    assert len(box_brep.edges) == 12


def test_topology_preservation_box_face_count(box_brep):
    assert len(box_brep.faces) == 6


def test_topology_preservation_face_is_planar_on_box(box_brep):
    for f in box_brep.faces:
        assert f.is_planar
