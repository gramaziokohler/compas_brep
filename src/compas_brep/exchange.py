"""The exchange document: its version tag and the shape of its loops.

ADR-0001 explains why the COMPAS-native JSON document, and not STEP, is the
cross-backend path. The pieces both backends must agree on live here so that the
agreement is one definition rather than a convention each side re-implements --
which is exactly how v5 ended up encoding loop role positionally with neither
writer guaranteeing the position.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from compas.geometry import ConicalSurface
from compas.geometry import CylindricalSurface
from compas.geometry import Point
from compas.geometry import SphericalSurface
from compas.geometry import ToroidalSurface

from compas_brep.curves import NurbsCurve
from compas_brep.errors import BrepError

EXCHANGE_VERSION = 6

LOOP_OUTER = "outer"
LOOP_INNER = "inner"

_LOOP_ROLES = (LOOP_OUTER, LOOP_INNER)


# =============================================================================
# The parameter space of an analytic surface tag
# =============================================================================
#
# A pcurve is only meaningful against a parameterization, so tagging a face
# `cylinder` says nothing unless both backends measure (u, v) the same way. The
# definition below is the document's, stated once: u is the angle about the
# frame's z-axis for every analytic tag, and v is what the tag's own geometry
# makes it.
#
# It matches OCC's native parameterization of the corresponding Geom_ surface,
# which is not a coincidence -- OCC's pcurves are already written in it, so
# adopting it costs the OCC backend nothing and keeps it the format's primary
# author (ADR-0002). `test_exchange_parameterization.py` pins that agreement
# against the real kernel on CI rather than leaving it as a claim here.
#
# Rhino agrees with none of it. Rhino parameterizes these surfaces by arc length
# -- so its own (u, v) must be mapped into this space on the way out and its
# surfaces rebuilt in this space on the way in. That mapping is the Rhino
# backend's problem and lives there; what the mapping is *onto* is this.


def _cone_semi_angle(surface: ConicalSurface) -> float:
    """The cone's half-opening angle, negative for a cone that tapers along +z."""
    return math.atan(-surface.radius / surface.height)


def analytic_surface_point(surface, u: float, v: float) -> Point:
    """Evaluate an analytic surface at ``(u, v)`` in the document's parameter space.

    Parameters
    ----------
    surface
        A COMPAS analytic surface carrying one of the format's analytic tags.
    u
        The angle about the frame's z-axis, in radians, for every tag.
    v
        The height along the axis (``cylinder``), the latitude in
        ``[-pi/2, pi/2]`` (``sphere``), the angle about the pipe (``torus``), or
        the distance along the generating line from the base circle (``cone``).

    Notes
    -----
    This is deliberately not ``surface.point_at``: COMPAS normalizes both
    parameters to ``[0, 1]``, and the document does not.

    """
    frame = surface.frame
    origin = frame.point

    if isinstance(surface, CylindricalSurface):
        radial, axial = surface.radius, v
    elif isinstance(surface, SphericalSurface):
        radial, axial = surface.radius * math.cos(v), surface.radius * math.sin(v)
    elif isinstance(surface, ToroidalSurface):
        radial = surface.radius_axis + surface.radius_pipe * math.cos(v)
        axial = surface.radius_pipe * math.sin(v)
    elif isinstance(surface, ConicalSurface):
        alpha = _cone_semi_angle(surface)
        radial, axial = surface.radius + v * math.sin(alpha), v * math.cos(alpha)
    else:
        raise BrepError(f"Not an analytic surface of the exchange format: {type(surface).__name__}")

    return Point(
        *(
            origin
            + frame.xaxis * (radial * math.cos(u))
            + frame.yaxis * (radial * math.sin(u))
            + frame.zaxis * axial
        )
    )


def analytic_surface_params(surface, point) -> tuple[float, float]:
    """Invert :func:`analytic_surface_point` for a point on ``surface``.

    ``u`` comes back folded into ``(-pi, pi]``. A point off the surface is not
    rejected -- it is projected -- so this answers "where would this point be",
    which is what recovering a parameter map needs.
    """
    frame = surface.frame
    offset = Point(*point) - frame.point
    x = offset.dot(frame.xaxis)
    y = offset.dot(frame.yaxis)
    z = offset.dot(frame.zaxis)
    u = math.atan2(y, x)

    if isinstance(surface, CylindricalSurface):
        return u, z
    if isinstance(surface, SphericalSurface):
        # Clamped: a point a rounding error off the pole would otherwise be a domain error.
        return u, math.asin(max(-1.0, min(1.0, z / surface.radius)))
    if isinstance(surface, ToroidalSurface):
        return u, math.atan2(z, math.hypot(x, y) - surface.radius_axis)
    if isinstance(surface, ConicalSurface):
        return u, z / math.cos(_cone_semi_angle(surface))
    raise BrepError(f"Not an analytic surface of the exchange format: {type(surface).__name__}")


def analytic_surface_v_is_periodic(surface) -> bool:
    """Whether ``v`` wraps every ``2 * pi`` for this tag, as ``u`` always does.

    Only the torus, whose ``v`` runs around the pipe. A sphere's ``v`` is a
    latitude: it is bounded, not periodic.
    """
    return isinstance(surface, ToroidalSurface)


def document_version(data: dict) -> int:
    """Return the version of an exchange document.

    A document with no version tag predates the tag and is read as v4.
    """
    return data.get("version", 4)


def loop_to_data(role: str, trims: list[dict]) -> dict:
    """Encode one loop of a face, tagged with the role it plays on that face."""
    if role not in _LOOP_ROLES:
        raise BrepError(f"Not a loop role: {role!r}. Expected one of {_LOOP_ROLES}.")
    return {"type": role, "trims": trims}


def face_loops_from_data(face_data: dict, version: int) -> Iterator[tuple[str, list[dict]]]:
    """Yield ``(role, trims)`` for each loop of a face document.

    v6 tags every loop explicitly. v4 and v5 encode the role by position --
    ``loops[0]`` is outer, the rest are inner -- a convention no writer of those
    versions enforced. Honoring it is a backward-compatibility concession, and
    reading it here keeps it confined to the legacy path.
    """
    loops = face_data["loops"]

    if version < 6:
        for i, trims in enumerate(loops):
            yield (LOOP_OUTER if i == 0 else LOOP_INNER), trims
        return

    for loop_data in loops:
        role = loop_data["type"]
        if role not in _LOOP_ROLES:
            raise BrepError(f"Not a loop role: {role!r}. Expected one of {_LOOP_ROLES}.")
        yield role, loop_data["trims"]


def trim_pcurve_from_data(trim_data: dict, version: int) -> NurbsCurve | None:
    """Decode a trim's pcurve.

    The pcurve is what distinguishes a genuinely trimmed face from a rectangular
    patch, so v6 makes it non-nullable: a v6 writer that cannot produce one raises
    rather than emitting ``null`` for a reader to find. v4 and v5 writers were
    allowed to emit ``null``, and those documents still read -- returning None is a
    concession to them, which is why it lives here rather than in either backend.
    """
    pcurve_data = trim_data.get("curve_2d")

    if pcurve_data is None:
        if version >= 6:
            raise BrepError("Trim has no pcurve. Every trim of a v6 document must carry one.")
        return None

    return NurbsCurve.__from_data__(pcurve_data)
