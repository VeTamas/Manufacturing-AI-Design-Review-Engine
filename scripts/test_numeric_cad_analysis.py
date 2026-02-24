#!/usr/bin/env python3
"""Acceptance tests for Numeric CAD Analysis (Phase 1: CNC only)."""

import sys
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))


def test_1_cnc_bins_unchanged():
    """CNC + bins → unchanged output (no numeric section)."""
    from agent.state import Inputs, PartSummary, GraphState
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
        step_path=None,
    )
    report = out.get("report_markdown", "")
    assert "## Numeric CNC Geometry Analysis" not in report
    assert "part_metrics" not in out or out.get("part_metrics") is None
    print("PASS: CNC + bins -> unchanged output")


def test_2_cnc_numeric_includes_section():
    """CNC + numeric → report includes numeric CNC section (if STEP available)."""
    from agent.state import Inputs, PartSummary
    from agent.run import run_agent
    from agent.geometry.part_summary_provider import get_numeric_analyzer

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
    # No STEP file - numeric will fallback to bins, no section added
    out = run_agent(
        inputs,
        part_summary,
        rag_enabled=False,
        part_summary_mode="numeric",
        step_path=None,
    )
    # Without STEP, no part_metrics stored
    assert out.get("part_metrics") is None or out.get("part_metrics_provider") is None
    # Report should not have numeric section (no metrics)
    report = out.get("report_markdown", "")
    if out.get("part_metrics_provider", "").startswith("numeric_cnc"):
        assert "## Numeric CNC Geometry Analysis" in report
    else:
        assert "## Numeric CNC Geometry Analysis" not in report
    print("PASS: CNC + numeric (no STEP) -> no numeric section (expected)")


def test_3_mim_numeric_no_metrics():
    """MIM + numeric selected → bins used, no metrics stored."""
    from agent.state import Inputs, PartSummary
    from agent.run import run_agent
    from agent.geometry.part_summary_provider import get_numeric_analyzer

    assert get_numeric_analyzer("MIM") is None

    inputs = Inputs(
        process="MIM",
        material="Steel",
        production_volume="Production",
        load_type="Static",
        tolerance_criticality="High",
    )
    part_summary = PartSummary(
        part_size="Medium",
        min_internal_radius="Small",
        min_wall_thickness="Thin",
        hole_depth_class="Moderate",
        pocket_aspect_class="OK",
        feature_variety="Medium",
        accessibility_risk="Low",
        has_clamping_faces=False,
    )
    out = run_agent(
        inputs,
        part_summary,
        rag_enabled=False,
        part_summary_mode="numeric",
        step_path="/fake/step.stp",  # Would fail anyway, but analyzer returns None first
    )
    # MIM has no analyzer - no part_metrics
    assert out.get("part_metrics") is None
    assert out.get("part_metrics_provider") is None
    report = out.get("report_markdown", "")
    assert "## Numeric CNC Geometry Analysis" not in report
    print("PASS: MIM + numeric -> bins used, no metrics stored")


def test_4_compileall():
    """compileall OK."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "."],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    print("PASS: compileall OK")


def test_5_numeric_fallback_on_exception():
    """When analyzer.analyze raises, fallback to bins: part_metrics=None, provider=numeric_cnc_v1_failed."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.geometry.part_summary_provider import build_part_summary

    def _raise(_path):
        raise RuntimeError("simulated OCP failure")

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
        "part_summary_mode": "numeric",
        "step_path": __file__,  # use self as existing path
    }

    with patch("agent.geometry.analyzers.cnc_numeric_v1.analyze", side_effect=_raise):
        bins, delta = build_part_summary(state)

    assert delta.get("part_metrics") is None
    assert delta.get("part_metrics_provider") == "numeric_cnc_v1_failed"
    assert bins.part_size == "Small"
    print("PASS: exception fallback -> part_metrics=None, provider=numeric_cnc_v1_failed")


