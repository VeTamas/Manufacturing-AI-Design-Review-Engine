from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


Severity = Literal["HIGH", "MEDIUM", "LOW"]


class Error(BaseModel):
    """Structured error emitted by graph nodes (recoverable; short-circuit when set)."""
    node: str
    type: str
    message: str
    retry_exhausted: bool = False


class Confidence(BaseModel):
    """Structured confidence and limitations from self-review."""
    score: float = Field(ge=0.0, le=1.0, default=0.5)  # Legacy: final_confidence
    deterministic_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    llm_delta: float = Field(ge=-0.10, le=0.10, default=0.0)
    final_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    llm_rationale: list[str] = Field(default_factory=list)
    uncertainty_flags: list[str] = Field(default_factory=list)
    high_confidence: list[str] = Field(default_factory=list)
    medium_confidence: list[str] = Field(default_factory=list)
    low_confidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    to_improve: list[str] = Field(default_factory=list)


class ConfidenceInputs(BaseModel):
    has_2d_drawing: bool = False
    step_scale_confirmed: bool = True
    turning_support_confirmed: bool = False


@dataclass
class Inputs:
    process: Literal["AUTO", "CNC", "CNC_TURNING", "AM", "FDM", "SHEET_METAL", "INJECTION_MOLDING", "CASTING", "FORGING", "EXTRUSION", "MIM", "THERMOFORMING", "COMPRESSION_MOLDING"]
    material: Literal["Aluminum", "Steel", "Plastic"]
    production_volume: Literal["Proto", "Small batch", "Production"]
    load_type: Literal["Static", "Dynamic", "Shock"]
    tolerance_criticality: Literal["Low", "Medium", "High"]
    am_tech: Literal["AUTO", "FDM", "METAL_LPBF", "THERMOPLASTIC_HIGH_TEMP", "SLA", "SLS", "MJF"] = "AUTO"  # Optional, only used when process == "AM"
    user_text: str = ""  # Optional free-text description/notes from user


@dataclass
class PartSummary:
    part_size: Literal["Small", "Medium", "Large"]
    min_internal_radius: Literal["Small", "Medium", "Large", "Unknown"]
    min_wall_thickness: Literal["Thin", "Medium", "Thick", "Unknown"]
    hole_depth_class: Literal["None", "Moderate", "Deep", "Unknown"]
    pocket_aspect_class: Literal["OK", "Risky", "Extreme", "Unknown"]
    feature_variety: Literal["Low", "Medium", "High"]
    accessibility_risk: Literal["Low", "Medium", "High"]
    has_clamping_faces: bool


def _merge_dict(a: dict, b: dict) -> dict:
    """Reducer: merge dicts (right-biased) for usage_by_node aggregation."""
    out = dict(a or {})
    out.update(b or {})
    return out


@dataclass
class Finding:
    id: str
    category: str  # DESIGN_REVIEW | DFM | PROCESS_SELECTION | etc.
    severity: Severity
    title: str
    why_it_matters: str
    recommendation: str
    evidence: dict | None = None  # optional numeric evidence for CNC-backed findings
    proposal: str | None = None  # Phase 3: deterministic redesign proposal (CNC numeric)
    proposal_steps: list[str] | None = None  # Phase 3: actionable steps (max 5)
    targets: list[str] | None = None  # Phase 3: optional target IDs (reserved)


class GraphState(TypedDict, total=False):
    # inputs
    inputs: Inputs
    part_summary: PartSummary
    rag_enabled: bool
    confidence_inputs: ConfidenceInputs | None
    cad_metrics: dict | None
    part_summary_mode: str  # "bins" | "numeric"
    part_metrics: dict | None  # numeric analysis results
    part_metrics_provider: str | None  # e.g. "numeric_cnc_v1"
    part_metrics_evidence: dict | None  # numeric-derived evidence for CNC rules
    part_features: dict | None  # CNC v2: hole/pocket features from STEP
    step_path: str | None  # path to STEP file for numeric analysis

    # outputs (trace/sources use reducers: nodes return delta lists)
    findings: list[Finding]
    actions: list[str]
    assumptions: list[str]
    report_markdown: str
    sources: Annotated[list[dict], operator.add]
    confidence: Confidence | None
    process_recommendation: dict | None
    trace: Annotated[list[str], operator.add]

    usage: dict
    usage_by_node: Annotated[dict[str, dict], _merge_dict]
    error: Error | None

    # refine node (post-RAG): optional enriched sections for report
    refined_priorities: list[str]
    refined_action_checklist: list[str]
    decision_rationale: str | None

    # agentic decision loop (hidden)
    decision_round: int
    max_rounds: int
    _decision: str  # Routing decision: "rag" | "reassess" | "accept"
    _summary_source: str  # "ui_final" = do not overwrite part_summary