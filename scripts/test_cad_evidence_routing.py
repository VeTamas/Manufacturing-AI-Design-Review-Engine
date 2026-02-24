#!/usr/bin/env python3
"""Tests for CAD evidence routing: cad_uploaded, cad_status, report, diagnostics."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))


def test_cad_presence_helpers():
    """Unit tests for cad_presence module."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.geometry.cad_presence import (
        cad_uploaded,
        cad_analysis_status,
        cad_evidence_available,
        cad_evidence_keys,
    )

    def mk_state(**kw):
        base = {
            "inputs": Inputs(
                process="CNC",
                material="Aluminum",
                production_volume="Proto",
                load_type="Static",
                tolerance_criticality="Medium",
            ),
            "part_summary": PartSummary(
                part_size="Small",
                min_internal_radius="Medium",
                min_wall_thickness="Medium",
                hole_depth_class="None",
                pocket_aspect_class="OK",
                feature_variety="Low",
                accessibility_risk="Low",
                has_clamping_faces=True,
            ),
        }
        base.update(kw)
        return base

    # Case 1: step uploaded, provider ok, metrics present
    s1 = mk_state(
        step_path="/tmp/part.step",
        part_metrics_provider="numeric_cnc_v1",
        part_metrics={
            "bounding_box_mm": [10, 20, 30],
            "volume_mm3": 6000,
            "surface_area_mm2": 2200,
        },
        part_metrics_evidence={"hole_count": 3},
    )
    assert cad_uploaded(s1) is True
    assert cad_analysis_status(s1) == "ok"
    assert cad_evidence_available(s1) is True
    assert "hole_count" in cad_evidence_keys(s1)

    # Case 2: step uploaded, provider timeout
    s2 = mk_state(
        step_path="/tmp/part.step",
        part_metrics_provider="numeric_cnc_v1_timeout",
    )
    assert cad_uploaded(s2) is True
    assert cad_analysis_status(s2) == "timeout"
    assert cad_evidence_available(s2) is False

    # Case 3: step uploaded, bins mode, no numeric
    s3 = mk_state(
        step_path="/tmp/part.step",
        part_summary_mode="bins",
        part_metrics_provider="cad_uploaded_no_numeric",
    )
    assert cad_uploaded(s3) is True
    assert cad_analysis_status(s3) == "none"
    assert cad_evidence_available(s3) is False

    # Case 4: no step_path
    s4 = mk_state()
    assert cad_uploaded(s4) is False
    assert cad_analysis_status(s4) == "none"
    assert cad_evidence_available(s4) is False

    print("PASS: cad_presence helpers")


def test_report_cad_section():
    """Report includes CAD uploaded/status/evidence lines; never 'No CAD' when uploaded."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.report import report_node

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Proto",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Small",
            min_internal_radius="Medium",
            min_wall_thickness="Medium",
            hole_depth_class="None",
            pocket_aspect_class="OK",
            feature_variety="Low",
            accessibility_risk="Low",
            has_clamping_faces=True,
        ),
        "step_path": "/tmp/part.step",
        "part_metrics_provider": "numeric_cnc_v1",
        "part_metrics": {
            "bounding_box_mm": [10, 20, 30],
            "volume_mm3": 6000,
            "surface_area_mm2": 2200,
        },
        "part_metrics_evidence": {"hole_count": 3},
        "findings": [],
        "actions": [],
        "assumptions": [],
    }
    result = report_node(state)
    report = result.get("report_markdown", "")
    assert "CAD uploaded: yes" in report
    assert "CAD analysis status: ok" in report
    assert "CAD evidence used in rules: yes" in report
    assert "No CAD" not in report
    print("PASS: report CAD section (ok case)")


def test_report_bins_mode_step_uploaded():
    """Bins mode + step uploaded: report must NOT say 'No CAD'."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.report import report_node

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Proto",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Small",
            min_internal_radius="Medium",
            min_wall_thickness="Medium",
            hole_depth_class="None",
            pocket_aspect_class="OK",
            feature_variety="Low",
            accessibility_risk="Low",
            has_clamping_faces=True,
        ),
        "step_path": "/tmp/part.step",
        "part_summary_mode": "bins",
        "part_metrics_provider": "cad_uploaded_no_numeric",
        "findings": [],
        "actions": [],
        "assumptions": [],
    }
    result = report_node(state)
    report = result.get("report_markdown", "")
    assert "CAD uploaded: yes" in report
    assert "CAD analysis status: none" in report
    assert "No CAD" not in report
    assert "No detailed CAD" not in report
    print("PASS: bins mode + step uploaded -> no 'No CAD'")