def test_6_cnc_numeric_adapter_thin_wall():
    """CNC numeric mode with min_wall_thickness_mm=0.8, thin_wall_flag=True: bins updated, DFM-N1 with evidence."""
    from agent.state import Inputs, PartSummary
    from agent.geometry.part_summary_provider import build_part_summary
    from agent.rulesets.cnc import run_cnc_rules

    def _mock_analyze(_path):
        return {
            "bounding_box_mm": [10.0, 15.0, 25.0],
            "volume_mm3": 3750.0,
            "surface_area_mm2": None,
            "min_wall_thickness_mm": 0.8,
            "min_internal_radius_mm": None,
            "thin_wall_flag": True,
            "tool_access_proxy": 0.4,
            "faces": 20,
            "edges": 30,
        }

    state = {
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
        "part_summary_mode": "numeric",
        "step_path": __file__,
    }

    with patch("agent.geometry.analyzers.cnc_numeric_v1.analyze", side_effect=_mock_analyze):
        _, delta = build_part_summary(state)

    assert delta.get("part_metrics_provider") == "numeric_cnc_v1"
    updated = delta.get("part_summary")
    assert updated is not None
    assert updated.min_wall_thickness == "Thin"
    ev = delta.get("part_metrics_evidence")
    assert ev is not None
    assert ev.get("min_wall_thickness_mm") == 0.8
    assert ev.get("thin_wall_flag") is True

    # Merge delta into state and run CNC rules
    state = {**state, **delta}
    out = run_cnc_rules(state)
    findings = out.get("findings", [])
    thin_finding = next((f for f in findings if f.id == "DFM-N1"), None)
    assert thin_finding is not None, "DFM-N1 (thin wall numeric) should appear"
    assert getattr(thin_finding, "evidence", None) is not None
    assert thin_finding.evidence.get("min_wall_thickness_mm") == 0.8
    assert thin_finding.evidence.get("thin_wall_flag") is True
    print("PASS: CNC numeric adapter thin wall -> bins updated, DFM-N1 with evidence")


def test_7_mim_numeric_no_adapter_no_evidence():
    """MIM numeric mode: adapter not applied, no part_metrics_evidence."""
    from agent.state import Inputs, PartSummary
    from agent.run import run_agent

    inputs = Inputs(
        process="MIM",
        material="Steel",
        production_volume="Production",
        load_type="Static",
        tolerance_criticality="High",
    )
    part_summary = PartSummary(
        part_size="Medium",
        min_internal_radius="Small",
        min_wall_thickness="Thin",
        hole_depth_class="Moderate",
        pocket_aspect_class="OK",
        feature_variety="Medium",
        accessibility_risk="Low",
        has_clamping_faces=False,
    )
    out = run_agent(
        inputs,
        part_summary,
        rag_enabled=False,
        part_summary_mode="numeric",
        step_path="/fake/step.stp",
    )
    assert out.get("part_metrics") is None
    assert out.get("part_metrics_provider") is None
    assert out.get("part_metrics_evidence") is None
    report = out.get("report_markdown", "")
    assert "DFM-N1" not in report
    assert "DFM-N2" not in report
    print("PASS: MIM numeric -> no adapter, no evidence")


def test_8_tool_access_proxy_guard():
    """When faces < CNC_ACCESS_MIN_FACES, adapter must NOT override accessibility_risk even if proxy suggests High."""
    from agent.state import Inputs, PartSummary
    from agent.geometry.part_summary_provider import build_part_summary
    from agent.geometry.cnc_numeric_adapter import CNC_ACCESS_MIN_FACES

    def _mock_analyze(_path):
        return {
            "bounding_box_mm": [10.0, 15.0, 25.0],
            "volume_mm3": 3750.0,
            "surface_area_mm2": None,
            "min_wall_thickness_mm": None,
            "min_internal_radius_mm": None,
            "thin_wall_flag": None,
            "tool_access_proxy": 0.85,  # Would map to High
            "faces": CNC_ACCESS_MIN_FACES - 1,  # Too few faces
            "edges": 10,
        }

    state = {
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
        "part_summary_mode": "numeric",
        "step_path": __file__,
    }

    with patch("agent.geometry.analyzers.cnc_numeric_v1.analyze", side_effect=_mock_analyze):
        _, delta = build_part_summary(state)

    updated = delta.get("part_summary")
    assert updated is not None
    assert updated.accessibility_risk == "Low", "accessibility_risk must NOT be overridden when faces < 20"
    assert delta.get("part_metrics_evidence") is not None
    print("PASS: tool_access_proxy guard -> accessibility_risk unchanged when faces < 20")


