# compas_brep

[![Github Actions Build Status](https://github.com/gramaziokohler/compas_brep/actions/workflows/build.yml/badge.svg)](https://github.com/gramaziokohler/compas_brep/actions)
[![License](https://img.shields.io/github/license/gramaziokohler/compas_brep)](https://pypi.python.org/pypi/compas-brep)
[![PyPI Package latest release](https://img.shields.io/pypi/v/compas-brep)](https://pypi.python.org/pypi/compas-brep)
[![Made with COMPAS](https://compas.dev/badge.svg)](https://compas.dev/#/)

A unified Brep wrapper for the [COMPAS](https://github.com/compas-dev/compas) framework with pluggable OCC and Rhino backends.

Provides a single `Brep` class with a stable public interface. The backend (OCC or Rhino) is selected automatically at runtime based on what is importable. All inputs and outputs are COMPAS types — never backend types.

Examples in `examples/` have mostly been copied from [COMPAS OCC](https://github.com/compas-dev/compas_occ) which is used as benchmark for this project.

## Installation

**Base (no backend):**

```bash
pip install compas_brep
```

**With [OCC backend](https://github.com/CadQuery/OCP):**

```bash
pip install "compas_brep[occ]"
```

The Rhino backend is available automatically when running inside Rhino.

## Usage

```python
import os
from compas_brep import Brep, DATA
from compas_viewer import Viewer

brep = Brep.from_step(os.path.join(DATA, "box_with_holes.stp"))

for face in brep.faces:
    print(face.surface)  # Plane for flat faces, NurbsSurface for curved faces

viewer = Viewer()
viewer.scene.add(brep)

viewer.show()

```

## Running tests

Install the OCC backend and run:

```bash
uv pip install "cadquery-ocp-novtk>=7.8"
pytest -m occ -q
```
