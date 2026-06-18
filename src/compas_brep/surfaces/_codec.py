"""Backend-neutral encode/decode for Brep face surfaces.

A single ``{"type": <tag>, "data": <payload>}`` codec shared by every
serialize/deserialize site so that adding a surface type touches one place
instead of five.

``Plane`` keeps its hand-rolled ``{"point", "normal"}`` payload for backward
compatibility with v4 documents; other types round-trip through their COMPAS
``__data__`` / ``__from_data__``.
"""

from __future__ import annotations

from compas.geometry import CylindricalSurface
from compas.geometry import Plane
from compas.geometry import Point
from compas.geometry import Vector

from .nurbs import NurbsSurface


def surface_to_data(surface) -> dict:
    """Encode a Brep face surface to a ``{"type", "data"}`` dict."""
    if isinstance(surface, Plane):
        return {
            "type": "plane",
            "data": {
                "point": [surface.point.x, surface.point.y, surface.point.z],
                "normal": [surface.normal.x, surface.normal.y, surface.normal.z],
            },
        }
    if isinstance(surface, NurbsSurface):
        return {"type": "nurbs", "data": surface.__data__}
    if isinstance(surface, CylindricalSurface):
        return {"type": "cylinder", "data": surface.__data__}
    raise TypeError(f"Cannot serialize surface of type {type(surface).__name__}")


def surface_from_data(data: dict):
    """Decode a ``{"type", "data"}`` dict back to a surface.

    Reads both v4 (``plane`` / ``nurbs`` only) and v5 documents.
    """
    tag = data["type"]
    payload = data["data"]
    if tag == "plane":
        return Plane(Point(*payload["point"]), Vector(*payload["normal"]))
    if tag == "nurbs":
        return NurbsSurface.__from_data__(payload)
    if tag == "cylinder":
        return CylindricalSurface.__from_data__(payload)
    raise ValueError(f"Unknown surface type tag: {tag!r}")