def test_report_timeout_case():
    """Step uploaded, provider timeout: cad_status timeout."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.report import report_node

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Proto",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Small",
            min_internal_radius="Medium",
            min_wall_thickness="Medium",
            hole_depth_class="None",
            pocket_aspect_class="OK",
            feature_variety="Low",
            accessibility_risk="Low",
            has_clamping_faces=True,
        ),
        "step_path": "/tmp/part.step",
        "part_metrics_provider": "numeric_cnc_v1_timeout",
        "findings": [],
        "actions": [],
        "assumptions": [],
    }
    result = report_node(state)
    report = result.get("report_markdown", "")
    assert "CAD uploaded: yes" in report
    assert "CAD analysis status: timeout" in report
    assert "No CAD" not in report
    print("PASS: timeout case -> cad_status timeout")


def test_run_sets_cad_uploaded_no_numeric():
    """run_agent sets part_metrics_provider=cad_uploaded_no_numeric when bins + step."""
    from agent.state import Inputs, PartSummary
    from agent.run import run_agent

    inputs = Inputs(
        process="CNC",
        material="Aluminum",
        production_volume="Proto",
        load_type="Static",
        tolerance_criticality="Medium",
    )
    part_summary = PartSummary(
        part_size="Small",
        min_internal_radius="Medium",
        min_wall_thickness="Medium",
        hole_depth_class="None",
        pocket_aspect_class="OK",
        feature_variety="Low",
        accessibility_risk="Low",
        has_clamping_faces=True,
    )
    out = run_agent(
        inputs,
        part_summary,
        rag_enabled=False,
        part_summary_mode="bins",
        step_path=__file__,  # use self as existing path
    )
    assert out.get("part_metrics_provider") == "cad_uploaded_no_numeric"
    assert out.get("step_path") == __file__
    print("PASS: run_agent sets cad_uploaded_no_numeric for bins + step")


def test_diagnostic_no_warn_when_evidence_used():
    """When part_metrics_evidence present and cad_status ok, diagnostic does NOT warn."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.rules import rules_node

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Proto",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Small",
            min_internal_radius="Medium",
            min_wall_thickness="Medium",
            hole_depth_class="None",
            pocket_aspect_class="OK",
            feature_variety="Low",
            accessibility_risk="Low",
            has_clamping_faces=True,
        ),
        "step_path": "/tmp/part.step",
        "part_metrics_provider": "numeric_cnc_v1",
        "part_metrics": {
            "bounding_box_mm": [10, 20, 30],
            "volume_mm3": 6000,
            "surface_area_mm2": 2200,
        },
        "part_metrics_evidence": {"hole_max_ld": 8.0, "hole_count": 2},
        "findings": [],
    }
    out = rules_node(state)
    trace = out.get("trace", [])
    assert any("rules: cad_uploaded=y" in t for t in trace)
    assert any("cad_status=ok" in t for t in trace)
    # Diagnostic should NOT fire when evidence_keys non-empty
    assert not any("cad_evidence_available_but_unused" in t for t in trace)
    print("PASS: diagnostic does not warn when evidence used")


if __name__ == "__main__":
    failures = []
    for name, fn in [
        ("test_cad_presence_helpers", test_cad_presence_helpers),
        ("test_report_cad_section", test_report_cad_section),
        ("test_report_bins_mode_step_uploaded", test_report_bins_mode_step_uploaded),
        ("test_report_timeout_case", test_report_timeout_case),
        ("test_run_sets_cad_uploaded_no_numeric", test_run_sets_cad_uploaded_no_numeric),
        ("test_diagnostic_no_warn_when_evidence_used", test_diagnostic_no_warn_when_evidence_used),
    ]:
        try:
            fn()
        except Exception as e:
            failures.append((name, e))
            print(f"FAIL: {name} - {e}")

    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print("\nAll CAD evidence routing tests passed.")
    sys.exit(0)