def test_9_numeric_fallback_on_timeout():
    """When analyzer.analyze raises TimeoutError, fallback: part_metrics=None, provider=numeric_cnc_v1_timeout."""
    from agent.state import Inputs, PartSummary
    from agent.geometry.part_summary_provider import build_part_summary

    def _timeout(_path):
        raise FuturesTimeoutError()

    state = {
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
        "part_summary_mode": "numeric",
        "step_path": __file__,
    }

    with patch("agent.geometry.analyzers.cnc_numeric_v1.analyze", side_effect=_timeout):
        bins, delta = build_part_summary(state)

    assert delta.get("part_metrics") is None
    assert delta.get("part_metrics_provider") == "numeric_cnc_v1_timeout"
    assert bins.part_size == "Small"
    print("PASS: timeout fallback -> part_metrics=None, provider=numeric_cnc_v1_timeout")


def test_10_mim_bins_regression():
    """MIM bins mode: ensure Thin/Small bins still work (regression test for non-CNC)."""
    from agent.state import Inputs, PartSummary
    from agent.run import run_agent

    inputs = Inputs(
        process="MIM",
        material="Steel",
        production_volume="Production",
        load_type="Static",
        tolerance_criticality="High",
    )
    part_summary = PartSummary(
        part_size="Small",
        min_internal_radius="Small",  # Legacy bin vocabulary
        min_wall_thickness="Thin",  # Legacy bin vocabulary
        hole_depth_class="Moderate",
        pocket_aspect_class="OK",
        feature_variety="High",
        accessibility_risk="Medium",
        has_clamping_faces=False,
    )
    out = run_agent(
        inputs,
        part_summary,
        rag_enabled=False,
        part_summary_mode="bins",
        step_path=None,
    )
    # Ensure no validation errors and bins unchanged
    assert out.get("error") is None
    assert out.get("part_summary") is not None
    assert out["part_summary"].min_wall_thickness == "Thin"
    assert out["part_summary"].min_internal_radius == "Small"
    report = out.get("report_markdown", "")
    assert "MIM" in report or "Metal Injection Molding" in report or len(out.get("findings", [])) > 0
    print("PASS: MIM bins regression -> Thin/Small bins work, no validation errors")


def test_11_report_numeric_formatting():
    """Report formats bounding_box_mm as AxBxC with 2 decimals, not raw list."""
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
        "part_metrics": {
            "bounding_box_mm": [206.123456, 50.291234, 258.987654],
            "volume_mm3": 2750000.12345,
            "surface_area_mm2": None,
            "tool_access_proxy": 0.1949,
            "faces": 25,
            "edges": 40,
        },
        "part_metrics_provider": "numeric_cnc_v1",
        "findings": [],
        "actions": [],
        "assumptions": [],
    }
    result = report_node(state)
    report = result.get("report_markdown", "")
    assert "## Numeric CNC Geometry Analysis" in report
    assert "bounding_box_mm: 206.12x50.29x258.99" in report or "bounding_box_mm: 206.12x50.29x258.99" in report.replace(" ", "")
    assert "[206" not in report  # No raw list repr
    assert "tool_access_proxy (lower is better): 0.19" in report or "tool_access_proxy (lower is better): 0.19" in report.replace(" ", "")
    print("PASS: report numeric formatting -> bounding_box_mm as AxBxC, tool_access_proxy direction clarified")


