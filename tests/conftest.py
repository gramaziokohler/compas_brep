"""pytest configuration for compas_brep tests.

Registers backend markers and applies skip conditions automatically:
- @pytest.mark.occ  — requires OCP (cadquery-ocp-novtk)
- @pytest.mark.rhino — requires rhinoinside
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--refresh-fixtures",
        action="store_true",
        default=False,
        help="Rewrite the committed exchange fixtures from live Rhino instead of asserting against them. Requires -m rhino.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "occ: tests that require the OCC backend (OCP / cadquery-ocp-novtk)")
    config.addinivalue_line("markers", "rhino: tests that require the Rhino backend (rhinoinside)")


def pytest_collection_modifyitems(config, items):
    try:
        import OCP  # noqa: F401

        occ_available = True
    except ImportError:
        occ_available = False

    try:
        import rhinoinside  # noqa: F401

        rhino_available = True
    except ImportError:
        rhino_available = False

    for item in items:
        if "occ" in item.keywords and not occ_available:
            item.add_marker(pytest.mark.skip(reason="OCP not installed — install compas_brep[occ]"))
        if "rhino" in item.keywords and not rhino_available:
            item.add_marker(pytest.mark.skip(reason="rhinoinside not installed"))
