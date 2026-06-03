"""Group 4: Topology inspection.

Tests face/edge/vertex counts and COMPAS sub-object types on Box and Cylinder.

Usage::

    python 04_topology.py --backend compas_brep
    python 04_topology.py --backend compas_occ
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _bench import die, emit, load_backend, parse_args, record
from compas.geometry import Box, Cylinder, Point


def _topology_records(results, Brep, label, make_fn):
    try:
        brep = make_fn(Brep)
    except Exception as exc:
        for suffix in (
            "face_count",
            "edge_count",
            "vertex_count",
            "face_surface_is_compas",
            "edge_curve_is_compas",
            "vertex_point_is_compas",
        ):
            results.append(
                {"name": f"{label} {suffix}", "type": "count", "value": None, "status": "ERROR", "reason": str(exc)}
            )
        return

    record(results, f"{label} face_count", "count", lambda b=brep: len(b.faces))
    record(results, f"{label} edge_count", "count", lambda b=brep: len(b.edges))
    record(results, f"{label} vertex_count", "count", lambda b=brep: len(b.vertices))

    def _face_surface_is_compas(b=brep):
        # Accept any Data subclass with control-point-like attributes, or Plane.
        # compas_brep returns its own NurbsSurface which differs from compas.geometry.NurbsSurface.
        for face in b.faces:
            surf = face.surface
            if surf is None:
                return False
            # Must be a COMPAS-style object (has no backend-native type leaking through)
            mod = type(surf).__module__
            if not (mod.startswith("compas") or mod.startswith("compas_brep")):
                return False
        return True

    def _edge_curve_is_compas(b=brep):
        for edge in b.edges:
            c = edge.curve
            if c is None:
                return False
            mod = type(c).__module__
            if not (mod.startswith("compas") or mod.startswith("compas_brep")):
                return False
        return True

    def _vertex_point_is_compas(b=brep):
        for v in b.vertices:
            if not isinstance(v.point, Point):
                return False
        return True

    record(results, f"{label} face_surface_is_compas", "bool", _face_surface_is_compas)
    record(results, f"{label} edge_curve_is_compas", "bool", _edge_curve_is_compas)
    record(results, f"{label} vertex_point_is_compas", "bool", _vertex_point_is_compas)


def main():
    args = parse_args()
    try:
        Brep = load_backend(args.backend)
    except ImportError as exc:
        die(f"Cannot import backend {args.backend!r}: {exc}")
        return

    results = []
    _topology_records(results, Brep, "Box(1,1,1)", lambda B: B.from_box(Box(1.0, 1.0, 1.0)))
    _topology_records(results, Brep, "Cylinder(r=0.5,h=2)", lambda B: B.from_cylinder(Cylinder(0.5, 2.0)))
    emit(results)


if __name__ == "__main__":
    main()
