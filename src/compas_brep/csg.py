"""BSP-tree based Constructive Solid Geometry engine.

Operates on polygon soup. Each polygon is convex and planar.
Based on the algorithm from "Merging BSP Trees Yields Polyhedral Set Operations"
by Naylor, Amanatides & Thibault (1990), popularized by csg.js.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from compas.geometry import Plane, Point, Vector
from compas.tolerance import TOL

EPSILON = TOL.absolute


@dataclass
class CSGPolygon:
    """A convex polygon with a plane."""

    vertices: list[Point]
    plane: Plane = field(default=None)
    shared: object = None  # arbitrary metadata (e.g. face index)

    def __post_init__(self):
        if self.plane is None:
            self.plane = _plane_from_points(self.vertices)

    def flipped(self) -> CSGPolygon:
        return CSGPolygon(
            vertices=list(reversed(self.vertices)),
            plane=Plane(self.plane.point, self.plane.normal * -1),
            shared=self.shared,
        )


def _plane_from_points(points: list[Point]) -> Plane:
    """Compute plane from polygon vertices using Newell's method."""
    n = len(points)
    nx, ny, nz = 0.0, 0.0, 0.0
    for i in range(n):
        p0 = points[i]
        p1 = points[(i + 1) % n]
        nx += (p0.y - p1.y) * (p0.z + p1.z)
        ny += (p0.z - p1.z) * (p0.x + p1.x)
        nz += (p0.x - p1.x) * (p0.y + p1.y)
    normal = Vector(nx, ny, nz)
    length = normal.length
    if length < EPSILON:
        normal = Vector(0, 0, 1)
    else:
        normal = normal / length
    return Plane(points[0], normal)


# Classification constants
COPLANAR = 0
FRONT = 1
BACK = 2
SPANNING = 3


def _classify_point(plane: Plane, point: Point) -> int:
    """Classify a point relative to a plane."""
    # signed distance = dot(normal, point - plane.point)
    t = (
        plane.normal.x * (point.x - plane.point.x)
        + plane.normal.y * (point.y - plane.point.y)
        + plane.normal.z * (point.z - plane.point.z)
    )
    if t < -EPSILON:
        return BACK
    elif t > EPSILON:
        return FRONT
    return COPLANAR


def _split_polygon(
    plane: Plane,
    polygon: CSGPolygon,
    coplanar_front: list[CSGPolygon],
    coplanar_back: list[CSGPolygon],
    front: list[CSGPolygon],
    back: list[CSGPolygon],
):
    """Split a polygon by a plane, distributing fragments to the appropriate lists."""
    polygon_type = COPLANAR
    types = []
    for v in polygon.vertices:
        t = _classify_point(plane, v)
        polygon_type |= t
        types.append(t)

    if polygon_type == COPLANAR:
        # Check if normals are aligned
        dot = (
            plane.normal.x * polygon.plane.normal.x
            + plane.normal.y * polygon.plane.normal.y
            + plane.normal.z * polygon.plane.normal.z
        )
        if dot > 0:
            coplanar_front.append(polygon)
        else:
            coplanar_back.append(polygon)
    elif polygon_type == FRONT:
        front.append(polygon)
    elif polygon_type == BACK:
        back.append(polygon)
    else:
        # SPANNING - need to split
        f = []
        b = []
        n = len(polygon.vertices)
        for i in range(n):
            j = (i + 1) % n
            ti = types[i]
            tj = types[j]
            vi = polygon.vertices[i]
            vj = polygon.vertices[j]

            if ti != BACK:
                f.append(vi)
            if ti != FRONT:
                b.append(vi)

            if (ti | tj) == SPANNING:
                # Compute intersection point
                t = (
                    plane.normal.x * (plane.point.x - vi.x)
                    + plane.normal.y * (plane.point.y - vi.y)
                    + plane.normal.z * (plane.point.z - vi.z)
                ) / (plane.normal.x * (vj.x - vi.x) + plane.normal.y * (vj.y - vi.y) + plane.normal.z * (vj.z - vi.z))
                v = Point(
                    vi.x + t * (vj.x - vi.x),
                    vi.y + t * (vj.y - vi.y),
                    vi.z + t * (vj.z - vi.z),
                )
                f.append(v)
                b.append(v)

        if len(f) >= 3:
            front.append(CSGPolygon(f, shared=polygon.shared))
        if len(b) >= 3:
            back.append(CSGPolygon(b, shared=polygon.shared))