def test_13_cad_present_no_missing_cad():
    """Regression: step_path present + bins -> no 'No CAD model' / missing_cad in confidence."""
    from agent.state import Inputs, ConfidenceInputs, GraphState
    from agent.nodes.self_review import (
        _cad_is_present,
        _generate_deterministic_confidence_texts,
        _normalize_confidence,
    )

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Proto",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "step_path": "dummy.step",
        "part_summary_mode": "bins",
        "confidence_inputs": ConfidenceInputs(has_2d_drawing=False, step_scale_confirmed=True),
        "findings": [],
        "sources": [],
        "rag_enabled": False,
    }

    assert _cad_is_present(state) is True
    det = _generate_deterministic_confidence_texts(state)
    limitations = det.get("limitations", [])
    # Must NOT include "No CAD model" or "No detailed CAD geometry provided"
    assert not any(
        "No CAD" in lim or "No detailed CAD" in lim
        for lim in limitations
    ), f"limitations must not include No CAD when step_path present: {limitations}"

    # Simulate LLM output with missing_cad; _normalize_confidence should filter it
    parsed = {
        "llm_delta": 0.0,
        "llm_rationale": ["A.", "B.", "C."],
        "uncertainty_flags": ["missing_cad", "no_2d_drawing"],
    }
    base_score = 0.6
    conf, _ = _normalize_confidence(parsed, state, base_score)
    flags = conf.uncertainty_flags
    assert "missing_cad" not in [f.strip().lower() for f in flags], (
        f"missing_cad must be filtered when CAD present: {flags}"
    )
    print("PASS: step_path present + bins -> no No CAD / missing_cad in confidence")


def test_14_numeric_timeout_not_missing_cad():
    """Regression: step_path + numeric_cnc_v1_timeout -> missing_cad absent; numeric_analysis_timeout present."""
    from agent.state import Inputs, ConfidenceInputs, GraphState
    from agent.nodes.self_review import (
        _cad_is_present,
        _generate_deterministic_confidence_texts,
        _normalize_confidence,
    )

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Proto",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "step_path": "dummy.step",
        "part_summary_mode": "numeric",
        "part_metrics_provider": "numeric_cnc_v1_timeout",
        "confidence_inputs": ConfidenceInputs(has_2d_drawing=False, step_scale_confirmed=True),
        "findings": [],
        "sources": [],
        "rag_enabled": False,
    }

    assert _cad_is_present(state) is True
    det = _generate_deterministic_confidence_texts(state)
    limitations = det.get("limitations", [])
    # Must include "Numeric CNC analysis unavailable" and NOT "No CAD model"
    assert not any(
        "No CAD" in lim or "No detailed CAD" in lim
        for lim in limitations
    ), f"must not say No CAD when step_path + provider present: {limitations}"
    assert any(
        "Numeric" in lim and ("timeout" in lim.lower() or "error" in lim.lower())
        for lim in limitations
    ), f"must indicate numeric analysis unavailable: {limitations}"

    parsed = {
        "llm_delta": 0.0,
        "llm_rationale": ["A.", "B.", "C."],
        "uncertainty_flags": ["missing_cad"],  # LLM wrongly added missing_cad
    }
    base_score = 0.6
    conf, _ = _normalize_confidence(parsed, state, base_score)
    flags = conf.uncertainty_flags
    assert "missing_cad" not in [f.strip().lower() for f in flags]
    assert "numeric_analysis_timeout" in [f.strip().lower() for f in flags], (
        f"numeric_analysis_timeout must appear when provider=timeout: {flags}"
    )
    print("PASS: numeric timeout -> missing_cad absent, numeric_analysis_timeout present")


