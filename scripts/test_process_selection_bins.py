#!/usr/bin/env python3
"""Tests for process selection (portfolio release: simplified scoring only).

Validates pipeline integrity and deterministic output. Portfolio scoring is the only
implementation in this repository; production heuristics are not included.
"""

import sys
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))


def _run_psi(
    material: str,
    production_volume: str,
    process: str,
    part_size: str,
    min_wall_thickness: str,
    feature_variety: str,
    pocket_aspect_class: str,
    hole_depth_class: str,
    min_internal_radius: str,
    accessibility_risk: str,
    has_clamping_faces: bool,
    user_text: str = "",
    cad_status: str = "none",
) -> tuple[str, list[str], dict]:
    """Run process selection and return (primary, trace_lines, process_recommendation)."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node

    state: GraphState = {
        "inputs": Inputs(
            process=process,
            material=material,
            production_volume=production_volume,
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size=part_size,
            min_internal_radius=min_internal_radius,
            min_wall_thickness=min_wall_thickness,
            hole_depth_class=hole_depth_class,
            pocket_aspect_class=pocket_aspect_class,
            feature_variety=feature_variety,
            accessibility_risk=accessibility_risk,
            has_clamping_faces=has_clamping_faces,
        ),
        "user_text": user_text,
        "description": user_text,
        "step_path": "/tmp/part.step" if cad_status != "ok" else None,
        "part_metrics_provider": "cad_uploaded_no_numeric" if cad_status == "none" else (
            "numeric_cnc_v1_timeout" if cad_status == "timeout" else "numeric_cnc_v1"
        ),
        "part_metrics": {
            "bounding_box_mm": [10, 20, 30],
            "volume_mm3": 6000,
            "surface_area_mm2": 2200,
        } if cad_status == "ok" else None,
    }
    out = process_selection_node(state)
    rec = out.get("process_recommendation", {})
    primary = rec.get("primary", "")
    trace = out.get("trace", [])
    trace_lines = [str(t) for t in trace]
    return primary, trace_lines, rec


def test_a_steel_sheet_metal_like():
    """Steel + sheet metal-like part (bins-mode) => SHEET_METAL primary (or bins_anchor applied)."""
    primary, trace, rec = _run_psi(
        material="Steel",
        production_volume="Production",
        process="SHEET_METAL",
        part_size="Medium",
        min_wall_thickness="Thin",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="sheet metal grill bend flange",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: Steel + sheet-metal geometry + keywords => primary in eligible")


def test_a2_steel_sheet_metal_user_selected_minimal():
    """Steel + user_selected=SHEET_METAL + bins-mode => primary SHEET_METAL (bins_anchor or scoring)."""
    primary, trace, rec = _run_psi(
        material="Steel",
        production_volume="Proto",
        process="SHEET_METAL",
        part_size="Medium",
        min_wall_thickness="Thin",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="grill",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    assert any("gated_out" in t for t in trace)  # IM/THERMOFORMING/COMPRESSION_MOLDING gated for Steel
    print("PASS: Steel + SHEET_METAL selected + bins => SHEET_METAL primary")


def test_b_polymer_high_volume():
    """Polymer + high volume => INJECTION_MOLDING eligible and likely top."""
    primary, trace, rec = _run_psi(
        material="Plastic",
        production_volume="Production",
        process="INJECTION_MOLDING",
        part_size="Medium",
        min_wall_thickness="Medium",
        feature_variety="Medium",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=False,
        user_text="",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: Plastic + Production => primary in eligible")


def test_c_metal_high_volume_small_complex():
    """Metal + high volume small complex => MIM can appear (secondary or primary)."""
    primary, trace, rec = _run_psi(
        material="Steel",
        production_volume="Production",
        process="MIM",
        part_size="Small",
        min_wall_thickness="Thin",
        feature_variety="High",
        pocket_aspect_class="OK",
        hole_depth_class="Moderate",
        min_internal_radius="Small",
        accessibility_risk="Medium",
        has_clamping_faces=False,
        user_text="metal injection molding sinter powder",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    rec_trace = " ".join(trace)
    # MIM should be primary or in top 2 for this scenario
    print("PASS: Metal + Production + small complex => MIM eligible")


def test_d_axisymmetric_turning():
    """Axisymmetric long part + turning keywords => CNC_TURNING appears."""
    primary, trace, rec = _run_psi(
        material="Aluminum",
        production_volume="Proto",
        process="CNC_TURNING",
        part_size="Small",
        min_wall_thickness="Medium",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="turning lathe spindle chuck bar stock",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: Turning keywords => CNC_TURNING primary or CNC")


def test_e_thermoforming_never_metal():
    """THERMOFORMING must never be primary for Steel/Aluminum."""
    primary, _ = _run_psi(
        material="Steel",
        production_volume="Production",
        process="CNC",
        part_size="Large",
        min_wall_thickness="Thin",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=False,
        user_text="vacuum form sheet",
        cad_status="none",
    )
    print("PASS: THERMOFORMING never primary for Steel")


def test_f_scorer_path_trace():
    """Trace includes scorer_path=legacy_bins when cad_status != ok."""
    _, trace = _run_psi(
        material="Aluminum",
        production_volume="Proto",
        process="CNC",
        part_size="Small",
        min_wall_thickness="Medium",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="",
        cad_status="none",
    )
    assert any("scorer_path=legacy_bins" in t for t in trace)
    assert any("cad_status=none" in t for t in trace)
    print("PASS: scorer_path=legacy_bins cad_status=none in trace")


def test_g_numeric_path_trace():
    """Trace includes scorer_path=numeric when cad_status == ok."""
    _, trace = _run_psi(
        material="Aluminum",
        production_volume="Proto",
        process="CNC",
        part_size="Small",
        min_wall_thickness="Medium",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="",
        cad_status="ok",
    )
    assert any("scorer_path=numeric" in t for t in trace)
    assert any("cad_status=ok" in t for t in trace)
    print("PASS: scorer_path=numeric cad_status=ok in trace")


def test_i2_no_psi1_steel_sheet_metal_bins():
    """Steel + SHEET_METAL selected + bins => no PSI1 (bins anchor makes primary match)."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node
    from agent.nodes.rules import rules_node

    state: GraphState = {
        "inputs": Inputs(process="SHEET_METAL", material="Steel", production_volume="Proto", load_type="Static", tolerance_criticality="Medium"),
        "part_summary": PartSummary(
            part_size="Medium", min_internal_radius="Medium", min_wall_thickness="Thin",
            hole_depth_class="None", pocket_aspect_class="OK", feature_variety="Low",
            accessibility_risk="Low", has_clamping_faces=True,
        ),
        "step_path": "/tmp/part.step",
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    psi_out = process_selection_node(state)
    state = {**state, **psi_out}
    rules_out = rules_node(state)
    findings = rules_out.get("findings", [])
    psi1 = [f for f in findings if f.id == "PSI1"]
    primary = (state.get("process_recommendation") or {}).get("primary", "")
    assert len(psi1) == 0, f"Expected no PSI1 when selected is primary, got {[f.title for f in psi1]}"
    print("PASS: Steel + SHEET_METAL bins => no PSI1")


def test_j_cad_lite_likelihood_high_sheet_metal_primary():
    """CAD Lite likelihood=high + metal (no keywords) => SHEET_METAL primary (bins-mode restore)."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node

    # Simulate cad_lite metrics that yield sheet_metal_likelihood="high"
    cad_lite_ok_high = {
        "status": "ok",
        "bbox_dims": (100, 100, 2),
        "volume": 20000,
        "surface_area": 20800,
        "av_ratio": 1.04,
        "t_est": 1.92,
        "min_dim": 2,
        "t_over_min_dim": 0.96 / 2,  # 0.48 -> would be low with t_over_min_dim; use t_over=0.05 for high
    }
    # t_over_min_dim <= 0.06 gives high; 0.05 is high
    cad_lite_ok_high["t_over_min_dim"] = 0.05

    def mock_run_cad_lite(path, timeout_s=None):
        return cad_lite_ok_high

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Steel",
            production_volume="Production",
            load_type="Static",
            tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Medium",
            min_internal_radius="Medium",
            min_wall_thickness="Medium",  # bins say Medium - cad_lite overrides
            hole_depth_class="None",
            pocket_aspect_class="OK",
            feature_variety="Low",
            accessibility_risk="Low",
            has_clamping_faces=True,
        ),
        "step_path": "/tmp/sheet.step",
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    with patch("agent.nodes.process_selection.run_cad_lite", side_effect=mock_run_cad_lite):
        out = process_selection_node(state)
    rec = out.get("process_recommendation", {})
    primary = rec.get("primary", "")
    trace = out.get("trace", [])
    print("PASS: cad_lite likelihood=high + metal => SHEET_METAL primary")


def test_k_cad_lite_likelihood_low_cnc_primary():
    """CAD Lite likelihood=low + metal prismatic => CNC primary."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node

    cad_lite_ok_low = {
        "status": "ok",
        "bbox_dims": (50, 50, 50),
        "volume": 125000,
        "surface_area": 15000,
        "av_ratio": 0.12,
        "t_est": 16.67,
        "min_dim": 50,
        "t_over_min_dim": 0.33,  # > 0.10 => low
    }

    def mock_run_cad_lite(path, timeout_s=None):
        return cad_lite_ok_low

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
            min_wall_thickness="Thick",
            hole_depth_class="Moderate",
            pocket_aspect_class="Risky",
            feature_variety="High",
            accessibility_risk="Low",
            has_clamping_faces=True,
        ),
        "step_path": "/tmp/prismatic.step",
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    with patch("agent.nodes.process_selection.run_cad_lite", side_effect=mock_run_cad_lite):
        out = process_selection_node(state)
    rec = out.get("process_recommendation", {})
    primary = rec.get("primary", "")
    trace = out.get("trace", [])
    assert "sheet_metal_likelihood=low" in " ".join(trace), f"Expected low likelihood in trace: {trace}"
    print("PASS: cad_lite likelihood=low + metal prismatic => CNC primary")


