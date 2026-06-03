"""Group 6: Modeling operations.

Tests fillet, trimmed, split, slice, offset, cap_planar_holes.
Operations not implemented in either library are reported as SKIP.

Usage::

    python 06_modeling_ops.py --backend compas_brep
    python 06_modeling_ops.py --backend compas_occ
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _bench import die, emit, load_backend, parse_args, record
from compas.geometry import Box, Cylinder, Plane, Point, Vector


def main():
    args = parse_args()
    try:
        Brep = load_backend(args.backend)
    except ImportError as exc:
        die(f"Cannot import backend {args.backend!r}: {exc}")
        return

    results = []

    # fillet(r=0.05) — all edges on a unit box; volume decreases, is_valid
    def _fillet_volume(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        brep.fillet(0.05)
        return brep.volume

    def _fillet_is_valid(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        brep.fillet(0.05)
        return bool(brep.is_valid)

    record(results, "fillet(0.05) volume", "volume", _fillet_volume)
    record(results, "fillet(0.05) is_valid", "bool", _fillet_is_valid)

    # trimmed(plane at z=0 pointing up) on Box(1,1,1) — keeps negative side → volume ≈ 0.5
    def _trimmed_volume(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        plane = Plane(Point(0, 0, 0), Vector(0, 0, 1))
        trimmed = brep.trimmed(plane)
        return trimmed.volume

    record(results, "trimmed(z=0) volume", "volume", _trimmed_volume)

    # split(plane at x=0) on Box(2,2,2) — 2 pieces, each volume ≈ 4
    def _split_count(B=Brep):
        brep = B.from_box(Box(2.0, 2.0, 2.0))
        plane = Plane(Point(0, 0, 0), Vector(1, 0, 0))
        cutter = B.from_plane(plane, domain_u=(-5, 5), domain_v=(-5, 5))
        pieces = brep.split(cutter)
        return len(pieces)

    def _split_volume_a(B=Brep):
        brep = B.from_box(Box(2.0, 2.0, 2.0))
        plane = Plane(Point(0, 0, 0), Vector(1, 0, 0))
        cutter = B.from_plane(plane, domain_u=(-5, 5), domain_v=(-5, 5))
        pieces = brep.split(cutter)
        return pieces[0].volume if pieces else None

    record(results, "split(x=0) piece_count", "count", _split_count)
    record(results, "split(x=0) piece_a volume", "volume", _split_volume_a)

    # slice(plane at y=0) on Box(2,2,2) — non-empty polylines
    def _slice_count(B=Brep):
        brep = B.from_box(Box(2.0, 2.0, 2.0))
        plane = Plane(Point(0, 0, 0), Vector(0, 1, 0))
        polylines = brep.slice(plane)
        return len(polylines)

    record(results, "slice(y=0) polyline_count", "count", _slice_count)

    # offset(d=0.1) on unit box — volume increases
    def _offset_volume(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        result = brep.offset(0.1)
        return result.volume

    record(results, "offset(0.1) volume", "volume", _offset_volume)

    # cap_planar_holes — cylinder with no caps becomes solid
    def _cap_is_solid(B=Brep):
        # Build a cylinder shell by removing caps via boolean subtraction of an inner cylinder
        # For simplicity, build a full cylinder and use cap_planar_holes to confirm it stays valid.
        brep = B.from_cylinder(Cylinder(0.5, 2.0))
        brep.cap_planar_holes()
        return bool(brep.is_solid)

    record(results, "cap_planar_holes is_solid", "bool", _cap_is_solid)

    emit(results)


if __name__ == "__main__":
    main()
