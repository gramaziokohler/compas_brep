# Installation

## Stable

Stable releases are available on PyPI.

```bash
pip install compas-brep
```

## With OCC backend

The OCC backend requires `cadquery-ocp-novtk`, which in turn requires Python ≥ 3.10.

Both the 7.x and 8.x series are supported. Which one you get is decided by your Python
version: 8.x requires Python ≥ 3.11, so Python 3.10 resolves to the latest 7.9.x instead.

```bash
pip install "compas-brep[occ]"
```

## Latest (from source)

```bash
git clone https://github.com/gramaziokohler/compas_brep.git
cd compas_brep
pip install -e .
```

## Development

```bash
git clone https://github.com/gramaziokohler/compas_brep.git
cd compas_brep
pip install -e ".[dev]"
```

## Rhino

`compas_brep` targets Python 3.9 to remain compatible with Rhino 8's 
CPython runtime. Install it via `# r: compas_brep` inside the Rhino/Grasshopper script editor or:

The Rhino backend activates automatically when `Rhino` is importable; no extra
install flag is needed.
