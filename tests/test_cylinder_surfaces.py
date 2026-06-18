"""Tests for cylinder surface extraction, codec, and round-trip (issue 02)."""

import json
import math

import pytest
from compas.geometry import CylindricalSurface
from compas.geometry import Cylinder
from compas.geometry import Frame
from compas.tolerance import TOL

from compas_brep import Brep

pytestmark = pytest.mark.occ

RADIUS = 0.5
HEIGHT = 2.0


@pytest.fixture
def cylinder_brep():
    return Brep.from_cylinder(Cylinder(RADIUS, HEIGHT))


@pytest.fixture
def cylinder_face(cylinder_brep):
    return next(f for f in cylinder_brep.faces if isinstance(f.surface, CylindricalSurface))


# =============================================================================
# 1. CylindricalSurface extraction
# =============================================================================


class TestCylindricalSurfaceExtraction:
    def test_cylinder_face_returns_cylindrical_surface(self, cylinder_face):
        assert isinstance(cylinder_face.surface, CylindricalSurface)

    def test_cylinder_radius_correct(self, cylinder_face):
        assert abs(cylinder_face.surface.radius - RADIUS) <= TOL.absolute

    def test_cylinder_frame_is_frame(self, cylinder_face):
        assert isinstance(cylinder_face.surface.frame, Frame)

    def test_cylinder_frame_origin_near_center(self, cylinder_face):
        origin = cylinder_face.surface.frame.point
        assert abs(origin.x) < TOL.absolute
        assert abs(origin.y) < TOL.absolute

    def test_cylinder_point_at_geometric_accuracy(self, cylinder_face):
        """COMPAS point_at agrees with OCC adaptor at equivalent parameters."""
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        occ_face = cylinder_face.native_face
        adaptor = BRepAdaptor_Surface(occ_face)
        surface = cylinder_face.surface

        # Sample 4 points at known OCC angles/heights and compare with COMPAS
        # OCC: u ∈ [0, 2π] (angle), v ∈ [0, height]
        # COMPAS: u ∈ [0, 1] (u_compas * 2π = angle), v = actual z
        test_params = [
            (0.0, 0.0),
            (math.pi / 2, 0.5),
            (math.pi, 1.0),
            (3 * math.pi / 2, 1.5),
        ]
        for u_occ, v_occ in test_params:
            occ_pt = adaptor.Value(u_occ, v_occ)
            compas_pt = surface.point_at(u_occ / (2 * math.pi), v_occ)
            dx = occ_pt.X() - compas_pt.x
            dy = occ_pt.Y() - compas_pt.y
            dz = occ_pt.Z() - compas_pt.z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            assert dist <= 1e-6, f"OCC vs COMPAS mismatch at u={u_occ:.3f}, v={v_occ:.3f}: dist={dist}"


# =============================================================================
# 2. BrepFace API: surface_type, is_cylinder, __repr__
# =============================================================================


class TestBrepFaceCylinderAPI:
    def test_surface_type_cylinder(self, cylinder_face):
        assert cylinder_face.surface_type == "cylinder"

    def test_is_cylinder_true(self, cylinder_face):
        assert cylinder_face.is_cylinder is True

    def test_is_nurbs_false_for_cylinder(self, cylinder_face):
        assert cylinder_face.is_nurbs is False

    def test_is_planar_false_for_cylinder(self, cylinder_face):
        assert cylinder_face.is_planar is False

    def test_repr_reports_cylinder(self, cylinder_face):
        assert "cylinder" in repr(cylinder_face)

    def test_planar_face_surface_type(self, cylinder_brep):
        planar_face = next(f for f in cylinder_brep.faces if f.is_planar)
        assert planar_face.surface_type == "plane"
        assert planar_face.is_cylinder is False


# =============================================================================
# 3. JSON round-trip
# =============================================================================


class TestCylinderRoundTrip:
    def test_round_trip_preserves_cylinder_type(self, cylinder_brep):
        data = cylinder_brep.__data__
        surface_types = [f["surface"]["type"] for f in data["faces"]]
        assert "cylinder" in surface_types

    def test_round_trip_face_count(self, cylinder_brep):
        data = cylinder_brep.__data__
        restored = Brep.__from_data__(data)
        assert len(restored.faces) == len(cylinder_brep.faces)

    def test_round_trip_volume(self, cylinder_brep):
        data = cylinder_brep.__data__
        restored = Brep.__from_data__(data)
        expected = math.pi * RADIUS**2 * HEIGHT
        assert abs(restored.volume - expected) < 0.01

    def test_json_round_trip(self, cylinder_brep):
        data = cylinder_brep.__data__
        restored = Brep.__from_data__(json.loads(json.dumps(data)))
        assert len(restored.faces) == len(cylinder_brep.faces)
        expected = math.pi * RADIUS**2 * HEIGHT
        assert abs(restored.volume - expected) < 0.01

    def test_restored_face_is_cylindrical_surface(self, cylinder_brep):
        data = cylinder_brep.__data__
        restored = Brep.__from_data__(data)
        cyl_faces = [f for f in restored.faces if isinstance(f.surface, CylindricalSurface)]
        assert len(cyl_faces) >= 1

    def test_restored_viewmesh_non_empty(self, cylinder_brep):
        data = cylinder_brep.__data__
        restored = Brep.__from_data__(data)
        mesh = restored.to_viewmesh()
        assert mesh.number_of_vertices() > 0
        assert mesh.number_of_faces() > 0


# =============================================================================
# 4. Analytic surface tessellation (no viewer required)
# =============================================================================


class TestAnalyticSurfaceTessellation:
    def test_tessellate_cylindrical_surface(self, cylinder_face):
        """CylindricalSurface tessellates to a non-empty mesh via space_u/space_v/point_at."""
        from compas.datastructures import Mesh

        surface = cylinder_face.surface
        u_params = list(surface.space_u(16))
        v_params = list(surface.space_v(8))

        vertices = []
        for u in u_params:
            for v in v_params:
                p = surface.point_at(u, v)
                vertices.append([p.x, p.y, p.z])

        faces = []
        nv = len(v_params)
        for i in range(len(u_params) - 1):
            for j in range(len(v_params) - 1):
                v0 = i * nv + j
                v1 = i * nv + (j + 1)
                v2 = (i + 1) * nv + (j + 1)
                v3 = (i + 1) * nv + j
                faces.append([v0, v1, v2])
                faces.append([v0, v2, v3])

        mesh = Mesh.from_vertices_and_faces(vertices, faces)
        assert mesh.number_of_vertices() > 0
        assert mesh.number_of_faces() > 0

    def test_tessellate_parametric_surface_helper(self, cylinder_face):
        """The shared tessellation helper produces a non-empty mesh for CylindricalSurface."""
        from compas_brep.scene.viewer.surfaceobject import _tessellate_parametric_surface

        mesh, boundaries = _tessellate_parametric_surface(cylinder_face.surface, 16, 8)
        assert mesh.number_of_vertices() > 0
        assert mesh.number_of_faces() > 0
        assert len(boundaries) == 4
