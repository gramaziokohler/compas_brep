"""Group 2: Boolean operations.

Tests union, difference, and intersection with standard shape pairs and reports
volume, face count, and is_solid.

Usage::

    python 02_booleans.py --backend compas_brep
    python 02_booleans.py --backend compas_occ
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _bench import die, emit, load_backend, parse_args, record
from compas.geometry import Box, Cylinder, Frame, Point, Sphere, Vector


def _bool_records(results, prefix, fn):
    try:
        brep = fn()
    except (NotImplementedError, AttributeError) as exc:
        for metric in ("volume", "face_count", "is_solid"):
            results.append(
                {
                    "name": f"{prefix} {metric}",
                    "type": "count" if metric == "face_count" else metric,
                    "value": None,
                    "status": "SKIP",
                    "reason": str(exc),
                }
            )
        return
    except Exception as exc:
        for metric in ("volume", "face_count", "is_solid"):
            results.append(
                {
                    "name": f"{prefix} {metric}",
                    "type": "count" if metric == "face_count" else metric,
                    "value": None,
                    "status": "ERROR",
                    "reason": str(exc),
                }
            )
        return

    record(results, f"{prefix} volume", "bool_volume", lambda b=brep: b.volume)
    record(results, f"{prefix} face_count", "count", lambda b=brep: len(b.faces))
    record(results, f"{prefix} is_solid", "bool", lambda b=brep: bool(b.is_solid))


def main():
    args = parse_args()
    try:
        Brep = load_backend(args.backend)
    except ImportError as exc:
        die(f"Cannot import backend {args.backend!r}: {exc}")
        return

    results = []

    # Pair 1: Box(2,2,2) − Cylinder(r=0.3, h=4)
    def _difference(B=Brep):
        box = B.from_box(Box(2.0, 2.0, 2.0))
        cyl = B.from_cylinder(Cylinder(0.3, 4.0))
        return box - cyl

    _bool_records(results, "Difference Box-Cylinder", _difference)

    # Pair 2: Box(2,2,2) + Box(1,1,1) translated by (1.5, 0, 0)
    def _union(B=Brep):
        box_a = B.from_box(Box(2.0, 2.0, 2.0))
        frame_b = Frame(Point(1.5, 0.0, 0.0), Vector(1, 0, 0), Vector(0, 1, 0))
        box_b = B.from_box(Box(1.0, 1.0, 1.0, frame_b))
        return box_a + box_b

    _bool_records(results, "Union Box+Box", _union)

    # Pair 3: Box(2,2,2) & Sphere(r=1.5)
    def _intersection(B=Brep):
        box = B.from_box(Box(2.0, 2.0, 2.0))
        sph = B.from_sphere(Sphere(1.5))
        return box & sph

    _bool_records(results, "Intersection Box&Sphere", _intersection)

    emit(results)


if __name__ == "__main__":
    main()
