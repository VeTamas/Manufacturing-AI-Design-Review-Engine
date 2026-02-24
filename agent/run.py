from __future__ import annotations

import os

# Default to offline-first behavior (can override with CNCR_OFFLINE=0)
os.environ.setdefault("CNCR_OFFLINE", "1")

from agent.graph import build_graph
from agent.state import ConfidenceInputs, Error, GraphState, Inputs, PartSummary

_INPUTS_PROCESS = frozenset({"AUTO", "CNC", "CNC_TURNING", "AM", "FDM", "SHEET_METAL", "INJECTION_MOLDING", "CASTING", "FORGING", "EXTRUSION", "MIM", "THERMOFORMING", "COMPRESSION_MOLDING"})
_INPUTS_MATERIAL = frozenset({"Aluminum", "Steel", "Plastic"})
_INPUTS_VOLUME = frozenset({"Proto", "Small batch", "Production"})
_INPUTS_LOAD = frozenset({"Static", "Dynamic", "Shock"})
_INPUTS_TOL = frozenset({"Low", "Medium", "High"})
_PART_SIZE = frozenset({"Small", "Medium", "Large"})
_PART_RADIUS = frozenset({"Small", "Medium", "Large", "Unknown"})
_PART_WALL = frozenset({"Thin", "Medium", "Thick", "Unknown"})
_PART_HOLE = frozenset({"None", "Moderate", "Deep", "Unknown"})
_PART_POCKET = frozenset({"OK", "Risky", "Extreme", "Unknown"})
_PART_VARIETY = frozenset({"Low", "Medium", "High"})
_PART_ACCESS = frozenset({"Low", "Medium", "High"})


def _validate_inputs_part_summary(inputs: Inputs, part_summary: PartSummary) -> Error | None:
    """Runtime validation of Inputs and PartSummary. Returns Error if invalid."""
    if not isinstance(inputs, Inputs) or not isinstance(part_summary, PartSummary):
        return Error(
            node="run",
            type="ValidationError",
            message="inputs and part_summary must be Inputs and PartSummary instances",
            retry_exhausted=False,
        )
    try:
        if getattr(inputs, "process", None) not in _INPUTS_PROCESS:
            return Error(node="run", type="ValidationError", message="inputs.process invalid", retry_exhausted=False)
        if getattr(inputs, "material", None) not in _INPUTS_MATERIAL:
            return Error(node="run", type="ValidationError", message="inputs.material invalid", retry_exhausted=False)
        if getattr(inputs, "production_volume", None) not in _INPUTS_VOLUME:
            return Error(node="run", type="ValidationError", message="inputs.production_volume invalid", retry_exhausted=False)
        if getattr(inputs, "load_type", None) not in _INPUTS_LOAD:
            return Error(node="run", type="ValidationError", message="inputs.load_type invalid", retry_exhausted=False)
        if getattr(inputs, "tolerance_criticality", None) not in _INPUTS_TOL:
            return Error(node="run", type="ValidationError", message="inputs.tolerance_criticality invalid", retry_exhausted=False)
        if getattr(part_summary, "part_size", None) not in _PART_SIZE:
            return Error(node="run", type="ValidationError", message="part_summary.part_size invalid", retry_exhausted=False)
        if getattr(part_summary, "min_internal_radius", None) not in _PART_RADIUS:
            return Error(node="run", type="ValidationError", message="part_summary.min_internal_radius invalid", retry_exhausted=False)
        if getattr(part_summary, "min_wall_thickness", None) not in _PART_WALL:
            return Error(node="run", type="ValidationError", message="part_summary.min_wall_thickness invalid", retry_exhausted=False)
        if getattr(part_summary, "hole_depth_class", None) not in _PART_HOLE:
            return Error(node="run", type="ValidationError", message="part_summary.hole_depth_class invalid", retry_exhausted=False)
        if getattr(part_summary, "pocket_aspect_class", None) not in _PART_POCKET:
            return Error(node="run", type="ValidationError", message="part_summary.pocket_aspect_class invalid", retry_exhausted=False)
        if getattr(part_summary, "feature_variety", None) not in _PART_VARIETY:
            return Error(node="run", type="ValidationError", message="part_summary.feature_variety invalid", retry_exhausted=False)
        if getattr(part_summary, "accessibility_risk", None) not in _PART_ACCESS:
            return Error(node="run", type="ValidationError", message="part_summary.accessibility_risk invalid", retry_exhausted=False)
        if not hasattr(part_summary, "has_clamping_faces") or not isinstance(getattr(part_summary, "has_clamping_faces"), bool):
            return Error(node="run", type="ValidationError", message="part_summary.has_clamping_faces must be bool", retry_exhausted=False)
    except Exception as e:
        return Error(node="run", type="ValidationError", message=str(e), retry_exhausted=False)
    return None


def run_agent(
    inputs: Inputs,
    part_summary: PartSummary,
    rag_enabled: bool = False,
    confidence_inputs: ConfidenceInputs | None = None,
    cad_metrics: dict | None = None,
    user_text: str | None = None,
    part_summary_mode: str = "bins",
    step_path: str | None = None,
) -> GraphState:
    graph = build_graph()
    state: GraphState = {
        "inputs": inputs,
        "part_summary": part_summary,
        "rag_enabled": rag_enabled,
        "confidence_inputs": confidence_inputs,
        "cad_metrics": cad_metrics,
        "user_text": user_text or "",
        "description": user_text or "",  # Compatibility: some nodes read "description" first
        "trace": ["Run started"],
        "_summary_source": "ui_final",
        "part_summary_mode": part_summary_mode,
        "step_path": step_path,
    }
    # Numeric analysis: if numeric mode and process has analyzer, run and add part_metrics
    if part_summary_mode == "numeric" and step_path:
        from agent.geometry.part_summary_provider import build_part_summary
        try:
            _, delta = build_part_summary(state)
            if delta:
                state = {**state, **delta}
        except Exception:
            pass  # Fallback: bins only

    # CAD presence: when STEP uploaded but no provider set (bins mode or analysis skipped),
    # set explicit provider so downstream never infers "No CAD"
    if step_path and not (state.get("part_metrics_provider") or "").strip():
        state = {**state, "part_metrics_provider": "cad_uploaded_no_numeric"}
    err = _validate_inputs_part_summary(inputs, part_summary)
    if err is not None:
        return {**state, "error": err}
    try:
        out: GraphState = graph.invoke(state)
        return out
    except Exception as e:
        return {
            **state,
            "error": Error(
                node="graph",
                type=type(e).__name__,
                message=str(e),
                retry_exhausted=False,
            ),
        }