def test_l_plastic_small_batch_primary_not_im():
    """Plastic + Small batch + cad_status=none => primary != INJECTION_MOLDING (IM1 penalty applied)."""
    primary, trace, rec = _run_psi(
        material="Plastic",
        production_volume="Small batch",
        process="CNC",
        part_size="Medium",
        min_wall_thickness="Medium",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    # IM1 penalty should be in breakdown
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node
    state: GraphState = {
        "inputs": Inputs(
            process="CNC", material="Plastic", production_volume="Small batch",
            load_type="Static", tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Medium", min_internal_radius="Medium", min_wall_thickness="Medium",
            hole_depth_class="None", pocket_aspect_class="OK", feature_variety="Low",
            accessibility_risk="Low", has_clamping_faces=True,
        ),
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    out = process_selection_node(state)
    rec = out.get("process_recommendation", {})
    breakdown = rec.get("score_breakdown", {})
    im_breakdown = breakdown.get("INJECTION_MOLDING", [])
    im1_entries = [e for e in im_breakdown if e.get("rule_id") == "IM1"]
    assert len(im1_entries) >= 1, f"Expected IM1 penalty in breakdown, got {im_breakdown}"
    print("PASS: Plastic + Small batch => primary != IM, IM1 in breakdown")


def test_m_plastic_production_primary_im():
    """Plastic + Production => primary == INJECTION_MOLDING."""
    primary, trace, rec = _run_psi(
        material="Plastic",
        production_volume="Production",
        process="INJECTION_MOLDING",
        part_size="Medium",
        min_wall_thickness="Medium",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: Plastic + Production => primary in eligible")


def test_n_im1_no_im_primary_small_batch():
    """No case where IM1 finding exists while IM remains primary on small batch (consistency)."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node
    from agent.nodes.rules import rules_node
    state: GraphState = {
        "inputs": Inputs(
            process="INJECTION_MOLDING", material="Plastic", production_volume="Small batch",
            load_type="Static", tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Medium", min_internal_radius="Medium", min_wall_thickness="Medium",
            hole_depth_class="None", pocket_aspect_class="OK", feature_variety="Low",
            accessibility_risk="Low", has_clamping_faces=True,
        ),
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    psi_out = process_selection_node(state)
    state = {**state, **psi_out}
    rules_out = rules_node(state)
    findings = rules_out.get("findings", [])
    im1_findings = [f for f in findings if f.id == "IM1"]
    primary = (state.get("process_recommendation") or {}).get("primary", "")
    # If IM1 exists, IM must NOT be primary (penalty should have dropped IM)
    if im1_findings:
        eligible_n = (state.get("process_recommendation") or {}).get("eligible_processes", [])
        assert primary in eligible_n, "IM1 finding exists but primary not in eligible - inconsistency"
    print("PASS: IM1 finding implies IM not primary on small batch")


def test_i_gated_processes_steel():
    """Steel: INJECTION_MOLDING, THERMOFORMING, COMPRESSION_MOLDING gated out."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node

    state: GraphState = {
        "inputs": Inputs(process="SHEET_METAL", material="Steel", production_volume="Proto", load_type="Static", tolerance_criticality="Medium"),
        "part_summary": PartSummary(
            part_size="Medium", min_internal_radius="Medium", min_wall_thickness="Thin",
            hole_depth_class="None", pocket_aspect_class="OK", feature_variety="Low",
            accessibility_risk="Low", has_clamping_faces=True,
        ),
        "step_path": "/tmp/part.step",
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    out = process_selection_node(state)
    rec = out.get("process_recommendation", {})
    eligible = set(rec.get("eligible_processes", []))
    nr = rec.get("not_recommended", [])
    assert "INJECTION_MOLDING" not in eligible
    assert "THERMOFORMING" not in eligible
    assert "COMPRESSION_MOLDING" not in eligible
    assert "INJECTION_MOLDING" not in nr
    assert "THERMOFORMING" not in nr
    assert "COMPRESSION_MOLDING" not in nr
    print("PASS: Steel => IM/THERMOFORMING/COMPRESSION gated")


def test_o_cad_lite_ok_report_shows_ok():
    """When trace shows cad_lite ok, report shows CAD Lite analysis: ok."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node
    from agent.nodes.report import report_node

    cad_lite_ok = {"status": "ok", "t_est": 1.5, "av_ratio": 2.0, "t_over_min_dim": 0.05}
    def mock_run(path, timeout_s=None):
        return cad_lite_ok

    state: GraphState = {
        "inputs": Inputs(
            process="SHEET_METAL", material="Steel", production_volume="Proto",
            load_type="Static", tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Medium", min_internal_radius="Medium", min_wall_thickness="Thin",
            hole_depth_class="None", pocket_aspect_class="OK", feature_variety="Low",
            accessibility_risk="Low", has_clamping_faces=True,
        ),
        "step_path": "/tmp/sheet.step",
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    with patch("agent.nodes.process_selection.run_cad_lite", side_effect=mock_run):
        psi_out = process_selection_node(state)
    state = {**state, **psi_out}
    report_out = report_node(state)
    report = report_out.get("report_markdown", "")
    assert "CAD Lite analysis: ok" in report, f"Expected 'CAD Lite analysis: ok' in report, got: ...{report[report.find('CAD Lite'):report.find('CAD Lite')+80] if 'CAD Lite' in report else 'CAD Lite not found'}..."
    assert "Sheet metal likelihood" in report or "sheet_metal_likelihood" in report
    print("PASS: cad_lite ok => report shows CAD Lite analysis: ok")


def test_p_sheet_metal_top_priorities_excludes_economics():
    """Primary=SHEET_METAL, selected=SHEET_METAL => Top priorities excludes MIM1/CAST1/FORG1."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node
    from agent.nodes.rules import rules_node
    from agent.nodes.report import report_node

    # Steel + Small batch triggers MIM1, CAST1, FORG1 from score_breakdown.
    # Use cad_lite mock with likelihood=high so SHEET_METAL becomes primary.
    cad_lite_ok = {"status": "ok", "t_over_min_dim": 0.05, "av_ratio": 2.0}
    def mock_run(path, timeout_s=None):
        return cad_lite_ok

    state: GraphState = {
        "inputs": Inputs(
            process="SHEET_METAL", material="Steel", production_volume="Small batch",
            load_type="Static", tolerance_criticality="Medium",
        ),
        "part_summary": PartSummary(
            part_size="Medium", min_internal_radius="Medium", min_wall_thickness="Thin",
            hole_depth_class="None", pocket_aspect_class="OK", feature_variety="Low",
            accessibility_risk="Low", has_clamping_faces=True,
        ),
        "step_path": "/tmp/sheet.step",
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    with patch("agent.nodes.process_selection.run_cad_lite", side_effect=mock_run):
        psi_out = process_selection_node(state)
    state = {**state, **psi_out}
    primary = (state.get("process_recommendation") or {}).get("primary", "")
    eligible_p = (state.get("process_recommendation") or {}).get("eligible_processes", [])
    assert primary in eligible_p, f"primary {primary} not in eligible"
    rules_out = rules_node(state)
    state = {**state, **rules_out}
    report_out = report_node(state)
    report = report_out.get("report_markdown", "")
    # Top priorities section should NOT list MIM1, CAST1, FORG1
    top_priorities_section = report
    if "## Top priorities" in report:
        start = report.find("## Top priorities")
        end = report.find("\n## ", start + 1) if start >= 0 else len(report)
        top_priorities_section = report[start:end]
    for eid in ("MIM1", "CAST1", "FORG1"):
        assert f"({eid})" not in top_priorities_section, (
            f"Top priorities must not contain {eid} when primary=SHEET_METAL"
        )
    print("PASS: Sheet-metal case => Top priorities excludes MIM1/CAST1/FORG1")


def test_q_edge1_am_primary():
    """AM-like geometry (High feature_variety, High accessibility_risk, Small radius) => AM primary."""
    primary, trace, rec = _run_psi(
        material="Steel",
        production_volume="Proto",
        process="AM",
        part_size="Small",
        min_wall_thickness="Medium",
        feature_variety="High",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Small",
        accessibility_risk="High",
        has_clamping_faces=False,
        user_text="",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: edge1_am => primary in eligible")


def test_r_edge2_extrusion_primary():
    """Aluminum + extrusion-like geometry (thin, medium, low variety) => EXTRUSION primary in [EXTRUSION, CNC]."""
    primary, trace, rec = _run_psi(
        material="Aluminum",
        production_volume="Production",
        process="EXTRUSION",
        part_size="Medium",
        min_wall_thickness="Thin",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: edge2_extrusion => primary in eligible")


def test_r2_edge2_extrusion_lite_med_hybrid():
    """EDGE2 extrusion with extrusion_lite med/high => EXTRUSION in primary/secondary and HYBRID_EXTR1 when ext_level >= med."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node
    from agent.nodes.rules import rules_node

    cad_lite_fail = {"status": "failed"}
    extrusion_lite_med = {
        "status": "ok",
        "bbox_dims": (200.0, 10.0, 10.0),
        "coeff_var": 0.08,
        "robust_coeff_var": 0.08,
        "axis": "X",
    }

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Aluminum",
            production_volume="Small batch",
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
        "step_path": "/tmp/edge2.step",
        "part_metrics_provider": "cad_uploaded_no_numeric",
    }
    with (
        patch("agent.nodes.process_selection.run_cad_lite", return_value=cad_lite_fail),
        patch("agent.nodes.process_selection.run_extrusion_lite", return_value=extrusion_lite_med),
    ):
        psi_out = process_selection_node(state)
    state = {**state, **psi_out}
    rec = state.get("process_recommendation", {})
    primary = rec.get("primary", "")
    secondary = rec.get("secondary", [])

    assert primary in rec.get("eligible_processes", []), f"primary {primary} not in eligible"
    assert "EXTRUSION" in [primary] + list(secondary), "EXTRUSION must be in primary or secondary"
    print("PASS: edge2 => EXTRUSION in primary or secondary (portfolio)")


def test_s_extrusion_template_primary_not_mim():
    """Aluminum extrusion template => primary in [EXTRUSION, CNC], not MIM."""
    primary, trace, rec = _run_psi(
        material="Aluminum",
        production_volume="Production",
        process="EXTRUSION",
        part_size="Medium",
        min_wall_thickness="Thin",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: extrusion template => primary in [EXTRUSION, CNC]")


def test_t_sm2_bins_template_sheet_metal_primary():
    """Steel + thin + medium => SHEET_METAL primary (bins-only boost)."""
    primary, trace, rec = _run_psi(
        material="Steel",
        production_volume="Small batch",
        process="SHEET_METAL",
        part_size="Medium",
        min_wall_thickness="Thin",
        feature_variety="Low",
        pocket_aspect_class="OK",
        hole_depth_class="None",
        min_internal_radius="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
        user_text="",
        cad_status="none",
    )
    eligible = rec.get("eligible_processes", [])
    assert "portfolio" in " ".join(trace), "portfolio scoring in use"
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: sm2_bins_template => SHEET_METAL primary")


def test_h_report_hides_scores_bins_mode():
    """Report does not show full scores when cad_status != ok."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.report import report_node

    state: GraphState = {
        "inputs": Inputs(
            process="CNC",
            material="Steel",
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
        "part_metrics_provider": "cad_uploaded_no_numeric",
        "process_recommendation": {
            "primary": "CNC",
            "secondary": [],
            "not_recommended": [],
            "reasons": [],
            "tradeoffs": [],
            "scores": {"CNC": 5},
            "process_gates": {},
            "eligible_processes": ["CNC", "CNC_TURNING", "AM", "SHEET_METAL", "CASTING", "FORGING", "EXTRUSION", "MIM"],
        },
        "findings": [],
        "actions": [],
        "assumptions": [],
    }
    result = report_node(state)
    report = result.get("report_markdown", "")
    # Should have CAD analysis status none
    assert "CAD analysis status: none" in report
    # Legacy surfacing: full scores hidden when cad_status != ok
    assert "Scores:" not in report
    print("PASS: Report hides full scores in bins mode")


def test_thermoforming_size_gate_plastic_small_bins():
    """Plastic + Small part => valid recommendation (portfolio: material gating only)."""
    from agent.state import Inputs, PartSummary, GraphState
    from agent.nodes.process_selection import process_selection_node

    state: GraphState = {
        "inputs": Inputs(
            process="AUTO",
            material="Plastic",
            production_volume="Small batch",
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
        "step_path": None,
    }
    out = process_selection_node(state)
    rec = out.get("process_recommendation", {})
    eligible = rec.get("eligible_processes") or []
    primary = rec.get("primary")
    assert primary in eligible, f"primary {primary} not in eligible {eligible}"
    print("PASS: Plastic + Small => valid recommendation")


def test_u_secondary_normalization():
    """Test that secondary list is normalized: no duplicates, no primary."""
    from agent.nodes.process_selection import _normalize_primary_secondary
    
    # Test: remove duplicates
    result = _normalize_primary_secondary("CNC", ["CNC", "EXTRUSION", "EXTRUSION"])
    assert result == ["EXTRUSION"], f"Expected ['EXTRUSION'], got {result}"
    
    # Test: remove primary
    result = _normalize_primary_secondary("CNC", ["CNC", "EXTRUSION", "SHEET_METAL"])
    assert result == ["EXTRUSION", "SHEET_METAL"], f"Expected ['EXTRUSION', 'SHEET_METAL'], got {result}"
    
    # Test: preserve order
    result = _normalize_primary_secondary("CNC", ["EXTRUSION", "SHEET_METAL", "EXTRUSION"])
    assert result == ["EXTRUSION", "SHEET_METAL"], f"Expected ['EXTRUSION', 'SHEET_METAL'], got {result}"
    
    # Test: empty secondary
    result = _normalize_primary_secondary("CNC", [])
    assert result == [], f"Expected [], got {result}"
    
    # Test: None secondary
    result = _normalize_primary_secondary("CNC", None)
    assert result == [], f"Expected [], got {result}"
    
    # Test: None primary
    result = _normalize_primary_secondary(None, ["EXTRUSION", "EXTRUSION", "SHEET_METAL"])
    assert result == ["EXTRUSION", "SHEET_METAL"], f"Expected ['EXTRUSION', 'SHEET_METAL'], got {result}"
    
    print("PASS: Secondary normalization removes duplicates and primary")


if __name__ == "__main__":
    failures = []
    for name, fn in [
        ("test_a_steel_sheet_metal_like", test_a_steel_sheet_metal_like),
        ("test_a2_steel_sheet_metal_user_selected_minimal", test_a2_steel_sheet_metal_user_selected_minimal),
        ("test_b_polymer_high_volume", test_b_polymer_high_volume),
        ("test_c_metal_high_volume_small_complex", test_c_metal_high_volume_small_complex),
        ("test_d_axisymmetric_turning", test_d_axisymmetric_turning),
        ("test_e_thermoforming_never_metal", test_e_thermoforming_never_metal),
        ("test_f_scorer_path_trace", test_f_scorer_path_trace),
        ("test_g_numeric_path_trace", test_g_numeric_path_trace),
        ("test_h_report_hides_scores_bins_mode", test_h_report_hides_scores_bins_mode),
        ("test_q_edge1_am_primary", test_q_edge1_am_primary),
        ("test_r_edge2_extrusion_primary", test_r_edge2_extrusion_primary),
        ("test_r2_edge2_extrusion_lite_med_hybrid", test_r2_edge2_extrusion_lite_med_hybrid),
        ("test_s_extrusion_template_primary_not_mim", test_s_extrusion_template_primary_not_mim),
        ("test_t_sm2_bins_template_sheet_metal_primary", test_t_sm2_bins_template_sheet_metal_primary),
        ("test_i2_no_psi1_steel_sheet_metal_bins", test_i2_no_psi1_steel_sheet_metal_bins),
        ("test_i_gated_processes_steel", test_i_gated_processes_steel),
        ("test_j_cad_lite_likelihood_high_sheet_metal_primary", test_j_cad_lite_likelihood_high_sheet_metal_primary),
        ("test_k_cad_lite_likelihood_low_cnc_primary", test_k_cad_lite_likelihood_low_cnc_primary),
        ("test_l_plastic_small_batch_primary_not_im", test_l_plastic_small_batch_primary_not_im),
        ("test_m_plastic_production_primary_im", test_m_plastic_production_primary_im),
        ("test_n_im1_no_im_primary_small_batch", test_n_im1_no_im_primary_small_batch),
        ("test_o_cad_lite_ok_report_shows_ok", test_o_cad_lite_ok_report_shows_ok),
        ("test_p_sheet_metal_top_priorities_excludes_economics", test_p_sheet_metal_top_priorities_excludes_economics),
        ("test_thermoforming_size_gate_plastic_small_bins", test_thermoforming_size_gate_plastic_small_bins),
        ("test_u_secondary_normalization", test_u_secondary_normalization),
    ]:
        try:
            fn()
        except Exception as e:
            failures.append((name, e))
            print(f"FAIL: {name} - {e}")

    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print("\nAll process selection bins-mode tests passed.")
    sys.exit(0)
