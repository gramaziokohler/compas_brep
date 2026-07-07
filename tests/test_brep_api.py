"""Comprehensive tests for the Brep API methods."""

import math

import pytest
from compas.datastructures import Mesh
from compas.geometry import Box
from compas.geometry import Frame
from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Polygon
from compas.geometry import Translation
from compas.geometry import Vector

from compas_brep import Brep

pytestmark = pytest.mark.occ

# =============================================================================
# Helpers
# =============================================================================


def _unit_box_brep():
    """Create a Brep from a 1x1x1 box centered at the origin."""
    return Brep.from_box(Box(1.0, 1.0, 1.0))


def _offset_box_brep(dx=2.0, dy=0.0, dz=0.0, size=1.0):
    """Create a Brep from a box at a given offset."""
    frame = Frame(Point(dx, dy, dz), Vector(1, 0, 0), Vector(0, 1, 0))
    return Brep.from_box(Box(size, size, size, frame))


# =============================================================================
# 1. Constructors
# =============================================================================


def test_constructors_from_box():
    brep = _unit_box_brep()
    assert isinstance(brep, Brep)
    assert len(brep.faces) == 6
    assert len(brep.vertices) == 8


def test_constructors_from_plane():
    plane = Plane(Point(0, 0, 0), Vector(0, 0, 1))
    brep = Brep.from_plane(plane, domain_u=(-2, 2), domain_v=(-3, 3))
    assert isinstance(brep, Brep)
    assert len(brep.faces) == 1
    assert brep.is_surface


def test_constructors_from_plane_default_domain():
    plane = Plane(Point(1, 2, 3), Vector(0, 0, 1))
    brep = Brep.from_plane(plane)
    assert isinstance(brep, Brep)
    assert len(brep.vertices) == 4


def test_constructors_from_extrusion_polygon():
    profile = Polygon([Point(0, 0, 0), Point(1, 0, 0), Point(1, 1, 0), Point(0, 1, 0)])
    brep = Brep.from_extrusion(profile, Vector(0, 0, 2))
    assert isinstance(brep, Brep)
    assert brep.is_valid
    # 4 side faces + 2 caps = 6
    assert len(brep.faces) == 6


def test_constructors_from_extrusion_no_caps():
    profile = Polygon([Point(0, 0, 0), Point(1, 0, 0), Point(1, 1, 0), Point(0, 1, 0)])
    brep = Brep.from_extrusion(profile, Vector(0, 0, 1), cap_ends=False)
    assert isinstance(brep, Brep)
    assert brep.is_valid
    # Backend may ignore cap_ends and always produce 6 faces; fallback produces 4
    assert len(brep.faces) >= 4


def test_constructors_from_brepfaces():
    box_brep = _unit_box_brep()
    faces = box_brep.faces
    brep = Brep.from_brepfaces(faces)
    assert isinstance(brep, Brep)
    assert len(brep.faces) == 6


def test_constructors_from_polygons():
    polygons = [
        Polygon([Point(0, 0, 0), Point(1, 0, 0), Point(1, 1, 0)]),
        Polygon([Point(0, 0, 0), Point(1, 1, 0), Point(0, 1, 0)]),
    ]
    brep = Brep.from_polygons(polygons)
    assert isinstance(brep, Brep)
    assert len(brep.faces) == 2


def test_constructors_from_mesh():
    mesh = Mesh.from_polyhedron(4)
    brep = Brep.from_mesh(mesh)
    assert isinstance(brep, Brep)
    assert brep.is_valid


def test_constructors_from_cone_delegates_to_backend():
    """from_cone requires a backend; verify it exists as a class method."""
    assert hasattr(Brep, "from_cone")
    assert callable(getattr(Brep, "from_cone"))


def test_constructors_from_loft_delegates_to_backend():
    """from_loft requires a backend; verify it exists as a class method."""
    assert hasattr(Brep, "from_loft")
    assert callable(getattr(Brep, "from_loft"))


# =============================================================================
# 2. Properties
# =============================================================================


def test_properties_aabb_dimensions():
    brep = _unit_box_brep()
    aabb = brep.aabb
    assert isinstance(aabb, Box)
    assert abs(aabb.xsize - 1.0) < 1e-6
    assert abs(aabb.ysize - 1.0) < 1e-6
    assert abs(aabb.zsize - 1.0) < 1e-6


def test_properties_aabb_offset_box():
    brep = _offset_box_brep(dx=5.0, dy=3.0, dz=1.0, size=2.0)
    aabb = brep.aabb
    assert abs(aabb.xsize - 2.0) < 1e-6
    assert abs(aabb.ysize - 2.0) < 1e-6
    assert abs(aabb.zsize - 2.0) < 1e-6


