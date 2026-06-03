"""Group 7: Mesh and STEP I/O.

Tests from_mesh, STEP round-trip, and to_viewmesh tessellation.

Usage::

    python 07_io.py --backend compas_brep
    python 07_io.py --backend compas_occ
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _bench import die, emit, load_backend, parse_args, record  # noqa: E402
from compas.datastructures import Mesh  # noqa: E402
from compas.geometry import Box, Cylinder  # noqa: E402


@contextlib.contextmanager
def _suppress_c_stdout():
    """Redirect C-level stdout (fd 1) to /dev/null during OCC STEP write calls."""
    old_fd = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(old_fd, 1)
        os.close(old_fd)


def _box_mesh():
    """Build a box-shaped mesh from a 1x1x1 box Mesh."""
    return Mesh.from_polyhedron(6)


def main():
    args = parse_args()
    try:
        Brep = load_backend(args.backend)
    except ImportError as exc:
        die(f"Cannot import backend {args.backend!r}: {exc}")
        return

    results = []

    # from_mesh: build a brep from a mesh, check face count and is_valid
    def _from_mesh_face_count(B=Brep):
        mesh = _box_mesh()
        brep = B.from_mesh(mesh)
        return len(brep.faces)

    def _from_mesh_is_valid(B=Brep):
        mesh = _box_mesh()
        brep = B.from_mesh(mesh)
        return bool(brep.is_valid)

    record(results, "from_mesh face_count", "count", _from_mesh_face_count)
    record(results, "from_mesh is_valid", "bool", _from_mesh_is_valid)

    # STEP round-trip: serialize a boolean-subtracted shape, reload, compare volume (1% tol)
    def _step_roundtrip_volume(B=Brep):
        box = B.from_box(Box(2.0, 2.0, 2.0))
        cyl = B.from_cylinder(Cylinder(0.3, 4.0))
        original = box - cyl
        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            path = f.name
        with _suppress_c_stdout():
            original.to_step(path)
        reloaded = B.from_step(path)
        return reloaded.volume

    def _step_roundtrip_original_volume(B=Brep):
        box = B.from_box(Box(2.0, 2.0, 2.0))
        cyl = B.from_cylinder(Cylinder(0.3, 4.0))
        original = box - cyl
        return original.volume

    record(results, "STEP roundtrip volume", "bool_volume", _step_roundtrip_volume)
    record(results, "STEP roundtrip original volume", "bool_volume", _step_roundtrip_original_volume)

    # to_viewmesh: tessellate a cylinder; vertex count and face count > 0
    def _viewmesh_vertex_count(B=Brep):
        brep = B.from_cylinder(Cylinder(0.5, 2.0))
        mesh = brep.to_viewmesh()
        return len(list(mesh.vertices()))

    def _viewmesh_face_count(B=Brep):
        brep = B.from_cylinder(Cylinder(0.5, 2.0))
        mesh = brep.to_viewmesh()
        return len(list(mesh.faces()))

    record(results, "to_viewmesh vertex_count", "count", _viewmesh_vertex_count)
    record(results, "to_viewmesh face_count", "count", _viewmesh_face_count)

    emit(results)


if __name__ == "__main__":
    main()
