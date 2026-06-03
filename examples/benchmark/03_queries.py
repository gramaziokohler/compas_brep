"""Group 3: Geometric queries.

Tests area, volume, centroid, aabb, is_solid, is_valid on a box and a cylinder.

Usage::

    python 03_queries.py --backend compas_brep
    python 03_queries.py --backend compas_occ
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _bench import die, emit, load_backend, parse_args, record
from compas.geometry import Box, Cylinder


def _query_records(results, Brep, label, make_fn):
    try:
        brep = make_fn(Brep)
    except Exception as exc:
        for suffix in (
            "area",
            "volume",
            "centroid_x",
            "centroid_y",
            "centroid_z",
            "aabb_xsize",
            "aabb_ysize",
            "aabb_zsize",
            "is_solid",
            "is_valid",
        ):
            results.append(
                {"name": f"{label} {suffix}", "type": "query", "value": None, "status": "ERROR", "reason": str(exc)}
            )
        return

    record(results, f"{label} area", "area", lambda b=brep: b.area)
    record(results, f"{label} volume", "volume", lambda b=brep: b.volume)

    def _centroid_x(b=brep):
        c = b.centroid
        return float(c.x)

    def _centroid_y(b=brep):
        c = b.centroid
        return float(c.y)

    def _centroid_z(b=brep):
        c = b.centroid
        return float(c.z)

    record(results, f"{label} centroid_x", "centroid", _centroid_x)
    record(results, f"{label} centroid_y", "centroid", _centroid_y)
    record(results, f"{label} centroid_z", "centroid", _centroid_z)

    def _aabb_xsize(b=brep):
        box = b.aabb
        return float(box.xsize)

    def _aabb_ysize(b=brep):
        box = b.aabb
        return float(box.ysize)

    def _aabb_zsize(b=brep):
        box = b.aabb
        return float(box.zsize)

    record(results, f"{label} aabb_xsize", "aabb_dim", _aabb_xsize)
    record(results, f"{label} aabb_ysize", "aabb_dim", _aabb_ysize)
    record(results, f"{label} aabb_zsize", "aabb_dim", _aabb_zsize)

    record(results, f"{label} is_solid", "bool", lambda b=brep: bool(b.is_solid))
    record(results, f"{label} is_valid", "bool", lambda b=brep: bool(b.is_valid))


def main():
    args = parse_args()
    try:
        Brep = load_backend(args.backend)
    except ImportError as exc:
        die(f"Cannot import backend {args.backend!r}: {exc}")
        return

    results = []
    _query_records(results, Brep, "Box(1,1,1)", lambda B: B.from_box(Box(1.0, 1.0, 1.0)))
    _query_records(results, Brep, "Cylinder(r=0.5,h=2)", lambda B: B.from_cylinder(Cylinder(0.5, 2.0)))
    emit(results)


if __name__ == "__main__":
    main()
