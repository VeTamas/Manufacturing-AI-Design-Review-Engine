#!/usr/bin/env python3
"""Smoke test: run the CLI pipeline on a known golden STEP path (if available)."""
from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Golden STEP paths to try (first existing wins)
GOLDEN_STEP_CANDIDATES = [
    project_root / "tests" / "golden" / "parts" / "cnc" / "CNC1.step",
    project_root / "tests" / "golden" / "parts" / "cnc" / "CNC2.step",
    project_root / "tests" / "golden" / "parts" / "sheetmetal" / "SM1.STEP",
    project_root / "tests" / "golden" / "parts" / "edge" / "EDGE2.STEP",
    project_root / "tests" / "golden" / "parts" / "extrusion" / "extrusion1.step",
]


def test_step_cli_smoke() -> bool:
    """Run run_pipeline on a known STEP; assert state has process_recommendation and report.
    Returns True if passed, False if skipped."""
    step_path = None
    for p in GOLDEN_STEP_CANDIDATES:
        if p.exists():
            step_path = p
            break
    if step_path is None:
        print("SKIP: No golden STEP file found")
        return False

    from scripts.run_step_cli import run_pipeline

    state = run_pipeline(step_path=str(step_path))
    assert isinstance(state, dict), "run_pipeline must return a dict"
    proc_rec = state.get("process_recommendation") or state.get("process_selection")
    assert proc_rec is not None or "process_recommendation" in str(state.keys()), (
        "state must include process recommendation"
    )
    report = state.get("report_markdown", "")
    assert isinstance(report, str), "state must include report_markdown string"
    return True


if __name__ == "__main__":
    try:
        ok = test_step_cli_smoke()
        if ok:
            print("PASS: step CLI smoke test")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)
