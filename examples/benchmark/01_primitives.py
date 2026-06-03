"""Group 1: Primitive construction.

Tests Box, Cylinder, Sphere, Cone, Torus construction and reports volume, area,
face/edge/vertex counts, and is_solid for each primitive.

Usage::

    python 01_primitives.py --backend compas_brep
    python 01_primitives.py --backend compas_occ
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _bench import die, emit, load_backend, parse_args, record
from compas.geometry import Box, Cone, Cylinder, Sphere, Torus


def _primitive_records(results, Brep, label, make_fn):
    prefix = label
    _TYPE = {
        "volume": "volume",
        "area": "area",
        "face_count": "count",
        "edge_count": "topo_count",  # compas_occ counts per-face occurrence; values differ by design
        "vertex_count": "topo_count",
        "is_solid": "bool",
    }
    try:
        brep = make_fn(Brep)
    except (NotImplementedError, AttributeError) as exc:
        for metric, mtype in _TYPE.items():
            results.append({"name": f"{prefix} {metric}", "type": mtype, "value": None, "status": "SKIP", "reason": str(exc)})
        return
    except Exception as exc:
        for metric, mtype in _TYPE.items():
            results.append({"name": f"{prefix} {metric}", "type": mtype, "value": None, "status": "ERROR", "reason": str(exc)})
        return

    record(results, f"{prefix} volume", "volume", lambda b=brep: b.volume)
    record(results, f"{prefix} area", "area", lambda b=brep: b.area)
    record(results, f"{prefix} face_count", "count", lambda b=brep: len(b.faces))
    record(results, f"{prefix} edge_count", "topo_count", lambda b=brep: len(b.edges))
    record(results, f"{prefix} vertex_count", "topo_count", lambda b=brep: len(b.vertices))
    record(results, f"{prefix} is_solid", "bool", lambda b=brep: bool(b.is_solid))


def main():
    args = parse_args()
    try:
        Brep = load_backend(args.backend)
    except ImportError as exc:
        die(f"Cannot import backend {args.backend!r}: {exc}")
        return

    results = []

    _primitive_records(results, Brep, "Box", lambda B: B.from_box(Box(1.0, 1.0, 1.0)))
    _primitive_records(results, Brep, "Cylinder", lambda B: B.from_cylinder(Cylinder(0.5, 2.0)))
    _primitive_records(results, Brep, "Sphere", lambda B: B.from_sphere(Sphere(1.0)))
    _primitive_records(results, Brep, "Cone", lambda B: B.from_cone(Cone(0.5, 2.0)))
    _primitive_records(results, Brep, "Torus", lambda B: B.from_torus(Torus(1.0, 0.2)))

    emit(results)


if __name__ == "__main__":
    main()