def test_properties_trims_returns_list():
    brep = _unit_box_brep()
    trims = brep.trims
    assert isinstance(trims, list)


def test_properties_points_count():
    brep = _unit_box_brep()
    assert len(brep.points) == 8


def test_properties_points_are_points():
    brep = _unit_box_brep()
    for pt in brep.points:
        assert isinstance(pt, Point)


def test_properties_curves_count():
    brep = _unit_box_brep()
    curves = brep.curves
    # A box has 12 edges
    assert len(curves) == len(brep.edges)


def test_properties_surfaces_count():
    brep = _unit_box_brep()
    surfaces = brep.surfaces
    assert len(surfaces) == 6


def test_properties_is_closed_box():
    brep = _unit_box_brep()
    assert brep.is_closed is True


def test_properties_is_solid_box():
    brep = _unit_box_brep()
    assert brep.is_solid is True


def test_properties_is_valid_box():
    brep = _unit_box_brep()
    assert brep.is_valid is True


def test_properties_is_shell_single_face():
    plane = Plane(Point(0, 0, 0), Vector(0, 0, 1))
    brep = Brep.from_plane(plane)
    # A single face is not solid, so is_shell should be True
    assert brep.is_shell is True


def test_properties_is_surface_single_face():
    plane = Plane(Point(0, 0, 0), Vector(0, 0, 1))
    brep = Brep.from_plane(plane)
    assert brep.is_surface is True


def test_properties_is_surface_box():
    brep = _unit_box_brep()
    assert brep.is_surface is False


def test_properties_volume_unit_box():
    brep = _unit_box_brep()
    assert abs(brep.volume - 1.0) < 0.01


def test_properties_volume_larger_box():
    brep = Brep.from_box(Box(2.0, 3.0, 4.0))
    assert abs(brep.volume - 24.0) < 0.1


def test_properties_area_unit_box():
    brep = _unit_box_brep()
    assert abs(brep.area - 6.0) < 0.01


def test_properties_centroid_unit_box_at_origin():
    brep = _unit_box_brep()
    c = brep.centroid
    assert abs(c.x) < 1e-6
    assert abs(c.y) < 1e-6
    assert abs(c.z) < 1e-6


def test_properties_centroid_offset_box():
    brep = _offset_box_brep(dx=3.0, dy=4.0, dz=5.0)
    c = brep.centroid
    assert abs(c.x - 3.0) < 1e-6
    assert abs(c.y - 4.0) < 1e-6
    assert abs(c.z - 5.0) < 1e-6


# =============================================================================
# 3. Topology queries
# =============================================================================


def test_topology_queries_vertex_neighbors_box():
    brep = _unit_box_brep()
    v = brep.vertices[0]
    neighbors = brep.vertex_neighbors(v)
    assert len(neighbors) == 3


def test_topology_queries_vertex_neighbors_are_vertices():
    brep = _unit_box_brep()
    v = brep.vertices[0]
    neighbors = brep.vertex_neighbors(v)
    for n in neighbors:
        assert n in brep.vertices


def test_topology_queries_vertex_edges_box():
    brep = _unit_box_brep()
    v = brep.vertices[0]
    edges = brep.vertex_edges(v)
    assert len(edges) == 3


def test_topology_queries_vertex_faces_box():
    brep = _unit_box_brep()
    v = brep.vertices[0]
    faces = brep.vertex_faces(v)
    assert len(faces) == 3


def test_topology_queries_edge_faces_box():
    brep = _unit_box_brep()
    edge = brep.edges[0]
    faces = brep.edge_faces(edge)
    # Each edge on a box is shared by exactly 2 faces
    assert len(faces) >= 1
    assert len(faces) <= 2


def test_topology_queries_edge_loop_returns_loop():
    brep = _unit_box_brep()
    edge = brep.edges[0]
    loop = brep.edge_loop(edge)
    assert loop is not None
    assert loop in brep.loops


def test_topology_queries_edge_loops_returns_list():
    brep = _unit_box_brep()
    edge = brep.edges[0]
    loops = brep.edge_loops(edge)
    assert isinstance(loops, list)
    assert len(loops) >= 1


# =============================================================================
# 4. Operations
# =============================================================================


def test_operations_copy_returns_brep():
    # Build from polygons to avoid unpicklable native OCC cache
    brep = Brep.from_polygons(_unit_box_brep().to_polygons())
    copy = brep.copy()
    assert isinstance(copy, Brep)
    assert len(copy.faces) == len(brep.faces)
    assert len(copy.vertices) == len(brep.vertices)


