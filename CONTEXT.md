# compas_brep — Project Context

## Purpose

`compas_brep` is a thin, unified wrapper around Rhino and OpenCASCADE (OCC) Brep implementations, built on top of the [COMPAS](https://github.com/compas-dev/compas) framework.

The project grew out of an earlier experiment building a pure-Python CSG/Brep engine. That direction was abandoned. The current goal is instead to take the *existing* compas Brep wrappers (historically split across `compas_rhino` and `compas_occ`) and reshape them into a single, coherent, pip-installable package that is easier to maintain and less error-prone.

## Core Design

A single `Brep` class serves as the public interface. It is a thin wrapper: its properties and methods delegate all real work to a backend. The backend is selected at runtime depending on the environment (Rhino or OCC).

```
Brep (public interface)
 ├── .backend  →  OccBrep  (when compas_occ is available)
 └── .backend  →  RhinoBrep  (when running inside Rhino)
```

Each property and method on `Brep` generally does one thing: call the equivalent on the backend and return the result. Business logic stays in the backends; the interface stays stable.

## Goals

- **Single installable package** — `pip install compas_brep` works; no manual plugin juggling.
- **Runtime backend selection** — the correct backend is picked automatically; user code never branches on the environment.
- **Stable public interface** — `Brep` looks the same regardless of backend.
- **Thin delegation layer** — the interface class contains almost no logic; backends own their implementation.
- **Easier maintenance** — adding a new operation means implementing it once per backend and exposing it once on `Brep`.

## What This Is Not

- Not a pure-Python Brep implementation.
- Not a new geometry kernel.
- Not a replacement for OCC or Rhino's native Brep capabilities.

## Backends

| Backend | Module | Activated when |
|---------|--------|----------------|
| OCC | `compas_brep.backend.occ` | `compas_occ` importable |
| Rhino | `compas_brep.backend.rhino` | running inside Rhino |

## Key Files

- [`src/compas_brep/brep.py`](src/compas_brep/brep.py) — the public `Brep` interface
- [`src/compas_brep/backend/`](src/compas_brep/backend/) — per-backend implementations
- [`src/compas_brep/operations.py`](src/compas_brep/operations.py) — boolean and geometric operations delegated to the backend
- [`src/compas_brep/face.py`](src/compas_brep/face.py), [`curves/`](src/compas_brep/curves/), [`surfaces/`](src/compas_brep/surfaces/) — geometry sub-types with the same delegation pattern
