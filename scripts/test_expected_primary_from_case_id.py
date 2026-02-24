#!/usr/bin/env python3
"""Sanity test for expected_primary_from_case_id (no pipeline, no network)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

_runner = project_root / "scripts" / "run_golden_tests.py"
_spec = importlib.util.spec_from_file_location("run_golden_tests", _runner)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
expected_primary_from_case_id = _mod.expected_primary_from_case_id
_auto_display_id = _mod._auto_display_id
_auto_has_geometry_evidence = _mod._auto_has_geometry_evidence


def main() -> int:
    failed = 0

    # No duplicate _auto suffix
    for case_id, want in [
        ("edge2_extrusion", "edge2_extrusion_auto"),
        ("edge2_extrusion_auto", "edge2_extrusion_auto"),
        ("cnc1_bins_steel_small", "cnc1_bins_steel_small_auto"),
        ("unknown", "unknown_auto"),
    ]:
        got = _auto_display_id(case_id)
        if got != want:
            print(f"FAIL _auto_display_id({case_id!r}) -> expected {want!r}, got {got!r}")
            failed += 1
        else:
            print(f"OK   _auto_display_id({case_id!r}) -> {got!r}")
    # Geometry evidence: no STEP/cad/ext => False for turning/extrusion skip
    case_no_step = {"case_id": "turning1_bins_steel", "step_filename": "nonexistent.step"}
    result_no_evidence = {"cad_lite_status": "none", "extrusion_lite_status": "none"}
    if _auto_has_geometry_evidence(case_no_step, result_no_evidence):
        print("FAIL _auto_has_geometry_evidence(no step/cad/ext) should be False")
        failed += 1
    else:
        print("OK   _auto_has_geometry_evidence(no evidence) -> False")
    result_with_cad = {"cad_lite_status": "ok", "extrusion_lite_status": "none"}
    if not _auto_has_geometry_evidence(case_no_step, result_with_cad):
        print("FAIL _auto_has_geometry_evidence(cad_ok) should be True")
        failed += 1
    else:
        print("OK   _auto_has_geometry_evidence(cad_ok) -> True")

    tests = [
        ("cnc1_bins_steel_small", "CNC"),
        ("sm1_bins_steel_small", "SHEET_METAL"),
        ("turning1_bins_steel", "CNC_TURNING"),
        ("cnc_turning2_bins_template", "CNC_TURNING"),
        ("extrusion1_bins_aluminum", "EXTRUSION"),
        ("im1_bins_plastic_high", "INJECTION_MOLDING"),
        ("edge1_am", "AM"),
        ("edge2_extrusion", "EXTRUSION"),
        ("edge2_extrusion_auto", "EXTRUSION"),
        ("edge4_impeller_cnc", "CNC"),
        ("edge5_bracket_ambiguous", None),
        ("edge1_bins_template", None),
    ]
    failed = 0
    for case_id, expected in tests:
        got = expected_primary_from_case_id(case_id)
        if got != expected:
            print(f"FAIL: {case_id} -> expected {expected!r}, got {got!r}")
            failed += 1
        else:
            print(f"OK:   {case_id} -> {got!r}")
    if failed:
        print(f"\n{failed} failure(s)")
        return 1
    print("\nAll mapping checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
