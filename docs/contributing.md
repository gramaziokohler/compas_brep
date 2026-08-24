# Adding a new operation

A new `Brep` operation touches four places. `fillet` is used below as a
worked example — read [Architecture](architecture.md) first if the pieces
don't look familiar.

## 1. Declare the pluggable

Add a signature-only function to [operations.py](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/operations.py).
No logic — it exists so both backends have something to implement.

```python
@pluggable(category="brep-operations")
def brep_fillet(brep: Brep, radius: float, edges: list[int] | None = None) -> Brep:
    raise NotImplementedError
```

## 2. Register it in each backend

In `backend/occ/plugins.py` and `backend/rhino/plugins.py`, register a
`@plugin` with the same name, gated by what that backend requires:

```python
# backend/occ/plugins.py
@plugin(category="brep-operations", requires=["OCP"])
def brep_fillet(brep, radius, edges=None):
    from .operations import occ_fillet

    return occ_fillet(brep, radius, edges)
```

```python
# backend/rhino/plugins.py
@plugin(category="brep-operations", requires=["Rhino"])
def brep_fillet(brep, radius, edges=None):
    from .operations import rhino_fillet

    return rhino_fillet(brep, radius, edges)
```

## 3. Implement it, once per backend

The real logic goes in `backend/occ/operations.py` and
`backend/rhino/operations.py` (or `factories.py` / `queries.py`, depending
on what the operation does), written directly against the native kernel:

```python
# backend/occ/operations.py
def occ_fillet(brep: Brep, radius: float, edges: list[int] | None = None) -> Brep:
    """Fillet edges of a Brep. If edges is None, fillet all edges."""
    shape = brep_to_occ(brep)
    fillet = BRepFilletAPI_MakeFillet(shape)
    ...
```

Both implementations must produce an equivalent result for the same input —
that's the whole point of having one `Brep` API. They don't need to share
code; OCC and Rhino calls look nothing alike.

## 4. Expose it on `Brep`

In [brep.py](https://github.com/gramaziokohler/compas_brep/blob/main/src/compas_brep/brep.py),
add the public method. It does nothing but call the pluggable:

```python
def filleted(self, radius: float, edges: list[int] | None = None) -> Brep:
    """Return a filleted copy of this Brep."""
    return brep_fillet(self, radius, edges)
```

If the operation should also have an in-place form, follow the existing
`x()` / `xed()` pattern (e.g. `fillet()` calls `filleted()` and replaces
`self` with the result).

## 5. Test it against both backends

Write one test per backend, marked accordingly:

```python
@pytest.mark.occ
def test_fillet_occ():
    ...

@pytest.mark.rhino
def test_fillet_rhino():
    ...
```

`occ` tests run on CI. `rhino` tests are skipped by default (`-m 'not
rhino'` in `pyproject.toml`) and only run locally, on a machine with a Rhino
license. Run the OCC suite yourself before committing — see
[Installation](installation.md).

If the operation changes what gets serialized (a new surface or curve type,
for instance), it also needs a round-trip test through the
[exchange format](architecture.md#exchange-format) — both backends must be
able to read what either one writes.
