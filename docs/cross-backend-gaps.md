# Cross-backend exchange gaps

Rhino and OCC agree on Brep *topology* (vertices, edges, faces, loops, trims) but
disagree on the low-level rules each kernel enforces when rebuilding one from the
[exchange document](https://github.com/gramaziokohler/compas_brep/blob/main/.agents/adr/0001-native-json-brep-exchange.md).
This page catalogs the gaps found so far, one per kernel disagreement, with what
compas_brep does about each.

Each gap follows the same shape: the document is silent on some detail neither
kernel's *native* API forces you to think about, the two kernels default to
different answers, and a document written by one and read by the other lands on
the wrong side of that default.

## Orientation is applied once, in the trim's own space

A face's `is_reversed` flag says its stored surface faces the wrong way. A trim's
`is_reversed` flag says it runs against its edge. The document defines both **in
the face's own, unflipped parameter space** — so a reader applies `is_reversed`
to the *face* and reads every trim as-is, once.

```mermaid
flowchart LR
    subgraph correct["one flip, applied once"]
        direction LR
        A1["trim.is_reversed<br/>(as written)"] --> B1["reader"]
        C1["face.is_reversed"] --> B1
        B1 --> D1["correctly oriented face"]
    end
```

Both backends had a writer or a reader that quietly composed the two flags
together, so the same orientation got applied twice:

- **OCC writer.** Explored a face's wires *through* the face itself. A `REVERSED`
  face composes its flag into every trim OCC hands back, so the writer recorded
  already-composed values. Fixed by exploring a `FORWARD`-oriented copy of the
  face instead — [`conversion.py:804`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/backend/occ/conversion.py#L804).
- **Rhino reader.** Reversed the trim loop *and* XOR'd every trim against
  `face.is_reversed` before calling `Trims.Add`, on top of `add_face` already
  setting `OrientationIsReversed`. Fixed by reading trims exactly as the document
  gives them — [`conversion.py:1217`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/backend/rhino/conversion.py#L1217).

**Symptom:** a blind hole round-tripped into a bump — volume went *up* instead of
down (981.9 → 1018.1) — because a reversed cylinder wall came back inside out.
Wrong by a plausible-looking number, so it passed any tolerance check on volume
alone; only `is_valid` (Rhino) or `BRepCheck_Analyzer` (OCC) caught it.

**Status:** fixed on both backends.

## A mirrored surface reverses the wire, not just the normal

OCC gives some rebuilt analytic surfaces (cylinder, sphere, cone, torus) a
left-handed placement. Straightening that mirrors the surface's `u` — which
reverses the *winding* of every loop on it, not just the surface normal.

```mermaid
flowchart LR
    M["mirror u<br/>(straighten placement)"] --> N["surface normal flips<br/>(is_reversed handles this)"]
    M --> W["wire winding flips<br/>(nothing handled this)"]
```

The code absorbed the normal flip into `is_reversed` but never turned the wire
around to match, so a loop wound clockwise in the mirrored space — bounding the
*outside* of the patch instead of the inside.

**Symptom:** every corner patch of a filleted box rebuilt inside out — reported
as a negative face area and `BRepCheck_BadOrientationOfSubshape`, while the
volume still integrated to the right number (integration over the wrong-signed
side of a *closed* patch still converges). This is why it survived as a
[known `xfail`](https://github.com/gramaziokohler/compas_brep/blob/main/tests/test_exchange_fixtures.py)
rather than being caught as a bug.

**Status:** fixed — the wire is reversed and every trim's `is_reversed` flipped
alongside the normal correction, [`conversion.py:850`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/backend/occ/conversion.py#L850).

## A pcurve is only valid on its edge's own interval

The document writes a trim's 2D pcurve over its **edge curve's** parameter
interval. If a rebuild reparameterizes the edge curve — moves where its `t=0`
is, or how far it runs — every pcurve written over the old interval is now being
evaluated against parameters the curve doesn't answer to anymore.

```mermaid
flowchart LR
    D["document: pcurve over edge's interval [t0, t1]"] --> R["rebuild"]
    R --> E2["edge curve rebuilt on a DIFFERENT interval"]
    E2 -.->|"pcurve still evaluated on old [t0, t1]"| G["pcurve lands off its own edge"]
```

Three kernel behaviors reparameterize an edge without telling the caller:

| Curve | Rebuild moves it to | Reference |
|---|---|---|
| `line` | `[0, length]` — a line stores only its endpoints | [`exchange.py`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/exchange.py) |
| periodic conic (`circle`, `ellipse`) | `[0, 2π)` — [`BRepBuilderAPI_MakeEdge`](https://dev.opencascade.org/doc/refman/html/class_b_rep_builder_a_p_i___make_edge.html) silently discards whole turns | [`conic_parameter_shift`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/exchange.py#L254) |
| conic with a **decreasing** interval | rejected outright — a NURBS knot vector cannot decrease | [`canonical_conic_interval`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/exchange.py#L216) |

**Symptoms, by row:**

1. A boolean leaves a cylinder's seam on e.g. `[5, 15]`; the reader rebuilds the
   line over `[0, 10]`. The seam's pcurve sits `t0` away from its own edge →
   `BRepCheck_InvalidRange`, unorientable face, broken wire on every full-turn
   cylindrical face surviving a boolean.
2. An OCC ellipse handed over on `[6.96, 11.00]` (past one turn) comes back on
   `[0.67, 4.71]`. The old pcurve is evaluated by extrapolation — worst observed
   gap over **1.7** units on a curve of radius ~1.
3. Rhino reports a scaled cylinder's elliptical rim running *clockwise*:
   `[π/2, −3π/2]`. Written straight out, that produces a **decreasing** NURBS
   knot vector — not a backwards curve, an unbuildable one. OCC rejects the
   whole document: `BSpline curve: Knots interval values too close`.

**Status:** fixed for all three. The document's rule is stated once — an edge's
interval always **increases**, and a writer or reader that reparameterizes an
edge shifts every pcurve on it by the same amount:

```mermaid
flowchart TD
    subgraph write["writing"]
        WC["conic traversed clockwise?"] -->|yes| WM["re-express in mirrored frame<br/>same curve, forwards interval<br/>canonical_conic_interval()"]
        WC -->|no| WOK["write as-is"]
    end
    subgraph read["reading"]
        RC["edge rebuild moves t0?"] -->|yes| RS["shift every pcurve on this edge<br/>by the same amount<br/>conic_parameter_shift() / shift_pcurve_parameters()"]
        RC -->|no| ROK["read as-is"]
    end
```

Row 3's fix re-expresses the same conic in a mirrored frame rather than reversing
the edge (which would strand every trim's `is_reversed`):

```
centre + a·cos(−t)·x + b·sin(−t)·(−y)  ==  centre + a·cos(t)·x + b·sin(t)·y
```

— same points, same direction of travel, only the frame and the interval turn
around. Verified to `0.000` deviation over the edge in
[`test_exchange_reversed_faces.py`](https://github.com/gramaziokohler/compas_brep/blob/main/tests/test_exchange_reversed_faces.py).

## Rhino tolerates pcurve drift OCC does not

A pcurve is an *approximation* to Rhino — accurate to the trim's own stated
tolerance, with the 3D edge curve as ground truth. OCC requires the two to agree
within the edge's tolerance and asserts it explicitly
([`SameParameter`](https://dev.opencascade.org/doc/refman/html/class_b_rep_lib.html)) —
a document that doesn't hold that agreement produces a shape OCC itself calls
invalid.

A straight (degree-1) pcurve for a `circle`/`arc` edge is only *exact* when the
surface's own `u` is linear in angle — true for OCC's analytic cylinder. Rotate
that cylinder in Rhino and its wall degrades to a rational NURBS, whose `u` is
no longer linear in angle: the straight pcurve now misses its own circular edge
by ~2×10⁻² against a tolerance of 10⁻⁶ — four orders of magnitude out, agreeing
only at span endpoints and midpoints (which is why naive sampling misses it).

**Symptom:** the cutter Brep was invalid **the moment OCC read it** — and a
boolean run against it anyway returned a result whose damage only surfaced two
process-hops later, in Rhino, as an unrelated-looking `Brep reconstruction
failed`.

**Status:** fixed — every OCC rebuild now calls
[`BRepLib.SameParameter_s`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/backend/occ/conversion.py#L995),
the reconciliation every OCC importer runs on foreign geometry, then checks
`BRepCheck_Analyzer` and **raises `BrepInvalidError` if the kernel still calls
its own rebuild invalid** — [`conversion.py:1004`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/backend/occ/conversion.py#L1004).

This matters beyond fixing the drift itself: compas_brep performs no geometry of
its own, it only asks a kernel to build one. So the moment a kernel hands back
something it won't call valid is the moment to stop — not the next operation
that happens to trip over it. A boolean that consumed a broken operand and
returned a broken result was, before this, indistinguishable from one that
worked.

## Not handled: 3D wire closure vs. 2D loop closure

OCC's own boolean operations can produce a face whose wire closes correctly in
**3D** but whose trims leave a small gap in **2D** parameter space (observed:
~5×10⁻⁷, itself within OCC's own tolerance). OCC calls this valid. Rhino's
`ON_BrepLoop::IsValid` requires trims to close in 2D and rejects it.

```mermaid
flowchart LR
    subgraph occ["OCC: valid"]
        direction LR
        A["wire closes in 3D"] -.->|"tiny 2D gap, within OCC's own tolerance"| B["pcurve doesn't quite\nclose in 2D"]
    end
    occ -->|"exchanged as-is"| rhino
    subgraph rhino["Rhino: rejected"]
        C["ON_BrepLoop.IsValid()\nrequires 2D closure"]
    end
```

This is a genuine disagreement between what each kernel is willing to call
"valid," not a bug in either writer. Things tried and rejected:

- `Brep.Repair()` in the Rhino builder closes the gap, but **masks real
  corruption** too — a cylinder whose axis was deliberately displaced by 3 units
  still "successfully" rebuilds under `Repair`. Given compas_brep raises on an
  invalid rebuild everywhere else (see above), silently repairing here would be
  inconsistent.
- Rhino's declared trim/edge tolerances make no difference — `ON_Brep::IsValid`'s
  2D check isn't tolerance-driven.
- OCC's own [`ShapeFix_Wire::FixGaps2d`](https://dev.opencascade.org/doc/refman/html/class_shape_fix___wire.html)
  reports touching the wire but doesn't close a gap that small — OCC considers
  it within tolerance already.

**Status:** unresolved. Currently the Rhino rebuild fails with a
`Brep reconstruction failed!` naming the bad loop — visible, not silent, but not
fixed either. Closing the gap ourselves would mean compas_brep doing geometry
work neither kernel considers necessary.

## Why not just use STEP?

STEP round-trips Breps between both kernels already (`Brep.to_step` /
`Brep.from_step`), so it's fair to ask whether it sidesteps all of the above.
Mostly it does — and it still isn't the right exchange path here.

Measured against the entities OCC actually writes for a box with a cylindrical
channel:

| Gap above | In STEP? | Why |
|---|---|---|
| Orientation applied twice | possible | Same layered flags — [`advanced_face`](http://www.steptools.com/stds/step/IR_final/part42/)`.same_sense`, `oriented_edge.orientation`, `edge_curve.same_sense`. Same ambiguity, but ISO 10303 pins how they compose, and you inherit a mature translator's reading instead of writing one. |
| Mirrored `u` | **impossible** | `axis2_placement_3d` stores only `axis` and `ref_direction`; y is derived as their cross product, so a placement is right-handed by construction. The kernel does the mirror when writing. |
| Pcurve interval reparameterized | **impossible** | STEP writes **no parameter intervals on edges**. See below. |
| Pcurve drift (`SameParameter`) | same problem, but named | STEP carries pcurves *and* declares which representation wins: `surface_curve('',#27,(#31,#43),.PCURVE_S1.)`. A reader knows what to trust and what to recompute. |
| 3D vs 2D loop closure | not addressed | A kernel-validity question, not a format one. STEP declares a global tolerance (`uncertainty_measure_with_unit(1.E-07)`) but doesn't mandate 2D closure. |

The third row is the interesting one. STEP delimits an edge by its **vertices**,
never by a parameter range — a real STEP file for the shape above contains zero
`trimmed_curve` entities:

```mermaid
flowchart TD
    subgraph step["STEP: edge = two vertices"]
        S1["edge_curve('', v_start, v_end, geometry, same_sense)"] --> S2["reader recomputes<br/>parameters by projecting<br/>the vertices onto the curve"]
    end
    subgraph json["exchange document: edge = curve + interval"]
        J1["curve + domain [t0, t1]"] --> J2["reader must rebuild the curve<br/>on that same interval<br/>-- or every pcurve on it moves"]
    end
```

So the whole family of "the interval moved and the pcurve didn't" simply cannot
be expressed in STEP. Two more measurements, both of which favour STEP:

- **Analytic surfaces survive.** The channel came back as
  `{Plane: 6, CylindricalSurface: 1}` — not a NURBS approximation.
- **Tolerances survive better than ours.** Source `1e-7 .. 1e-7` → after STEP
  `1e-7 .. 1e-7`, but after a compas_brep JSON round-trip `1e-7 .. 1e-6`. Our
  rebuild loosens one edge tenfold; STEP's did not.

### So why is the JSON document still the exchange path?

1. **Rhino's STEP import needs the UI thread and opens a modal dialog.** It goes
   through `RhinoDoc.ActiveDoc.ReadFile`
   ([`backend/rhino/io.py`](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/backend/rhino/io.py)).
   Anything headless — a worker, a solver loop, a Grasshopper component ticking
   on a timer — blocks on a dialog nobody is there to dismiss.
2. **Translators heal on import, which hides problems.** STEP readers run repair
   pipelines ([OCC's STEP translator](https://dev.opencascade.org/doc/overview/html/occt_user_guides__step.html)
   is explicit about this). That turns errors into silent geometry changes — the
   opposite of failing where the problem was caused. The `BrepInvalidError` this
   package raises on an invalid rebuild would simply never fire.
3. **You control neither the fidelity nor the failure modes** — you would be
   debugging two translators you do not own instead of one format you do. This is
   [ADR-0001](https://github.com/gramaziokohler/compas_brep/blob/main/.agents/adr/0001-native-json-brep-exchange.md)'s
   original argument, and it still holds.

!!! note "Scope of these measurements"

    The OCC→STEP→OCC figures above are measured. The claims about Rhino's STEP
    *import* come from reading that code path (and from the dialog it opens), not
    from measured geometry — the dialog is exactly what makes the round trip
    hard to automate.

`to_step` / `from_step` remain the right tool for what they are for: exchanging
geometry with third-party CAD, interactively, where a dialog is fine and a
translator's healing is welcome.
