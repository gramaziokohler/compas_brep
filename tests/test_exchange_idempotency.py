"""OCC rebuild/re-extract round-trip stability.

``Brep.__from_data__(doc).__data__`` was not idempotent for the OCC backend: every
call re-extracted topology from a freshly rebuilt native ``TopoDS_Shape``, and the
rebuild (``brep_to_occ``) minted a fresh, independent ``TopoDS_Edge``/``TopoDS_Vertex``
per face rather than sharing one per document edge/vertex -- leaving
``BRepBuilderAPI_Sewing``'s 1e-6 tolerance to merge the near-duplicates back
together. Two consecutive round trips were enough to collapse a real cone into a
degenerate point (v2 e3 f2 -> v4 e2 f2 -> v1 e1 f1, volume 0.0), a positive-feedback
instability, not just seam-invalidity drift. See
.agents/issues/brep-exchange/08-occ-rebuild-does-not-share-edges.md.

Fixed by a shared vertex/edge table in ``brep_to_occ``, keyed by document identity
(``occ_rebuild`` already decodes each document vertex/edge index into one Python
object shared by every trim that uses it -- ``brep_to_occ`` just wasn't honoring
that sharing natively).
"""

from __future__ import annotations

import pytest
from compas.data import json_dump
from compas.data import json_load
from compas.tolerance import TOL
from exchange_fixtures import OCC_SOURCES
from exchange_fixtures import load_occ_fixture

from compas_brep import Brep


def _round_trip(data: dict) -> tuple[Brep, dict]:
    brep = Brep.__from_data__(data)
    return brep, brep.__data__


@pytest.mark.occ
@pytest.mark.parametrize("name", sorted(OCC_SOURCES))
def test_occ_round_trip_is_idempotent(name):
    # A second round trip through an already-rebuilt document must reproduce the
    # same connectivity and volume as the first -- not keep drifting toward collapse.
    brep1, data1 = _round_trip(load_occ_fixture(name))
    brep2, data2 = _round_trip(data1)

    assert len(data1["vertices"]) == len(data2["vertices"])
    assert len(data1["edges"]) == len(data2["edges"])
    assert len(data1["faces"]) == len(data2["faces"])
    assert TOL.is_close(brep1.volume, brep2.volume)


@pytest.mark.occ
def test_occ_cone_round_trip_never_collapses():
    # The issue's own reproduction: 3 consecutive round trips on a real cone must
    # neither keep changing connectivity nor let the volume drop to 0.0.
    data = load_occ_fixture("cone")
    volumes = []
    for _ in range(3):
        brep, data = _round_trip(data)
        volumes.append(brep.volume)
        assert len(data["vertices"]) > 0
        assert len(data["edges"]) > 0
        assert len(data["faces"]) == 2

    assert all(volume > 0.0 for volume in volumes)
    assert all(TOL.is_close(volume, volumes[0]) for volume in volumes)


@pytest.mark.occ
@pytest.mark.parametrize("name", sorted(OCC_SOURCES))
def test_json_dump_load_preserves_volume_and_face_count(name, tmp_path):
    # compas.data.json_dump/json_load chains exactly the two hops
    # (__data__, __from_data__) that expose the instability -- this is what
    # surfaced the defect originally, before it was known to be backend-internal.
    brep = Brep.__from_data__(load_occ_fixture(name))
    path = tmp_path / "brep.json"
    json_dump(brep, path)
    restored = json_load(path)

    assert len(restored.faces) == len(brep.faces)
    assert TOL.is_close(restored.volume, brep.volume)