def test_15_dfm_nh1_hole_ld_triggers():
    """When part_metrics_evidence has hole_max_ld >= 6, DFM-NH1 triggers with evidence."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.rulesets.cnc import run_cnc_rules

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
        "part_metrics_evidence": {
            "hole_max_ld": 8.2,
            "hole_max_depth_mm": 41.0,
            "hole_diameters_mm": [5.0, 6.0],
        },
    }
    out = run_cnc_rules(state)
    findings = out.get("findings", [])
    nh1 = next((f for f in findings if f.id == "DFM-NH1"), None)
    assert nh1 is not None, "DFM-NH1 should trigger when hole_max_ld >= 6"
    assert nh1.evidence is not None
    assert nh1.evidence.get("hole_max_ld") == 8.2
    print("PASS: hole_max_ld=8.2 -> DFM-NH1 triggers with evidence")


def test_16_dfm_np1_pocket_aspect_triggers():
    """When part_metrics_evidence has pocket_max_aspect >= 4, DFM-NP1 triggers."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.rulesets.cnc import run_cnc_rules

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Proto",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Medium",
            min_internal_radius="Medium",
            min_wall_thickness="Medium",
            hole_depth_class="None",
            pocket_aspect_class="OK",
            feature_variety="Low",
            accessibility_risk="Low",
            has_clamping_faces=True,
        ),
        "part_metrics_evidence": {
            "pocket_max_aspect": 5.0,
            "pocket_max_depth_mm": 25.0,
            "pocket_count": 2,
        },
    }
    out = run_cnc_rules(state)
    findings = out.get("findings", [])
    np1 = next((f for f in findings if f.id == "DFM-NP1"), None)
    assert np1 is not None, "DFM-NP1 should trigger when pocket_max_aspect >= 4"
    assert np1.evidence is not None
    assert np1.evidence.get("pocket_max_aspect") == 5.0
    print("PASS: pocket_max_aspect=5.0 -> DFM-NP1 triggers")


def test_18_dfm_nh1_proposal_contains_evidence():
    """Phase 3: DFM-NH1 has proposal with hole_max_ld and <= 6."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.rulesets.cnc import run_cnc_rules

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
        "part_metrics_evidence": {"hole_max_ld": 8.2, "hole_max_depth_mm": 41.0},
    }
    out = run_cnc_rules(state)
    nh1 = next((f for f in out["findings"] if f.id == "DFM-NH1"), None)
    assert nh1 is not None
    assert nh1.proposal is not None
    assert "8.2" in nh1.proposal
    assert "<= 6" in nh1.proposal
    assert nh1.proposal_steps is not None
    assert len(nh1.proposal_steps) >= 1
    print("PASS: DFM-NH1 proposal contains 8.2 and <= 6")


def test_19_dfm_np1_proposal_contains_aspect():
    """Phase 3: DFM-NP1 has proposal mentioning pocket_max_aspect."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.rulesets.cnc import run_cnc_rules

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Proto",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Medium",
            min_internal_radius="Medium",
            min_wall_thickness="Medium",
            hole_depth_class="None",
            pocket_aspect_class="OK",
            feature_variety="Low",
            accessibility_risk="Low",
            has_clamping_faces=True,
        ),
        "part_metrics_evidence": {"pocket_max_aspect": 5.0, "pocket_count": 2},
    }
    out = run_cnc_rules(state)
    np1 = next((f for f in out["findings"] if f.id == "DFM-NP1"), None)
    assert np1 is not None
    assert np1.proposal is not None
    assert "5.0" in np1.proposal
    print("PASS: DFM-NP1 proposal mentions 5.0")


def test_21_report_detected_cnc_features_section():
    """Phase 4: Report renders 'Detected CNC features' when CNC+numeric mode."""
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
        "part_summary_mode": "numeric",
        "part_features": {},
        "part_metrics_provider": "numeric_cnc_v1",
        "findings": [],
        "actions": [],
        "assumptions": [],
    }
    result = report_node(state)
    report = result.get("report_markdown", "")
    assert "## Detected CNC features" in report
    assert "hole_count" in report
    print("PASS: Report renders Detected CNC features when CNC+numeric")


