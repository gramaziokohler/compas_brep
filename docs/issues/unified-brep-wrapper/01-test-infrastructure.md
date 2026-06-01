## Parent

../../prd/unified-brep-wrapper.md

## What to build

Add pytest infrastructure so the test suite runs cleanly in any environment — with or without a backend installed — and so CI can run the OCC tests automatically on every push.

Add a `conftest.py` that registers `occ` and `rhino` pytest marks and applies a skip condition to each: `occ` tests are skipped when `OCP` is not importable; `rhino` tests are skipped when `rhinoinside` is not importable. Update all existing tests to carry `@pytest.mark.occ`. No tests should fail due to a missing backend — they should skip.

Add a GitHub Actions workflow that installs `compas_brep[occ]` and runs `pytest -m occ` on every push and pull request.

## Acceptance criteria

- [x] `pytest` completes without errors on a machine with no backend installed (all backend tests skipped)
- [x] `pytest -m occ` runs the full OCC test suite when `OCP` is importable
- [x] `pytest -m rhino` is a valid invocation and skips all tests when `rhinoinside` is absent
- [x] All existing tests carry `@pytest.mark.occ`
- [x] GitHub Actions workflow file exists and runs `pytest -m occ` with OCC installed
- [ ] CI passes on a clean push

## Blocked by

None — can start immediately.