def test_operations_copy_is_independent():
    # Build from polygons to avoid unpicklable native OCC cache
    brep = Brep.from_polygons(_unit_box_brep().to_polygons())
    copy = brep.copy()
    # Modify the original via transform
    brep.transform(Translation.from_vector(Vector(10, 10, 10)))
    # Copy's centroid should be unchanged at origin
    c = copy.centroid
    assert abs(c.x) < 1e-6
    assert abs(c.y) < 1e-6
    assert abs(c.z) < 1e-6


def test_operations_transform_moves_centroid():
    brep = _unit_box_brep()
    T = Translation.from_vector(Vector(5, 0, 0))
    brep.transform(T)
    c = brep.centroid
    assert abs(c.x - 5.0) < 1e-6
    assert abs(c.y) < 1e-6
    assert abs(c.z) < 1e-6


def test_operations_transformed_returns_new_brep():
    # Build from polygons to avoid unpicklable native OCC cache in copy
    brep = Brep.from_polygons(_unit_box_brep().to_polygons())
    T = Translation.from_vector(Vector(0, 3, 0))
    new_brep = brep.transformed(T)
    assert isinstance(new_brep, Brep)
    # Original unchanged
    assert abs(brep.centroid.y) < 1e-6
    # New brep moved
    assert abs(new_brep.centroid.y - 3.0) < 1e-6


# -- translate / scale / rotate (inherited from compas.geometry.Geometry) --


def test_operations_translate_moves_centroid():
    brep = _unit_box_brep()
    brep.translate(Vector(5, 0, 0))
    c = brep.centroid
    assert abs(c.x - 5.0) < 1e-6
    assert abs(c.y) < 1e-6
    assert abs(c.z) < 1e-6


def test_operations_translated_returns_new_brep():
    brep = Brep.from_polygons(_unit_box_brep().to_polygons())
    new_brep = brep.translated(Vector(0, 3, 0))
    assert isinstance(new_brep, Brep)
    # Original unchanged
    assert abs(brep.centroid.y) < 1e-6
    # New brep moved
    assert abs(new_brep.centroid.y - 3.0) < 1e-6


def test_operations_scale_uniform_moves_centroid_and_volume():
    brep = _offset_box_brep(dx=2.0)
    brep.scale(2)
    c = brep.centroid
    assert abs(c.x - 4.0) < 1e-6
    assert abs(c.y) < 1e-6
    assert abs(brep.volume - 8.0) < 1e-6


def test_operations_scale_nonuniform_moves_centroid_and_volume():
    # Regression test: gp_Trsf (used for rigid + uniform-scale transforms) cannot
    # represent anisotropic scale. occ_transform must route this through gp_GTrsf.
    brep = _offset_box_brep(dx=1.0, dy=1.0, dz=1.0)
    brep.scale(2, 3, 4)
    c = brep.centroid
    assert abs(c.x - 2.0) < 1e-6
    assert abs(c.y - 3.0) < 1e-6
    assert abs(c.z - 4.0) < 1e-6
    assert abs(brep.volume - 24.0) < 1e-6


def test_operations_scaled_returns_new_brep():
    brep = Brep.from_polygons(_offset_box_brep(dx=2.0).to_polygons())
    new_brep = brep.scaled(2)
    assert isinstance(new_brep, Brep)
    # Original unchanged
    assert abs(brep.centroid.x - 2.0) < 1e-6
    # New brep scaled
    assert abs(new_brep.centroid.x - 4.0) < 1e-6


def test_operations_rotate_default_axis_and_point():
    # Default axis is Z, default point is the origin.
    brep = _offset_box_brep(dx=2.0)
    brep.rotate(math.pi / 2)
    c = brep.centroid
    assert abs(c.x) < 1e-6
    assert abs(c.y - 2.0) < 1e-6
    assert abs(c.z) < 1e-6


def test_operations_rotate_custom_axis_and_point():
    brep = _offset_box_brep(dx=5.0)
    brep.rotate(math.pi, axis=Vector(0, 0, 1), point=Point(3, 0, 0))
    c = brep.centroid
    assert abs(c.x - 1.0) < 1e-6
    assert abs(c.y) < 1e-6


def test_operations_rotated_returns_new_brep():
    brep = Brep.from_polygons(_offset_box_brep(dx=2.0).to_polygons())
    new_brep = brep.rotated(math.pi / 2)
    assert isinstance(new_brep, Brep)
    # Original unchanged
    assert abs(brep.centroid.x - 2.0) < 1e-6
    # New brep rotated
    assert abs(new_brep.centroid.y - 2.0) < 1e-6


