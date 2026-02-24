#!/usr/bin/env python3
"""
Regression test: verify offline explain fallback works without internet.
Ensures pipeline does not crash when CNCR_OFFLINE=1 or connection fails.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Force offline mode
os.environ["CNCR_OFFLINE"] = "1"
# Remove API key to ensure offline fallback
if "OPENAI_API_KEY" in os.environ:
    del os.environ["OPENAI_API_KEY"]


def test_offline_explain_fallback():
    """Test that pipeline runs offline without crashing."""
    from scripts.run_step_cli import run_pipeline
    
    step_path = project_root / "tests" / "golden" / "parts" / "edge" / "EDGE2.STEP"
    if not step_path.exists():
        print(f"ERROR: Test file not found: {step_path}", file=sys.stderr)
        return 1
    
    print(f"Running pipeline offline on {step_path.name}...")
    try:
        state = run_pipeline(
            step_path=str(step_path),
            process="CNC",
            material="Steel",
            production_volume="Small batch",
            load_type="Static",
            tolerance_criticality="Medium",
            rag_enabled=False,
            numeric=False,
        )
    except Exception as e:
        print(f"ERROR: Pipeline crashed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    # Check for fatal errors
    if state.get("error"):
        err = state.get("error")
        err_type = type(err).__name__ if not isinstance(err, dict) else err.get("type", "Unknown")
        err_msg = str(err) if not isinstance(err, dict) else err.get("message", "Unknown error")
        print(f"ERROR: Pipeline returned error: {err_type}: {err_msg}", file=sys.stderr)
        return 1
    
    # Verify report_markdown exists and is non-empty
    report_markdown = state.get("report_markdown", "")
    if not report_markdown or not isinstance(report_markdown, str) or len(report_markdown.strip()) < 50:
        print(f"ERROR: report_markdown missing or too short (len={len(report_markdown)})", file=sys.stderr)
        return 1
    
    # Verify trace contains offline fallback message
    trace = state.get("trace", [])
    trace_str = " ".join(str(t) for t in trace).lower()
    if "offline fallback" not in trace_str and "offline" not in trace_str:
        print(f"WARNING: Trace does not mention offline fallback: {trace}", file=sys.stderr)
        # Not a failure, but worth noting
    
    print("OK Pipeline completed successfully offline")
    print(f"OK Report generated ({len(report_markdown)} chars)")
    print(f"OK Trace: {len(trace)} items")
    if "offline" in trace_str:
        print("OK Offline fallback confirmed in trace")
    
    return 0


if __name__ == "__main__":
    sys.exit(test_offline_explain_fallback())
