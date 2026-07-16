"""The source geometry behind ``tests/fixtures/``, and how to compare against it.

The committed fixtures are real Rhino-authored exchange documents. They exist
because CI has no Rhino license and ``-m 'not rhino'`` skips Rhino tests by
default even locally, so a live cross-backend round-trip is a test that never
runs. Reading a committed Rhino document from an OCC-marked test is the only
mechanism that catches "Rhino writes a tag OCC cannot read" on CI.

This module is the single definition of what each fixture is built from, shared
by the OCC-marked readers, the Rhino-marked regeneration test, and the refresh
path -- so the geometry cannot drift apart from the document it authored.

To refresh the fixtures intentionally, on a machine with a Rhino license::

    pytest -m rhino tests/test_exchange_fixtures.py --refresh-fixtures

That rewrites every file from live Rhino instead of asserting against it. Review
the diff: a change here is a change to the cross-backend contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from compas.geometry import Box
from compas.geometry import Cylinder
from compas.geometry import Sphere
from compas.tolerance import TOL

from compas_brep import Brep

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def build_box() -> Brep:
    """A unit box: planar faces, one outer loop each, no singular trims."""
    return Brep.from_box(Box(1.0, 1.0, 1.0))


def build_filleted_box() -> Brep:
    """A filleted box: NURBS fillet faces, and the case that caught the rectangular crop."""
    return Brep.from_box(Box(2.0, 2.0, 2.0)).filleted(0.3)


def build_sphere() -> Brep:
    """A sphere: singular trims at both poles."""
    return Brep.from_sphere(Sphere(1.0))


def build_box_with_hole() -> Brep:
    """A box with a through-hole: the inner loop, on two faces."""
    return Brep.from_box(Box(2.0, 2.0, 2.0)) - Brep.from_cylinder(Cylinder(0.3, 4.0))


def build_cylinder() -> Brep:
    """A cylinder: the analytic ``cylinder`` tag, and a seam."""
    return Brep.from_cylinder(Cylinder(0.5, 2.0))


SOURCES = {
    "box": build_box,
    "filleted_box": build_filleted_box,
    "sphere": build_sphere,
    "box_with_hole": build_box_with_hole,
    "cylinder": build_cylinder,
}

# The fixtures above are Rhino-authored and read by OCC. These are the mirror: OCC
# -authored documents, committed so that a Rhino-marked test can read them without an
# OCC install. Without them the OCC -> Rhino direction is verified nowhere, since
# neither backend is ever importable in the same process as the other.
OCC_SOURCES = {
    "cylinder": build_cylinder,
}


def fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"rhino_{name}.json"


def occ_fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"occ_{name}.json"


def load_fixture(name: str) -> dict:
    with open(fixture_path(name)) as f:
        return json.load(f)


def load_occ_fixture(name: str) -> dict:
    with open(occ_fixture_path(name)) as f:
        return json.load(f)


def _dump(path: Path, data: dict) -> None:
    FIXTURE_DIR.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def write_fixture(name: str, data: dict) -> None:
    _dump(fixture_path(name), data)


def write_occ_fixture(name: str, data: dict) -> None:
    _dump(occ_fixture_path(name), data)


def documents_differ(committed, regenerated, path: str = "") -> str | None:
    """Return a description of the first difference between two documents, or None.

    Structure -- keys, lengths, tags, roles, indices -- must match exactly. Floats
    only have to match within ``TOL``: the fixtures are kernel output, and pinning
    them bit-exactly would make this a tripwire for Rhino's own version rather than
    a detector of drift in our writer.
    """
    if isinstance(committed, dict):
        if not isinstance(regenerated, dict):
            return f"{path}: dict became {type(regenerated).__name__}"
        if committed.keys() != regenerated.keys():
            missing = sorted(set(committed) ^ set(regenerated))
            return f"{path}: keys differ ({missing})"
        for key in committed:
            found = documents_differ(committed[key], regenerated[key], f"{path}.{key}")
            if found:
                return found
        return None

    if isinstance(committed, list):
        if not isinstance(regenerated, list):
            return f"{path}: list became {type(regenerated).__name__}"
        if len(committed) != len(regenerated):
            return f"{path}: length {len(committed)} -> {len(regenerated)}"
        for i, (a, b) in enumerate(zip(committed, regenerated)):
            found = documents_differ(a, b, f"{path}[{i}]")
            if found:
                return found
        return None

    if isinstance(committed, bool) or isinstance(regenerated, bool):
        return None if committed is regenerated else f"{path}: {committed} -> {regenerated}"

    if isinstance(committed, (int, float)) and isinstance(regenerated, (int, float)):
        return None if TOL.is_close(committed, regenerated) else f"{path}: {committed} -> {regenerated}"

    return None if committed == regenerated else f"{path}: {committed!r} -> {regenerated!r}"