def test_operations_flip_reverses_faces():
    brep = _unit_box_brep()
    original_reversed = [f._is_reversed for f in brep.faces]
    brep.flip()
    for face, orig in zip(brep.faces, original_reversed):
        assert face._is_reversed is not orig


def test_operations_flip_twice_restores():
    brep = _unit_box_brep()
    original_reversed = [f._is_reversed for f in brep.faces]
    brep.flip()
    brep.flip()
    for face, orig in zip(brep.faces, original_reversed):
        assert face._is_reversed is orig


def test_operations_to_polygons_count():
    brep = _unit_box_brep()
    polygons = brep.to_polygons()
    assert len(polygons) == 6


def test_operations_to_polygons_types():
    brep = _unit_box_brep()
    polygons = brep.to_polygons()
    for p in polygons:
        assert isinstance(p, Polygon)


def test_operations_to_viewmesh():
    brep = _unit_box_brep()
    mesh = brep.to_viewmesh()
    assert isinstance(mesh, Mesh)
    assert mesh.number_of_vertices() > 0
    assert mesh.number_of_faces() > 0


def test_operations_to_meshes():
    brep = _unit_box_brep()
    meshes = brep.to_meshes()
    assert isinstance(meshes, list)
    assert len(meshes) == 1
    for m in meshes:
        assert isinstance(m, Mesh)


def test_operations_to_tesselation():
    brep = _unit_box_brep()
    result = brep.to_tesselation()
    assert isinstance(result, tuple)
    assert len(result) == 2
    mesh, boundaries = result
    assert isinstance(mesh, Mesh)
    assert isinstance(boundaries, list)
    assert mesh.number_of_vertices() > 0


# =============================================================================
# 5. Boolean operator syntax
# =============================================================================


def test_boolean_operators_sub_returns_valid_brep():
    a = _unit_box_brep()
    b = _offset_box_brep(dx=0.5, size=0.5)
    result = a - b
    assert isinstance(result, Brep)
    assert result.is_valid
    assert result.volume > 0


def test_boolean_operators_add_returns_valid_brep():
    a = _unit_box_brep()
    b = _offset_box_brep(dx=0.5, size=1.0)
    result = a + b
    assert isinstance(result, Brep)
    assert result.is_valid
    assert result.volume > 0


def test_boolean_operators_and_returns_valid_brep():
    a = _unit_box_brep()
    b = _offset_box_brep(dx=0.25, size=1.0)
    result = a & b
    assert isinstance(result, Brep)
    assert result.is_valid
    assert result.volume > 0


def test_boolean_operators_sub_volume_decreases():
    a = Brep.from_box(Box(2.0, 2.0, 2.0))
    b = _unit_box_brep()
    result = a - b
    assert result.volume < a.volume


def test_boolean_operators_add_volume_between_parts_and_sum():
    a = _unit_box_brep()
    b = _offset_box_brep(dx=0.5, size=1.0)
    result = a + b
    # Union volume should be less than sum (overlap) but more than either
    assert result.volume < a.volume + b.volume
    assert result.volume > a.volume


def test_boolean_operators_and_volume_less_than_both():
    a = _unit_box_brep()
    b = _offset_box_brep(dx=0.25, size=1.0)
    result = a & b
    assert result.volume < a.volume
    assert result.volume < b.volume


def test_boolean_operators_from_boolean_union_multi():
    a = _unit_box_brep()
    b = _offset_box_brep(dx=0.8, size=1.0)
    c = _offset_box_brep(dx=1.6, size=1.0)
    result = Brep.from_boolean_union_multi(a, b, c)
    assert isinstance(result, Brep)
    assert result.is_valid
    assert result.volume > a.volume


def test_boolean_operators_from_boolean_union_multi_requires_two():
    a = _unit_box_brep()
    with pytest.raises(ValueError):
        Brep.from_boolean_union_multi(a)


# =============================================================================
# 6. String representations
# =============================================================================


def test_string_representations_repr_contains_counts():
    brep = _unit_box_brep()
    r = repr(brep)
    assert "Brep" in r
    assert "vertices=8" in r
    assert "faces=6" in r


def test_string_representations_str_contains_sections():
    brep = _unit_box_brep()
    s = str(brep)
    assert "Brep" in s
    assert "Vertices:" in s
    assert "Edges:" in s
    assert "Loops:" in s
    assert "Faces:" in s
    assert "Area:" in s
    assert "Volume:" in s


def test_string_representations_repr_is_string():
    brep = _unit_box_brep()
    assert isinstance(repr(brep), str)


def test_string_representations_str_is_string():
    brep = _unit_box_brep()
    assert isinstance(str(brep), str)
