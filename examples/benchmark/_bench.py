"""Shared utilities for benchmark scripts."""

from __future__ import annotations

import argparse
import json
import os
import sys


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend",
        choices=["compas_brep", "compas_occ"],
        default=os.environ.get("BREP_BACKEND", "compas_brep"),
    )
    return parser.parse_args()


def load_backend(name: str):
    """Return the Brep class for the requested backend."""
    if name == "compas_brep":
        from compas_brep import Brep

        return Brep
    elif name == "compas_occ":
        from compas_occ.brep import OCCBrep  # noqa: PLC0415

        return OCCBrep
    raise ValueError(f"Unknown backend: {name!r}")


def _skip_exc_types():
    types = [NotImplementedError, AttributeError]
    try:
        from compas.plugins import PluginNotInstalledError

        types.append(PluginNotInstalledError)
    except ImportError:
        pass
    return tuple(types)


_SKIP_EXC = _skip_exc_types()


def record(results: list, name: str, type_: str, fn):
    """Call fn(), append result dict; catch errors as SKIP or ERROR."""
    try:
        value = fn()
        results.append({"name": name, "type": type_, "value": value, "status": "ok"})
    except _SKIP_EXC as exc:
        results.append({"name": name, "type": type_, "value": None, "status": "SKIP", "reason": str(exc)})
    except Exception as exc:
        results.append({"name": name, "type": type_, "value": None, "status": "ERROR", "reason": str(exc)})


def emit(results: list) -> None:
    print(json.dumps(results, indent=2))


def die(msg: str) -> None:
    print(json.dumps([{"name": "_fatal", "type": "fatal", "value": None, "status": "ERROR", "reason": msg}]))
    sys.exit(1)
