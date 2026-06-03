"""Group 8: Extrusion, sweep, loft, pipe.

Tests from_extrusion, from_loft, from_sweep, from_pipe.
Operations not implemented in either library are reported as SKIP.

For sweep and pipe, a straight-line wire path is constructed via the active backend's
native API (OCC BRepBuilderAPI_MakeEdge, or compas_occ equivalent). If the native wire
constructor is unavailable the test is marked SKIP.

Usage::

    python 08_generators.py --backend compas_brep
    python 08_generators.py --backend compas_occ
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _bench import die, emit, load_backend, parse_args, record
from compas.geometry import Point, Polygon, Vector


def _make_wire_path_compas_brep(Brep, length=2.0):
    """Return a Brep whose native shape is a straight wire of the given length.

    Uses OCC BRepBuilderAPI_MakeEdge/MakeWire, which is available when the OCC
    backend is active. Raises RuntimeError if OCC is not importable.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Pnt

    half = length / 2.0
    p1 = gp_Pnt(0.0, 0.0, -half)
    p2 = gp_Pnt(0.0, 0.0, half)
    edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
    wire = BRepBuilderAPI_MakeWire(edge).Wire()
    return Brep.from_native(wire)


def _make_wire_path_compas_occ(OccBRep, length=2.0):
    """Return a BRep whose native shape is a straight wire, using compas_occ's API."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Pnt

    half = length / 2.0
    p1 = gp_Pnt(0.0, 0.0, -half)
    p2 = gp_Pnt(0.0, 0.0, half)
    edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
    wire = BRepBuilderAPI_MakeWire(edge).Wire()
    return OccBRep.from_native(wire)


def _make_wire_path(Brep, backend_name: str, length=2.0):
    if backend_name == "compas_brep":
        return _make_wire_path_compas_brep(Brep, length)
    elif backend_name == "compas_occ":
        return _make_wire_path_compas_occ(Brep, length)
    raise RuntimeError(f"Unknown backend: {backend_name!r}")


def main():
    args = parse_args()
    try:
        Brep = load_backend(args.backend)
    except ImportError as exc:
        die(f"Cannot import backend {args.backend!r}: {exc}")
        return

    results = []

    # from_extrusion: extrude a 1x1 square by (0, 0, 2) → expected volume ≈ 2.0, face_count 6
    def _extrusion_volume(B=Brep):
        profile = Polygon([Point(0, 0, 0), Point(1, 0, 0), Point(1, 1, 0), Point(0, 1, 0)])
        brep = B.from_extrusion(profile, Vector(0, 0, 2))
        return brep.volume

    def _extrusion_face_count(B=Brep):
        profile = Polygon([Point(0, 0, 0), Point(1, 0, 0), Point(1, 1, 0), Point(0, 1, 0)])
        brep = B.from_extrusion(profile, Vector(0, 0, 2))
        return len(brep.faces)

    record(results, "from_extrusion volume", "volume", _extrusion_volume)
    record(results, "from_extrusion face_count", "count", _extrusion_face_count)

    # from_loft: loft two NURBS circles — volume > 0, is_solid
    def _loft_is_solid(B=Brep):
        from compas_brep.curves.nurbs import NurbsCurve

        n = 16
        c1_pts = [Point(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
        c2_pts = [
            Point(0.5 * math.cos(2 * math.pi * i / n), 0.5 * math.sin(2 * math.pi * i / n), 2.0) for i in range(n)
        ]
        c1 = NurbsCurve.from_points(c1_pts, degree=3)
        c2 = NurbsCurve.from_points(c2_pts, degree=3)
        brep = B.from_loft([c1, c2])
        return bool(brep.is_solid)

    def _loft_volume_positive(B=Brep):
        from compas_brep.curves.nurbs import NurbsCurve

        n = 16
        c1_pts = [Point(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
        c2_pts = [
            Point(0.5 * math.cos(2 * math.pi * i / n), 0.5 * math.sin(2 * math.pi * i / n), 2.0) for i in range(n)
        ]
        c1 = NurbsCurve.from_points(c1_pts, degree=3)
        c2 = NurbsCurve.from_points(c2_pts, degree=3)
        brep = B.from_loft([c1, c2])
        return brep.volume > 0.0

    record(results, "from_loft is_solid", "bool", _loft_is_solid)
    record(results, "from_loft volume_positive", "bool", _loft_volume_positive)

    # from_sweep: sweep a small square face along a straight wire path (L=2)
    # Profile is a 0.2x0.2 square at z=-1 (start of wire); expected volume ≈ 0.04*2 = 0.08
    def _sweep_volume_positive(B=Brep, bn=args.backend):
        try:
            path = _make_wire_path(B, bn, length=2.0)
        except (ImportError, RuntimeError) as exc:
            raise NotImplementedError(f"wire path unavailable: {exc}") from exc
        from compas.geometry import Plane as _Plane

        profile = B.from_plane(_Plane(Point(0, 0, -1), Vector(0, 0, 1)), domain_u=(-0.1, 0.1), domain_v=(-0.1, 0.1))
        result = B.from_sweep(profile, path)
        return result.volume > 0.0

    record(results, "from_sweep volume_positive", "bool", _sweep_volume_positive)

    # from_pipe: pipe along a straight wire path (L=2, r=0.1) — volume ≈ π*r²*L
    def _pipe_volume(B=Brep, bn=args.backend):
        try:
            path = _make_wire_path(B, bn, length=2.0)
        except (ImportError, RuntimeError) as exc:
            raise NotImplementedError(f"wire path unavailable: {exc}") from exc
        return B.from_pipe(path, 0.1).volume

    record(results, "from_pipe volume", "volume", _pipe_volume)

    emit(results)


if __name__ == "__main__":
    main()
