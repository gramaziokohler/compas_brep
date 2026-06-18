"""Tests for OCC native-handle topology sub-object wrappers (issue 02)."""

import pytest
from compas.geometry import CylindricalSurface
from compas.geometry import Plane
from compas.geometry import Point

from compas_brep import Brep
from compas_brep.backend import OccBrepEdge
from compas_brep.backend import OccBrepFace
from compas_brep.backend import OccBrepLoop
from compas_brep.backend import OccBrepTrim
from compas_brep.backend import OccBrepVertex
from compas_brep.curves import NurbsCurve
from compas_brep.surfaces import NurbsSurface

pytestmark = pytest.mark.occ


@pytest.fixture
def box_brep():
    from compas.geometry import Box

    return Brep.from_box(Box(1.0, 1.0, 1.0))


@pytest.fixture
def cylinder_brep():
    from compas.geometry import Cylinder

    return Brep.from_cylinder(Cylinder(0.5, 2.0))


@pytest.fixture
def sphere_brep():
    from compas.geometry import Sphere

    return Brep.from_sphere(Sphere(1.0))


# =============================================================================
# 1. Sub-objects are OCC wrapper instances
# =============================================================================


class TestSubObjectTypes:
    def test_vertices_are_occ_wrappers(self, box_brep):
        for v in box_brep.vertices:
            assert isinstance(v, OccBrepVertex)

    def test_edges_are_occ_wrappers(self, box_brep):
        for e in box_brep.edges:
            assert isinstance(e, OccBrepEdge)

    def test_faces_are_occ_wrappers(self, box_brep):
        for f in box_brep.faces:
            assert isinstance(f, OccBrepFace)

    def test_loops_are_occ_wrappers(self, box_brep):
        for loop in box_brep.loops:
            assert isinstance(loop, OccBrepLoop)

    def test_trims_are_occ_wrappers(self, box_brep):
        for trim in box_brep.trims:
            assert isinstance(trim, OccBrepTrim)


# =============================================================================
# 2. Native handle is accessible and not a COMPAS type
# =============================================================================


class TestNativeHandles:
    def test_vertex_native_is_not_compas(self, box_brep):
        v = box_brep.vertices[0]
        native = v.native_vertex
        assert native is not v  # not self-referential like the base class
        assert not isinstance(native, Point)

    def test_edge_native_is_not_compas(self, box_brep):
        e = box_brep.edges[0]
        native = e.native_edge
        assert native is not e
        assert not isinstance(native, OccBrepEdge)

    def test_face_native_is_not_compas(self, box_brep):
        f = box_brep.faces[0]
        native = f.native_face
        assert native is not f
        assert not isinstance(native, OccBrepFace)

    def test_loop_native_is_not_compas(self, box_brep):
        loop = box_brep.loops[0]
        native = loop.native_loop
        assert native is not loop
        assert not isinstance(native, OccBrepLoop)

    def test_trim_native_is_not_compas(self, box_brep):
        trim = box_brep.trims[0]
        native = trim.native_trim
        assert native is not trim
        assert not isinstance(native, OccBrepTrim)


# =============================================================================
# 3. Property values are COMPAS types
# =============================================================================


class TestPropertyTypes:
    def test_vertex_point_is_point(self, box_brep):
        v = box_brep.vertices[0]
        assert isinstance(v.point, Point)

    def test_edge_curve_is_compas_type(self, box_brep):
        from compas.geometry import Line

        for e in box_brep.edges:
            assert isinstance(e.curve, (Line, NurbsCurve))

    def test_face_surface_planar_returns_plane(self, box_brep):
        for f in box_brep.faces:
            assert isinstance(f.surface, (Plane, NurbsSurface))

    def test_face_surface_nurbs_returns_nurbs(self, sphere_brep):
        surfaces = [f.surface for f in sphere_brep.faces]
        nurbs_surfaces = [s for s in surfaces if isinstance(s, NurbsSurface)]
        assert len(nurbs_surfaces) >= 1

    def test_face_surface_cylinder_returns_cylindrical(self, cylinder_brep):
        surfaces = [f.surface for f in cylinder_brep.faces]
        cyl_surfaces = [s for s in surfaces if isinstance(s, CylindricalSurface)]
        assert len(cyl_surfaces) >= 1

    def test_trim_curve_2d_is_nurbs_or_none(self, cylinder_brep):
        for trim in cylinder_brep.trims:
            c = trim.curve_2d
            assert c is None or isinstance(c, NurbsCurve)


# =============================================================================
# 4. Property caching (identity check)
# =============================================================================


class TestPropertyCaching:
    def test_vertex_point_cached(self, box_brep):
        v = box_brep.vertices[0]
        p1 = v.point
        p2 = v.point
        assert p1 is p2

    def test_edge_curve_cached(self, box_brep):
        e = box_brep.edges[0]
        c1 = e.curve
        c2 = e.curve
        assert c1 is c2

    def test_face_surface_cached(self, box_brep):
        f = box_brep.faces[0]
        s1 = f.surface
        s2 = f.surface
        assert s1 is s2

    def test_trim_curve_2d_cached(self, sphere_brep):
        # Use a trim from a NURBS face where pcurve is available
        nurbs_face = next(f for f in sphere_brep.faces if f.is_nurbs)
        trim = nurbs_face.outer_loop.trims[0]
        c1 = trim.curve_2d
        c2 = trim.curve_2d
        assert c1 is c2


# =============================================================================
# 5. Existing topology tests still pass
# =============================================================================


class TestTopologyPreservation:
    def test_box_vertex_count(self, box_brep):
        assert len(box_brep.vertices) == 8

    def test_box_edge_count(self, box_brep):
        assert len(box_brep.edges) == 12

    def test_box_face_count(self, box_brep):
        assert len(box_brep.faces) == 6

    def test_vertex_neighbors_count(self, box_brep):
        v = box_brep.vertices[0]
        assert len(box_brep.vertex_neighbors(v)) == 3

    def test_edge_faces_count(self, box_brep):
        e = box_brep.edges[0]
        assert 1 <= len(box_brep.edge_faces(e)) <= 2

    def test_face_is_planar_on_box(self, box_brep):
        for f in box_brep.faces:
            assert f.is_planar

    def test_edge_first_last_vertex_are_brep_vertices(self, box_brep):
        e = box_brep.edges[0]
        assert e.first_vertex in box_brep.vertices
        assert e.last_vertex in box_brep.vertices