def test_22_explain_cache_signature_includes_part_features():
    """Phase 4: Cache signature changes when part_features changes."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.explain import _explain_cache_signature

    def make_state(hole_count: int):
        return {
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
            "part_summary_mode": "numeric",
            "findings": [],
            "part_features": {"hole_count": hole_count, "pocket_count": 0},
        }

    s1 = _explain_cache_signature(make_state(3))
    s2 = _explain_cache_signature(make_state(5))
    assert s1 != s2
    print("PASS: Cache signature differs when part_features.hole_count differs")


def test_20_report_includes_proposal():
    """Phase 3: Report renders Proposal for numeric finding."""
    from agent.state import Inputs, PartSummary, Finding, GraphState
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
        "findings": [
            Finding(
                id="DFM-NH1",
                category="DFM",
                severity="MEDIUM",
                title="Deep hole L/D ratio",
                why_it_matters="High L/D increases deflection.",
                recommendation="Consider peck drilling.",
                evidence={"hole_max_ld": 8.2},
                proposal="Reduce maximum hole L/D from 8.2 to <= 6.",
                proposal_steps=["Step one", "Step two"],
            )
        ],
        "actions": [],
        "assumptions": [],
    }
    result = report_node(state)
    report = result.get("report_markdown", "")
    assert "Proposal:" in report
    assert "8.2" in report
    assert "Proposal steps:" in report
    print("PASS: Report includes Proposal and Proposal steps")


def test_17_non_cnc_no_feature_rules():
    """Non-CNC process: part_metrics_evidence with hole/pocket metrics does NOT trigger DFM-NH/NP."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.rulesets.cnc import run_cnc_rules

    state: GraphState = {
        "inputs": Inputs(
            process="MIM",
            material="Steel",
            production_volume="Production",
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
            has_clamping_faces=False,
        ),
        "part_metrics_evidence": {
            "hole_max_ld": 8.2,
            "pocket_max_aspect": 5.0,
        },
    }
    out = run_cnc_rules(state)
    findings = out.get("findings", [])
    nh1 = next((f for f in findings if f.id == "DFM-NH1"), None)
    np1 = next((f for f in findings if f.id == "DFM-NP1"), None)
    assert nh1 is None, "DFM-NH1 must not trigger for MIM"
    assert np1 is None, "DFM-NP1 must not trigger for MIM"
    print("PASS: non-CNC -> no DFM-NH/DFM-NP feature rules")


def test_23_report_proxy_subsection():
    """Phase 4.1: part_features with hole_count=0 and hole_proxy_count=3 -> hole_count: 0 and fallback proxies subsection."""
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
        "part_summary_mode": "numeric",
        "part_features": {
            "hole_count": 0,
            "hole_max_ld": 0,
            "hole_max_depth_mm": 0,
            "hole_diameters_mm": [],
            "pocket_count": 0,
            "pocket_max_aspect": 0,
            "pocket_max_depth_mm": 0,
            "hole_proxy_count": 3,
            "hole_proxy_max_ld": 5.2,
            "hole_proxy_max_depth_mm": 12.5,
            "hole_proxy_diameters_mm": [3.0, 4.0, 5.0],
        },
        "findings": [],
        "actions": [],
        "assumptions": [],
    }
    result = report_node(state)
    report = result.get("report_markdown", "")
    assert "hole_count: 0\n" in report or "- hole_count: 0\n" in report
    assert "Detected CNC features (fallback proxies)" in report
    assert "hole_proxy_count: 3\n" in report or "- hole_proxy_count: 3\n" in report
    assert "pocket_count: 0\n" in report or "- pocket_count: 0\n" in report
    print("PASS: report hole_count=0 + hole_proxy_count=3 -> hole_count: 0 and fallback proxies subsection")


def test_24_checklist_normalize_strips_severity():
    """Phase 4.1: _normalize_checklist_item strips severity tags (e.g. 'Verify LOW] Low accessibility...')."""
    from agent.nodes.explain import _normalize_checklist_item

    # Strip [HIGH], [MEDIUM], [LOW] and similar
    out = _normalize_checklist_item("Verify LOW] Low accessibility for hole features.")
    assert "[LOW]" not in out and "[HIGH]" not in out and "[MEDIUM]" not in out
    assert "LOW]" not in out
    assert out.lower().startswith("verify ") or out.lower().startswith("address ")
    assert "low accessibility" in out.lower()

    # Strip leading [HIGH] etc.
    out2 = _normalize_checklist_item("[MEDIUM] Review pocket depth for chatter risk.")
    assert "[MEDIUM]" not in out2
    assert "review" in out2.lower() or "pocket" in out2.lower()

    # No severity tag in output
    out3 = _normalize_checklist_item("Verify LOW] Keep current tool access.")
    assert "LOW]" not in out3
    assert "verify" in out3.lower() or "keep" in out3.lower()
    print("PASS: checklist normalization strips severity tags")


