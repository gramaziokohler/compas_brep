# Introduction

`compas_brep` is a unified Brep wrapper for the [COMPAS](https://compas.dev) framework.
It consolidates the Brep implementations previously spread across `compas_rhino` and
`compas_occ` into a single coherent package with a stable public interface: the `Brep`
class is the only class you need to import, and its argument and return types are
always COMPAS types — never backend-specific ones.

The backend (OCC or Rhino) is selected automatically at runtime based on what's
importable, so switching environments requires no code changes.

Curious about the details? Start here:

- [What is a Brep?](brep-basics.md) — the shape model, in one page.
- [Motivation](motivation.md) — why wrap two backends instead of picking one.
- [Architecture](architecture.md) — what happens where, and how dispatch works.
