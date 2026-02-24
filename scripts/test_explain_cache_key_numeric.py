#!/usr/bin/env python3
"""Test that explain cache key changes when CNC numeric state changes."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))


def test_explain_cache_signature_differs_by_part_summary_mode():
    """part_summary_mode differs -> signatures differ."""
    from agent.state import Inputs, PartSummary
    from agent.nodes.explain import _explain_cache_signature

    def make_state(mode: str):
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
            "findings": [],
            "sources": [],
            "rag_enabled": False,
            "part_summary_mode": mode,
        }

    sig_bins = _explain_cache_signature(make_state("bins"))
    sig_numeric = _explain_cache_signature(make_state("numeric"))
    assert sig_bins != sig_numeric
    print("PASS: part_summary_mode bins vs numeric -> different signatures")


def test_explain_cache_signature_differs_by_part_metrics_provider():
    """part_metrics_provider differs -> signatures differ."""
    from agent.state import Inputs, PartSummary
    from agent.nodes.explain import _explain_cache_signature

    def make_state(provider: str | None):
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
            "findings": [],
            "sources": [],
            "rag_enabled": False,
            "part_summary_mode": "numeric",
            "step_path": "dummy.step",
            "part_metrics_provider": provider,
        }

    sig_none = _explain_cache_signature(make_state(None))
    sig_v1 = _explain_cache_signature(make_state("numeric_cnc_v1"))
    sig_timeout = _explain_cache_signature(make_state("numeric_cnc_v1_timeout"))
    assert sig_none != sig_v1
    assert sig_v1 != sig_timeout
    print("PASS: part_metrics_provider differs -> different signatures")


def test_explain_cache_signature_differs_by_part_metrics_evidence():
    """part_metrics_evidence differs -> signatures differ."""
    from agent.state import Inputs, PartSummary
    from agent.nodes.explain import _explain_cache_signature

    def make_state(evidence: dict | None):
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
            "findings": [],
            "sources": [],
            "rag_enabled": False,
            "part_summary_mode": "numeric",
            "step_path": "part_a.step",
            "part_metrics_provider": "numeric_cnc_v1",
            "part_metrics_evidence": evidence,
        }

    sig_empty = _explain_cache_signature(make_state(None))
    sig_ev1 = _explain_cache_signature(make_state({"min_wall_thickness_mm": 0.8}))
    sig_ev2 = _explain_cache_signature(make_state({"min_wall_thickness_mm": 1.2}))
    assert sig_empty != sig_ev1
    assert sig_ev1 != sig_ev2
    print("PASS: part_metrics_evidence differs -> different signatures")


def test_explain_cache_signature_differs_by_step_path_basename():
    """step_path basename differs -> signatures differ."""
    from agent.state import Inputs, PartSummary
    from agent.nodes.explain import _explain_cache_signature

    def make_state(step_path: str | None):
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
            "findings": [],
            "sources": [],
            "rag_enabled": False,
            "part_summary_mode": "numeric",
            "step_path": step_path,
            "part_metrics_provider": "numeric_cnc_v1",
        }

    sig_none = _explain_cache_signature(make_state(None))
    sig_a = _explain_cache_signature(make_state("/path/to/part_a.step"))
    sig_b = _explain_cache_signature(make_state("/other/part_b.stp"))
    assert sig_none != sig_a
    assert sig_a != sig_b
    print("PASS: step_path basename differs -> different signatures")


def test_explain_cache_signature_identical_for_identical_state():
    """Identical state -> identical signatures."""
    from agent.state import Inputs, PartSummary
    from agent.nodes.explain import _explain_cache_signature

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
        "findings": [],
        "part_summary_mode": "bins",
        "step_path": None,
    }
    s1 = _explain_cache_signature(state)
    s2 = _explain_cache_signature(state)
    assert s1 == s2
    print("PASS: identical state -> identical signatures")


if __name__ == "__main__":
    failures = []
    tests = [
        ("part_summary_mode", test_explain_cache_signature_differs_by_part_summary_mode),
        ("part_metrics_provider", test_explain_cache_signature_differs_by_part_metrics_provider),
        ("part_metrics_evidence", test_explain_cache_signature_differs_by_part_metrics_evidence),
        ("step_path_basename", test_explain_cache_signature_differs_by_step_path_basename),
        ("identical_state", test_explain_cache_signature_identical_for_identical_state),
    ]
    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            failures.append((name, e))
            print(f"FAIL: {name} - {e}")

    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print("\nAll explain cache key tests passed.")
    sys.exit(0)
