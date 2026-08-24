"""Backend-neutral encode/decode for Brep edge curves.

The counterpart of ``surfaces/_codec.py``: one ``{"type": <tag>, "data": <payload>}``
codec shared by every serialize/deserialize site, so that adding a curve type touches
one place instead of four.

An analytic edge carries its conic **and the parameter interval the edge runs over**.
The interval is not redundant with the conic, and leaving it out is the subtle way to
break this format:

* A trim's pcurve is written over its edge curve's parameter interval, so a reader
  that reconstructs the interval differently from the writer lands every pcurve on
  that edge somewhere else.
* The intervals real kernels produce are not the tidy ones. Measured on OCC: a
  sphere's meridian runs ``[3*pi/2, 5*pi/2]`` and a tilted cut's full ellipse runs
  ``[3*pi/2, 3*pi/2 + 2*pi]``. Neither fits COMPAS ``Arc``'s ``0 <= angle <= 2*pi``,
  so the COMPAS type cannot be the only thing on the wire.

Hence ``circle`` and ``arc`` both carry a COMPAS ``Circle`` plus a domain, and differ
only in whether that domain is a full turn. COMPAS ``Arc`` is deliberately unused: it
would force the writer to rotate the frame to bring the angles into range, and every
pcurve on the edge would then have to be shifted to match -- work that buys nothing,
since the domain has to be on the wire regardless.

``line`` keeps its bare ``[[x, y, z], [x, y, z]]`` payload for backward compatibility
with v4/v5 documents; ``nurbs`` round-trips through COMPAS ``__data__`` as before.
"""

from __future__ import annotations

from compas.geometry import Circle
from compas.geometry import Ellipse
from compas.geometry import Line
from compas.geometry import Point

from compas_brep.errors import BrepError

from .nurbs import NurbsCurve

#: Every edge curve tag the exchange format defines.
EDGE_CURVE_TAGS = ("line", "circle", "arc", "ellipse", "nurbs")


def edge_curve_to_data(curve, domain: tuple[float, float] | None = None) -> dict:
    """Encode a Brep edge curve to a ``{"type", "data"}`` dict.

    Parameters
    ----------
    curve
        A COMPAS ``Line``, ``Circle``, ``Ellipse``, or a ``NurbsCurve``.
    domain
        The parameter interval the edge runs over, required for ``Circle`` and
        ``Ellipse`` and ignored otherwise. See :func:`compas_brep.exchange.analytic_curve_point`
        for what the parameter means.

    """
    from compas_brep.exchange import analytic_curve_is_full_turn

    if isinstance(curve, Line):
        return {
            "type": "line",
            "data": [
                [curve.start.x, curve.start.y, curve.start.z],
                [curve.end.x, curve.end.y, curve.end.z],
            ],
        }

    if isinstance(curve, (Circle, Ellipse)):
        if domain is None:
            raise BrepError(f"A {type(curve).__name__} edge curve must carry the parameter interval the edge runs over.")
        if isinstance(curve, Circle):
            tag = "circle" if analytic_curve_is_full_turn(domain) else "arc"
        else:
            tag = "ellipse"
        return {
            "type": tag,
            "data": {"curve": curve.__data__, "domain": [domain[0], domain[1]]},
        }

    if isinstance(curve, NurbsCurve):
        return {"type": "nurbs", "data": curve.__data__}

    raise BrepError(f"Cannot serialize edge curve of type {type(curve).__name__}")


def edge_curve_from_data(data: dict) -> tuple[Line | Circle | Ellipse | NurbsCurve, tuple[float, float] | None]:
    """Decode a ``{"type", "data"}`` dict back to ``(curve, domain)``.

    ``domain`` is ``None`` for the tags that carry their own parameterization
    (``line`` via its endpoints, ``nurbs`` via its knots).

    Reads v4, v5, and v6 documents: the analytic tags are new in v6, and the two
    older versions only ever wrote ``line`` and ``nurbs``.
    """
    tag = data["type"]
    payload = data["data"]

    if tag == "line":
        # v4/v5 and both backends' writers use a two-point list; ``BrepEdge.__data__``
        # has always written a ``{"start", "end"}`` mapping. Read both.
        if isinstance(payload, dict):
            return Line(Point(*payload["start"]), Point(*payload["end"])), None
        return Line(Point(*payload[0]), Point(*payload[1])), None

    if tag == "nurbs":
        return NurbsCurve.__from_data__(payload), None

    if tag in ("circle", "arc"):
        return Circle.__from_data__(payload["curve"]), tuple(payload["domain"])

    if tag == "ellipse":
        return Ellipse.__from_data__(payload["curve"]), tuple(payload["domain"])

    raise ValueError(f"Unknown edge curve type tag: {tag!r}")
