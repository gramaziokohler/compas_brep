# Introduction

`compas_brep` is a unified Brep wrapper for the [COMPAS](https://compas.dev) framework.
It consolidates the Brep implementations previously spread across `compas_rhino` and
`compas_occ` into a single coherent package with a stable public interface.

## Design principles

**Single public interface**
:   The `Brep` class is the only class users need to import. All argument and return
    types are COMPAS types — never backend-specific types.

**Pluggable backends**
:   The backend (OCC or Rhino) is selected automatically at runtime based on what
    is importable. Switching environments requires no code changes.

**Lazy topology**
:   `BrepVertex`, `BrepEdge`, `BrepLoop`, `BrepFace`, and `BrepTrim` are
    native-handle wrappers. Properties (`.point`, `.curve`, `.surface`, …) call
    into the native kernel on demand and cache results per-property.

**Pure-Python geometry values**
:   `NurbsCurve` and `NurbsSurface` are plain value types storing control points,
    knots, and weights. They carry no backend dependency.

## Architecture overview

```
Brep  (public interface)
 └── _native_brep  →  TopoDS_Shape (OCC)  |  Rhino.Geometry.Brep (Rhino)

Brep.faces  →  list[BrepFace]   (native-handle wrappers, lazily populated)
BrepFace.surface  →  NurbsSurface  (COMPAS value type, lazily extracted)
```

Operations are dispatched through the COMPAS plugin system — `@pluggable`
functions in `compas_brep.operations` that each backend implements with
`@plugin` decorators gated by `requires=["OCP"]` or `requires=["Rhino"]`.
