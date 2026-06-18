# compas_brep

[![Github Actions Build Status](https://github.com/gramaziokohler/compas_brep/workflows/build/badge.svg)](https://github.com/gramaziokohler/compas_brep/actions)
[![License](https://img.shields.io/github/license/gramaziokohler/compas_brep.svg)](https://pypi.python.org/pypi/compas-brep)
[![PyPI Package latest release](https://img.shields.io/pypi/v/compas-brep.svg)](https://pypi.python.org/pypi/compas-brep)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/compas-brep.svg)](https://pypi.python.org/pypi/compas-brep)
[![Made with COMPAS](https://compas.dev/badge.svg)](https://compas.dev/#/)

A unified Brep wrapper for the [COMPAS](https://github.com/compas-dev/compas) framework with pluggable OCC and Rhino backends.

Provides a single `Brep` class with a stable public interface. The backend (OCC or Rhino) is selected automatically at runtime based on what is importable. All inputs and outputs are COMPAS types — never backend types.

## Installation

**Base (no backend):**

```bash
pip install compas-brep
```

**With OCC backend:**

```bash
pip install "compas-brep[occ]"
```

The Rhino backend is available automatically when running inside Rhino or with `rhinoinside` installed.

## Usage

```python
from compas_brep import Brep

brep = Brep.from_step("model.stp")

for face in brep.faces:
    surface = face.surface  # returns a NurbsSurface (COMPAS type)
```

## Running tests

Install the OCC backend and run:

```bash
uv pip install "cadquery-ocp-novtk>=7.8"
pytest -m occ -q
```
