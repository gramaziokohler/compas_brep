"""Group 5: Transformations.

Tests translate, rotate, and transformed copy on a unit box. Volume must be invariant;
centroid must match the expected transformed position.

Usage::

    python 05_transforms.py --backend compas_brep
    python 05_transforms.py --backend compas_occ
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _bench import die, emit, load_backend, parse_args, record
from compas.geometry import Box, Rotation, Translation, Vector


def main():
    args = parse_args()
    try:
        Brep = load_backend(args.backend)
    except ImportError as exc:
        die(f"Cannot import backend {args.backend!r}: {exc}")
        return

    results = []

    # Translate by (1, 2, 3) — volume invariant, centroid shifts
    def _translate_volume(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        T = Translation.from_vector(Vector(1, 2, 3))
        brep.transform(T)
        return brep.volume

    def _translate_centroid_x(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        T = Translation.from_vector(Vector(1, 2, 3))
        brep.transform(T)
        return float(brep.centroid.x)

    def _translate_centroid_y(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        T = Translation.from_vector(Vector(1, 2, 3))
        brep.transform(T)
        return float(brep.centroid.y)

    def _translate_centroid_z(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        T = Translation.from_vector(Vector(1, 2, 3))
        brep.transform(T)
        return float(brep.centroid.z)

    record(results, "Translate(1,2,3) volume", "volume", _translate_volume)
    record(results, "Translate(1,2,3) centroid_x", "centroid", _translate_centroid_x)
    record(results, "Translate(1,2,3) centroid_y", "centroid", _translate_centroid_y)
    record(results, "Translate(1,2,3) centroid_z", "centroid", _translate_centroid_z)

    # Rotate 45° around Z — volume invariant
    def _rotate_volume(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        R = Rotation.from_axis_and_angle([0, 0, 1], math.radians(45))
        brep.transform(R)
        return brep.volume

    record(results, "Rotate45Z volume", "volume", _rotate_volume)

    # transformed(T) returns a copy — original and copy have equal volume
    def _transformed_copy_volume(B=Brep):
        brep = B.from_box(Box(1.0, 1.0, 1.0))
        T = Translation.from_vector(Vector(5, 5, 5))
        copy = brep.transformed(T)
        return copy.volume

    record(results, "transformed(T) copy volume", "volume", _transformed_copy_volume)

    emit(results)


if __name__ == "__main__":
    main()
