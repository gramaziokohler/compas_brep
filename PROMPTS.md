# compas_brep Prompt Log

Rolling log of prompts given to Claude during the development of this project.

---

## Prompt 1 — Project Bootstrap (2026-03-19)

> you are going to help me with a small side project that might turn huge: I'd like us to make a fully functional Brep implementation in pure python, based on the COMPAS framework. meaning we'll use COMPAS datastructures and geometry primitives to describe the Brep and COMPAS's algorithms to implement all of the brep modeling operations (trimming, booleans, chamfer, extrusion etc.). The Brep class itself will adopt the interface of compas.geometry.Brep. do a first iteration. the success criteria is the ability to create two breps out of two compas boxes and run a boolean subtraction of one from the other. then the result is to be converted to mesh and visualized using compas viewer.
> relevant projects are:
> https://github.com/compas-dev/compas
> https://github.com/compas-dev/compas_viewer
>
> use as reference the brep implementations of
> https://github.com/Open-Cascade-SAS/OCCT
> https://github.com/mcneel/opennurbs
>
> use UV and ruff and other modern tools for python, use python 3.13
> GO!

**Result:** Created the project with UV, ruff, pytest. Implemented `PythonBrep` inheriting from `compas.geometry.Brep`, with BSP-tree CSG engine for boolean operations (union, subtract, intersect). Topology classes: BrepVertex, BrepEdge, BrepLoop, BrepFace, BrepTrim. `from_box`, `to_viewmesh`, `to_meshes`. All 6 tests passing. Volume identity `(A-B) + (A&B) = A` verified.

---

## Prompt 2 — Drop Inheritance, Rename (2026-03-19)

> looks like a great start. to continue, don't inherit from Brep, provide the same interface though. and then rename to just "Brep" instead of "PythonBrep"

**Result:** Removed all COMPAS base class inheritance. Renamed `PythonBrep` -> `Brep`, `PythonBrepVertex` -> `BrepVertex`, etc. All classes standalone with matching interfaces. No more `__new__` override needed.

---

## Prompt 3 — Viewer Integration (2026-03-19)

> when using compas occ Brep, the viewer seems to take a Brep directly and the visualized object does not seem triangulated. any idea why that might be?

**Result:** Researched the compas_viewer pipeline. Added `to_tesselation()` returning `(Mesh, list[Polyline])`. Created `compas_brep.scene.BrepObject` for viewer integration. Registered via COMPAS plugin system (`__all_plugins__`). The viewer now accepts `Brep` directly via `viewer.scene.add(brep)` with proper edge boundary rendering. Brep now inherits from `compas.data.Data` to satisfy the scene system.

---

## Prompt 4 — Fix Solid Appearance (2026-03-19)

> much better but the resulting brep appears like it's made out of 3 separate solids, using compas_occ it simply appears as a single solid

**Result:** Implemented coplanar face merging as a post-CSG step. Added T-junction resolution (inserting vertices where one polygon's vertex lies on another's edge). Faces reduced from 15 to 9 after boolean subtraction. Internal seam edges eliminated — result now appears as a single solid.

---

## Prompt 5 — Major Expansion: NURBS Curves, Surfaces, Brep Operations (2026-03-20)

> I've dropped a bunch of example scripts in the examples folder, these are from compas_occ. our brep should eventually support the same functionality. expand our implementation to support as many of these example as possible. there are also examples for nurbs curves and surfaces. these are supported in COMPAS in very much the same way as breps (plugins to rhino/occ backends) so these might have to also be implemented as pure python, compas based, types. keep a nice separation of those if you end up implementing them and follow similar interfaces as there are in the COMPAS wrappers.
>
> Also, although we're pure python, numpy and scipy are both dependencies of COMPAS so they can and should be used where this would lead to improved performance.
>
> Finally, please also document the prompts I give you in a rolling prompt log file in the repository. GO!

**Result:** (in progress)

# Next prompts:

## Convert OCC example scripts to compas_brep examples

## serialization and deserialization of Breps to/from JSON

## documentation
zensical
API reference
Developer guide:

    imagine I'm a developer who vibe-coded this whole thing in a couple hours and now has to maintain it for the next couple years. I have a basic understanding of Breps but I don't know much about the implementation details. I want to be able to understand the codebase and make changes to it without breaking things. I also want to be able to add new features and functionality as needed. I want to be able to debug issues that come up and fix them quickly. I want to be able to write tests for new features and bug fixes. I want to be able to understand the architecture of the codebase and how the different components interact with each other. 

## dev tools

Add bump-my-version, pre-commit hooks, CI with github actions, code coverage, etc.

## Performance benchmarking and optimization 

Evaluate the performance of the current implementation on a variety of test cases (use compas occ as the baseline). Identify bottlenecks and optimize critical sections of the code using numpy, scipy.

Where this could be highly beneficial, consider further optimizations such as extracting some algorithms into c-extensions with nanobind or use just-in-time compilation with numba.