class BSPNode:
    """A node in a BSP tree."""

    def __init__(self, polygons: list[CSGPolygon] | None = None):
        self.plane: Plane | None = None
        self.front: BSPNode | None = None
        self.back: BSPNode | None = None
        self.polygons: list[CSGPolygon] = []
        if polygons:
            self.build(polygons)

    def clone(self) -> BSPNode:
        """Clone the entire tree iteratively."""
        root_clone = BSPNode()
        # Stack of (source_node, target_node)
        stack = [(self, root_clone)]
        while stack:
            src, tgt = stack.pop()
            if src.plane:
                tgt.plane = Plane(
                    Point(src.plane.point.x, src.plane.point.y, src.plane.point.z),
                    Vector(src.plane.normal.x, src.plane.normal.y, src.plane.normal.z),
                )
            tgt.polygons = [
                CSGPolygon(
                    [Point(v.x, v.y, v.z) for v in p.vertices],
                    Plane(
                        Point(p.plane.point.x, p.plane.point.y, p.plane.point.z),
                        Vector(p.plane.normal.x, p.plane.normal.y, p.plane.normal.z),
                    ),
                    p.shared,
                )
                for p in src.polygons
            ]
            if src.front:
                tgt.front = BSPNode()
                stack.append((src.front, tgt.front))
            if src.back:
                tgt.back = BSPNode()
                stack.append((src.back, tgt.back))
        return root_clone

    def invert(self):
        """Flip all polygons and swap front/back (iterative)."""
        stack = [self]
        while stack:
            node = stack.pop()
            for p in node.polygons:
                p.vertices.reverse()
                p.plane = Plane(p.plane.point, p.plane.normal * -1)
            if node.plane:
                node.plane = Plane(node.plane.point, node.plane.normal * -1)
            node.front, node.back = node.back, node.front
            if node.front:
                stack.append(node.front)
            if node.back:
                stack.append(node.back)

    def clip_polygons(self, polygons: list[CSGPolygon]) -> list[CSGPolygon]:
        """Remove all polygons that are inside this BSP tree (iterative)."""
        # Process iteratively using a stack of (node, polygons_to_classify)
        # Each entry produces front_result and back_result polygons
        # We use a worklist approach: each polygon set flows through the tree
        result: list[CSGPolygon] = []
        # Stack entries: (node, polygons)
        stack = [(self, polygons)]
        while stack:
            node, polys = stack.pop()
            if node.plane is None:
                result.extend(polys)
                continue
            front_polys: list[CSGPolygon] = []
            back_polys: list[CSGPolygon] = []
            for p in polys:
                _split_polygon(node.plane, p, front_polys, back_polys, front_polys, back_polys)
            if node.front:
                stack.append((node.front, front_polys))
            else:
                result.extend(front_polys)
            if node.back:
                stack.append((node.back, back_polys))
            # else: back_polys are discarded (inside the tree)
        return result

    def clip_to(self, bsp: BSPNode):
        """Remove all polygons in this tree that are inside the other BSP tree (iterative)."""
        stack = [self]
        while stack:
            node = stack.pop()
            node.polygons = bsp.clip_polygons(node.polygons)
            if node.front:
                stack.append(node.front)
            if node.back:
                stack.append(node.back)

    def all_polygons(self) -> list[CSGPolygon]:
        """Return all polygons in this tree (iterative)."""
        polygons: list[CSGPolygon] = []
        stack = [self]
        while stack:
            node = stack.pop()
            polygons.extend(node.polygons)
            if node.front:
                stack.append(node.front)
            if node.back:
                stack.append(node.back)
        return polygons

    def build(self, polygons: list[CSGPolygon]):
        """Build BSP tree from polygons (iterative)."""
        if not polygons:
            return
        # Stack entries: (node, polygons_to_add)
        stack = [(self, polygons)]
        while stack:
            node, polys = stack.pop()
            if not polys:
                continue
            if node.plane is None:
                node.plane = Plane(
                    Point(polys[0].plane.point.x, polys[0].plane.point.y, polys[0].plane.point.z),
                    Vector(polys[0].plane.normal.x, polys[0].plane.normal.y, polys[0].plane.normal.z),
                )
            front_polys: list[CSGPolygon] = []
            back_polys: list[CSGPolygon] = []
            for p in polys:
                _split_polygon(node.plane, p, node.polygons, node.polygons, front_polys, back_polys)
            if front_polys:
                if node.front is None:
                    node.front = BSPNode()
                stack.append((node.front, front_polys))
            if back_polys:
                if node.back is None:
                    node.back = BSPNode()
                stack.append((node.back, back_polys))


def csg_union(a_polygons: list[CSGPolygon], b_polygons: list[CSGPolygon]) -> list[CSGPolygon]:
    """Boolean union of two polygon soups."""
    a = BSPNode(a_polygons)
    b = BSPNode(b_polygons)
    a.clip_to(b)
    b.clip_to(a)
    b.invert()
    b.clip_to(a)
    b.invert()
    a.build(b.all_polygons())
    return a.all_polygons()


def csg_subtract(a_polygons: list[CSGPolygon], b_polygons: list[CSGPolygon]) -> list[CSGPolygon]:
    """Boolean subtraction: A - B."""
    a = BSPNode(a_polygons)
    b = BSPNode(b_polygons)
    a.invert()
    a.clip_to(b)
    b.clip_to(a)
    b.invert()
    b.clip_to(a)
    b.invert()
    a.build(b.all_polygons())
    a.invert()
    return a.all_polygons()


def csg_intersect(a_polygons: list[CSGPolygon], b_polygons: list[CSGPolygon]) -> list[CSGPolygon]:
    """Boolean intersection of two polygon soups."""
    a = BSPNode(a_polygons)
    b = BSPNode(b_polygons)
    a.invert()
    b.clip_to(a)
    b.invert()
    a.clip_to(b)
    b.clip_to(a)
    a.build(b.all_polygons())
    a.invert()
    return a.all_polygons()
