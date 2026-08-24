# Motivation

Two mature Brep kernels are common in AEC/design software: **Rhino**'s and
**OpenCASCADE (OCC)**'s. Neither covers every use case on its own.

| | Rhino | OCC |
|---|---|---|
| Where it runs | Inside Rhino / Grasshopper (licensed) | Anywhere Python runs — CI, servers, Linux |
| Strengths | Mature NURBS modeling, the tool most AEC designers already use | Free, open source, scriptable headless |
| Weaknesses | No Rhino, no Brep | Rougher edges on some operations (fillets, some booleans) |

Before `compas_brep`, COMPAS had two separate Brep wrappers — one in
`compas_rhino`, one in `compas_occ` — with diverging APIs. A script written
against one didn't run against the other, and bugs got fixed in one but not
the other.

`compas_brep` wraps both behind a single `Brep` class with one API. Write the
code once:

- Inside Rhino/Grasshopper, it runs on the Rhino kernel.
- On CI, a server, or a plain Python install, it runs on OCC.
- Files can move between the two (see [Exchange format](architecture.md#exchange-format)),
  so a Brep built in Grasshopper can be checked, tested, and processed
  headlessly in CI, and vice versa.

No code branches on which backend is active — `compas_brep` picks it
automatically at runtime, based on what's importable. See
[Architecture](architecture.md) for how.
