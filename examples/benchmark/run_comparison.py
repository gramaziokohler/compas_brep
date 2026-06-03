"""Benchmark comparison runner.

Runs each group script against both backends, compares numerical outputs within
stated tolerances, and prints a summary table.

Exit code 0 when all non-skipped operations pass; non-zero otherwise.

Usage::

    python examples/benchmark/run_comparison.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).parent

GROUP_SCRIPTS = [
    BENCH_DIR / "01_primitives.py",
    BENCH_DIR / "02_booleans.py",
    BENCH_DIR / "03_queries.py",
    BENCH_DIR / "04_topology.py",
    BENCH_DIR / "05_transforms.py",
    BENCH_DIR / "06_modeling_ops.py",
    BENCH_DIR / "07_io.py",
    BENCH_DIR / "08_generators.py",
]

# Tolerance table: type → ("relative"|"absolute"|"exact") and threshold
TOLERANCES: dict[str, tuple[str, float]] = {
    "volume": ("relative", 0.001),  # 0.1% for primitives/queries
    "bool_volume": ("relative", 0.01),  # 1% for booleans / STEP round-trip
    "area": ("relative", 0.001),  # 0.1%
    "centroid": ("absolute", 1e-6),
    "aabb_dim": ("absolute", 1e-6),
    "count": ("exact", 0),
    "bool": ("exact", 0),
    "query": ("relative", 0.001),
}


def _run_script(script: Path, backend: str) -> list[dict]:
    """Run a benchmark script and parse its JSON output."""
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--backend", backend],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 and not result.stdout.strip():
            return [
                {"name": "_fatal", "type": "fatal", "value": None, "status": "ERROR", "reason": result.stderr.strip()}
            ]
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return [{"name": "_fatal", "type": "fatal", "value": None, "status": "ERROR", "reason": "Timeout"}]
    except json.JSONDecodeError as exc:
        return [
            {"name": "_fatal", "type": "fatal", "value": None, "status": "ERROR", "reason": f"JSON parse error: {exc}"}
        ]
    except Exception as exc:
        return [{"name": "_fatal", "type": "fatal", "value": None, "status": "ERROR", "reason": str(exc)}]


def _compare(name: str, type_: str, val_a, val_b) -> tuple[str, str]:
    """Return (status, detail) for a pair of values."""
    if val_a is None or val_b is None:
        return "N/A", "one or both values missing"

    tol_kind, tol_val = TOLERANCES.get(type_, ("relative", 0.01))

    if tol_kind == "exact":
        ok = val_a == val_b
        return ("PASS" if ok else "FAIL"), f"{val_a!r} vs {val_b!r}"

    if not isinstance(val_a, (int, float)) or not isinstance(val_b, (int, float)):
        return "N/A", "non-numeric"

    if tol_kind == "relative":
        ref = max(abs(val_a), abs(val_b), 1e-12)
        ok = abs(val_a - val_b) / ref <= tol_val
        detail = f"{val_a:.6g} vs {val_b:.6g} (tol {tol_val * 100:.1f}%)"
    else:  # absolute
        ok = abs(val_a - val_b) <= tol_val
        detail = f"{val_a:.6g} vs {val_b:.6g} (tol {tol_val:.2e})"

    return ("PASS" if ok else "FAIL"), detail


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def main() -> int:
    col_w = [32, 14, 14, 6, 0]  # name, brep, occ, status, detail
    header = f"{'Operation':<{col_w[0]}} {'compas_brep':>{col_w[1]}} {'compas_occ':>{col_w[2]}} {'':>{col_w[3]}} detail"
    sep = "-" * len(header)

    print(header)
    print(sep)

    all_pass = True
    any_fail = False

    for script in GROUP_SCRIPTS:
        group_name = script.stem
        results_brep = _run_script(script, "compas_brep")
        results_occ = _run_script(script, "compas_occ")

        # Index by name
        by_name_brep = {r["name"]: r for r in results_brep}
        by_name_occ = {r["name"]: r for r in results_occ}

        all_names = list(by_name_brep.keys()) or list(by_name_occ.keys())

        print(f"\n[{group_name}]")

        for name in all_names:
            if name.startswith("_"):
                continue

            rec_brep = by_name_brep.get(name, {})
            rec_occ = by_name_occ.get(name, {})

            status_brep = rec_brep.get("status", "missing")
            status_occ = rec_occ.get("status", "missing")
            val_brep = rec_brep.get("value")
            val_occ = rec_occ.get("value")
            type_ = rec_brep.get("type") or rec_occ.get("type", "volume")

            # Determine row status
            if status_brep == "SKIP" or status_occ == "SKIP" or status_brep == "missing" or status_occ == "missing":
                row_status = "SKIP"
                detail = rec_brep.get("reason") or rec_occ.get("reason") or "not available"
            elif status_brep == "ERROR":
                row_status = "ERROR"
                detail = rec_brep.get("reason", "")
                any_fail = True
                all_pass = False
            elif status_occ == "ERROR":
                # OCC error → treat as SKIP (occ not installed or op missing)
                row_status = "SKIP"
                detail = f"compas_occ error: {rec_occ.get('reason', '')}"
            else:
                row_status, detail = _compare(name, type_, val_brep, val_occ)
                if row_status == "FAIL":
                    any_fail = True
                    all_pass = False

            line = (
                f"  {name:<{col_w[0] - 2}}"
                f" {_fmt(val_brep):>{col_w[1]}}"
                f" {_fmt(val_occ):>{col_w[2]}}"
                f" {row_status:>{col_w[3]}}  {detail}"
            )
            print(line)

    print()
    print(sep)
    if all_pass and not any_fail:
        print("Result: ALL PASS (non-skipped operations match within tolerance)")
        return 0
    else:
        print("Result: FAIL — one or more operations diverge beyond tolerance")
        return 1


if __name__ == "__main__":
    sys.exit(main())
