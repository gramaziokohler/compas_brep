"""The exchange document: its version tag and the shape of its loops.

ADR-0001 explains why the COMPAS-native JSON document, and not STEP, is the
cross-backend path. The pieces both backends must agree on live here so that the
agreement is one definition rather than a convention each side re-implements --
which is exactly how v5 ended up encoding loop role positionally with neither
writer guaranteeing the position.
"""

from __future__ import annotations

from collections.abc import Iterator

from compas_brep.curves import NurbsCurve
from compas_brep.errors import BrepError

EXCHANGE_VERSION = 6

LOOP_OUTER = "outer"
LOOP_INNER = "inner"

_LOOP_ROLES = (LOOP_OUTER, LOOP_INNER)


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