def test_12_tolerance_validation():
    """_contains_invented_tolerances flags invented patterns, not normal dimensions."""
    from agent.nodes.explain import _contains_invented_tolerances

    # Should flag invented tolerances
    assert _contains_invented_tolerances("±0.05 mm") is True
    assert _contains_invented_tolerances("0.05–0.20 mm") is True
    assert _contains_invented_tolerances("tolerance of 0.1 mm") is True
    assert _contains_invented_tolerances("tighten to ±0.05 mm") is True
    assert _contains_invented_tolerances("range 0.1-0.2 mm") is True

    # Should NOT flag normal dimensions
    assert _contains_invented_tolerances("50 mm diameter") is False
    assert _contains_invented_tolerances("part is 100 mm long") is False
    assert _contains_invented_tolerances("wall thickness 2.5 mm") is False
    assert _contains_invented_tolerances("tolerance_criticality is Medium") is False

    print("PASS: tolerance validation -> flags invented patterns, ignores normal dimensions")


if __name__ == "__main__":
    failures = []
    for name, fn in [
        ("test_1_cnc_bins_unchanged", test_1_cnc_bins_unchanged),
        ("test_2_cnc_numeric_includes_section", test_2_cnc_numeric_includes_section),
        ("test_3_mim_numeric_no_metrics", test_3_mim_numeric_no_metrics),
        ("test_4_compileall", test_4_compileall),
        ("test_5_numeric_fallback_on_exception", test_5_numeric_fallback_on_exception),
        ("test_6_cnc_numeric_adapter_thin_wall", test_6_cnc_numeric_adapter_thin_wall),
        ("test_7_mim_numeric_no_adapter_no_evidence", test_7_mim_numeric_no_adapter_no_evidence),
        ("test_8_tool_access_proxy_guard", test_8_tool_access_proxy_guard),
        ("test_9_numeric_fallback_on_timeout", test_9_numeric_fallback_on_timeout),
        ("test_10_mim_bins_regression", test_10_mim_bins_regression),
        ("test_11_report_numeric_formatting", test_11_report_numeric_formatting),
        ("test_12_tolerance_validation", test_12_tolerance_validation),
        ("test_13_cad_present_no_missing_cad", test_13_cad_present_no_missing_cad),
        ("test_14_numeric_timeout_not_missing_cad", test_14_numeric_timeout_not_missing_cad),
        ("test_15_dfm_nh1_hole_ld_triggers", test_15_dfm_nh1_hole_ld_triggers),
        ("test_16_dfm_np1_pocket_aspect_triggers", test_16_dfm_np1_pocket_aspect_triggers),
        ("test_17_non_cnc_no_feature_rules", test_17_non_cnc_no_feature_rules),
        ("test_18_dfm_nh1_proposal_contains_evidence", test_18_dfm_nh1_proposal_contains_evidence),
        ("test_19_dfm_np1_proposal_contains_aspect", test_19_dfm_np1_proposal_contains_aspect),
        ("test_20_report_includes_proposal", test_20_report_includes_proposal),
        ("test_21_report_detected_cnc_features_section", test_21_report_detected_cnc_features_section),
        ("test_22_explain_cache_signature_includes_part_features", test_22_explain_cache_signature_includes_part_features),
        ("test_23_report_proxy_subsection", test_23_report_proxy_subsection),
        ("test_24_checklist_normalize_strips_severity", test_24_checklist_normalize_strips_severity),
    ]:
        try:
            fn()
        except Exception as e:
            failures.append((name, e))
            print(f"FAIL: {name} - {e}")

    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print("\nAll acceptance tests passed.")
    sys.exit(0)
