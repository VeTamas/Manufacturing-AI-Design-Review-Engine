"""Single source of truth for CAD presence and analysis status.

Used across process_selection, rules, report, and self_review to ensure
consistent semantics: never claim "No CAD" when STEP is uploaded.
"""
from __future__ import annotations

from typing import Literal

from agent.state import GraphState

# Providers that indicate successful analysis (technology-agnostic)
_OK_PROVIDERS = frozenset({"numeric_cnc_v1", "sheet_metal_lite_v1"})
# Provider suffixes indicating failure/timeout
_FAIL_SUFFIX = "_failed"
_TIMEOUT_SUFFIX = "_timeout"

_REQUIRED_METRIC_KEYS = frozenset({"bounding_box_mm", "volume_mm3", "surface_area_mm2"})


def cad_uploaded(state: GraphState) -> bool:
    """Whether a STEP file path is present (CAD uploaded).

    CAD_UPLOADED := bool(step_path)
    """
    step_path = state.get("step_path")
    return bool(step_path and isinstance(step_path, str) and str(step_path).strip())


def cad_analysis_status(
    state: GraphState,
) -> Literal["none", "ok", "failed", "timeout"]:
    """Analysis status for uploaded CAD.

    - ok: provider indicates success AND metrics dict has required keys
    - failed: provider suffix _failed
    - timeout: provider suffix _timeout
    - none: no analysis run (bins mode) or no provider
    """
    provider = (state.get("part_metrics_provider") or "").strip()
    part_metrics = state.get("part_metrics")
    part_summary_mode = state.get("part_summary_mode") or "bins"

    if provider.endswith(_TIMEOUT_SUFFIX):
        return "timeout"
    if provider.endswith(_FAIL_SUFFIX):
        return "failed"
    if provider in _OK_PROVIDERS:
        if isinstance(part_metrics, dict) and _REQUIRED_METRIC_KEYS <= part_metrics.keys():
            return "ok"
        # Provider says ok but metrics invalid -> treat as failed
        return "failed"
    # cad_uploaded_no_numeric, empty, or bins-only: none
    return "none"


def cad_evidence_available(state: GraphState) -> bool:
    """Whether CAD-derived evidence is available for downstream use.

    True when cad_analysis_status(state) == "ok".
    """
    return cad_analysis_status(state) == "ok"


def cad_evidence_keys(state: GraphState) -> tuple[str, ...]:
    """Return keys present in part_metrics_evidence or part_features (for tracing)."""
    keys: list[str] = []
    ev = state.get("part_metrics_evidence")
    if isinstance(ev, dict) and ev:
        keys.extend(ev.keys())
    pf = state.get("part_features")
    if isinstance(pf, dict) and pf:
        for k in pf:
            if k not in keys:
                keys.append(k)
    return tuple(sorted(keys))
