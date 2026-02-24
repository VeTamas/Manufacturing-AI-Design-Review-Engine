from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from agent.config import CONFIG
from agent.geometry.cad_presence import cad_analysis_status, cad_uploaded
from agent.geometry.evidence_for_llm import build_geometry_evidence_block
from agent.llm import ChatOpenAINoTemperature
from agent.llm.ollama_client import OllamaClient
from agent.state import Confidence, Error, GraphState
from agent.utils.retry import run_with_retries

logger = logging.getLogger(__name__)


def _offline_enabled() -> bool:
    """Check if offline mode is enabled."""
    return os.getenv("CNCR_OFFLINE", "1") == "1"

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

_FALLBACK_CONFIDENCE = Confidence(
    score=0.5,
    high_confidence=[],
    medium_confidence=[],
    low_confidence=[],
    limitations=["Self-review parsing failed; using fallback."],
    to_improve=["Verify agent output manually."],
)


def _read_text(path: Path) -> str:
    from agent.utils.filetrace import traced_read_text
    return traced_read_text(path, encoding="utf-8")


def _build_user_payload(state: GraphState) -> str:
    findings = state.get("findings", [])
    actions = state.get("actions", [])
    assumptions = state.get("assumptions", [])
    sources = state.get("sources", [])
    inputs = state.get("inputs")
    part = state.get("part_summary")

    parts = []
    if findings:
        parts.append("Findings:\n" + "\n".join(
            f"- [{f.severity}] {f.title}: {f.recommendation}" for f in findings
        ))
    else:
        parts.append("Findings: none.")
    parts.append("\nActions: " + (", ".join(actions) if actions else "none."))
    parts.append("\nAssumptions: " + (", ".join(assumptions) if assumptions else "none."))
    if sources:
        parts.append("\nRAG sources (snippet filenames): " + ", ".join(s.get("source", "?") for s in sources[:5]))
    else:
        parts.append("\nRAG sources: none.")
    if inputs:
        parts.append(
            f"\nInputs: material={inputs.material}, volume={inputs.production_volume}, "
            f"load={inputs.load_type}, tolerance_crit={inputs.tolerance_criticality}"
        )
    if part:
        parts.append(
            f"Part summary: size={part.part_size}, radius={part.min_internal_radius}, "
            f"wall={part.min_wall_thickness}, hole_depth={part.hole_depth_class}, "
            f"pocket={part.pocket_aspect_class}, variety={part.feature_variety}, "
            f"access={part.accessibility_risk}, clamping={part.has_clamping_faces}"
        )
    # CAD presence (use central helper; authoritative predicate)
    cad_present = cad_uploaded(state)
    cad_status = cad_analysis_status(state)
    parts.append(f"\nCAD uploaded: {'yes' if cad_present else 'no'}")
    parts.append(f"CAD analysis status: {cad_status}")
    if cad_present:
        step_path = state.get("step_path")
        if step_path and isinstance(step_path, str):
            parts.append(f"STEP path: {os.path.basename(step_path)}")
        provider = state.get("part_metrics_provider")
        if provider:
            parts.append(f"part_metrics_provider: {provider}")
    # Geometry/metrics for confidence delta (close call, CAD evidence, RAG)
    parts.append("\n" + build_geometry_evidence_block(state))
    proc_rec = state.get("process_recommendation") or {}
    scores = proc_rec.get("scores") or {}
    primary = proc_rec.get("primary")
    second = next((p for p in sorted(scores, key=lambda x: scores.get(x, 0), reverse=True) if p != primary), None) if primary else None
    score_diff = (scores.get(primary, 0) - scores.get(second, 0)) if (primary and second) else 0
    conf = state.get("confidence_inputs")
    has_2d = bool(conf.get("has_2d_drawing", False) if isinstance(conf, dict) else (getattr(conf, "has_2d_drawing", False) if conf else False))
    rag_sources = state.get("sources") or []
    parts.append(f"\nDelta factors: close_call={score_diff <= 2 and primary and second} has_2d_drawing={has_2d} cad_evidence={'y' if cad_status == 'ok' or (proc_rec.get('cad_lite') or {}).get('status') == 'ok' else 'n'} rag_sources_count={len(rag_sources)}")
    return "\n".join(parts)


def _validate_llm_json_required(parsed: dict | None) -> bool:
    """Validate that parsed LLM JSON has required keys for hybrid confidence.
    
    Requires: llm_delta or delta or score; llm_rationale (list len>=3 after filtering placeholders);
    uncertainty_flags (list). If any missing, treat as invalid.
    """
    if not parsed or not isinstance(parsed, dict):
        return False
    if "llm_delta" not in parsed and "delta" not in parsed and "score" not in parsed:
        return False
    rationale = parsed.get("llm_rationale", [])
    if not isinstance(rationale, list):
        return False
    rationale_clean = [str(x).strip() for x in rationale if str(x).strip() and not _is_generic_placeholder(str(x))]
    if len(rationale_clean) < 3:
        return False
    flags = parsed.get("uncertainty_flags", [])
    if not isinstance(flags, list):
        return False
    return True


def _parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    # Drop markdown code fences if present
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if m:
        raw = m.group(1).strip()
    try:
        out = json.loads(raw)
        if isinstance(out, dict):
            return out
    except json.JSONDecodeError:
        pass
    return None


_REQUIRED_NUMERIC_KEYS = frozenset({"bounding_box_mm", "volume_mm3", "surface_area_mm2"})


def _cad_is_present(state: GraphState) -> bool:
    """Single authoritative predicate: CAD/STEP is present.

    Delegates to cad_presence.cad_uploaded for consistency.
    Kept for backward compatibility with _numeric_metrics_present etc.
    """
    from agent.geometry.cad_presence import cad_uploaded
    return cad_uploaded(state)


def _numeric_metrics_present(state: GraphState) -> bool:
    """CNC-only: CAD + numeric_cnc_v1 metrics are present (do not suggest attach numeric)."""
    if not _cad_is_present(state):
        return False
    provider = state.get("part_metrics_provider") or ""
    if provider != "numeric_cnc_v1":
        return False
    part_metrics = state.get("part_metrics")
    return (
        isinstance(part_metrics, dict)
        and part_metrics
        and _REQUIRED_NUMERIC_KEYS <= part_metrics.keys()
    )


def _to_improve_suggests_numeric(t: str) -> bool:
    """True if text suggests attaching/running numeric analysis."""
    lower = str(t).lower()
    patterns = [
        "attach numeric", "run numeric", "numeric analysis", "upload step",
        "provide numeric", "include numeric", "add numeric", "numeric metrics",
    ]
    return any(p in lower for p in patterns)


def _has_critical_unknown(part: Any) -> bool:
    """True if PartSummary has critical fields Unknown (hole_depth_class 'None' = no holes, not missing)."""
    if not part:
        return True
    if getattr(part, "min_internal_radius", None) == "Unknown":
        return True
    if getattr(part, "min_wall_thickness", None) == "Unknown":
        return True
    if getattr(part, "hole_depth_class", None) == "Unknown":
        return True
    if getattr(part, "pocket_aspect_class", None) == "Unknown":
        return True
    return False


def _apply_flag_adjustments(
    base_score: float,
    flags: list[str],
    state: GraphState,
) -> tuple[float, list[tuple[str, float]]]:
    """Apply deterministic adjustments based on LLM uncertainty flags.
    
    Args:
        base_score: Deterministic baseline score
        flags: List of uncertainty flag strings from LLM
        state: GraphState
        
    Returns:
        Tuple of (adjusted_score, list of (flag, delta) applied)
    """
    mapping = {
        "missing_cad": -0.05,
        "no_2d_drawing": -0.04,
        "no_numeric_tolerances": -0.03,
        "unknown_shop_constraints": -0.02,
        "unclear_volume": -0.03,
        "process_mismatch_uncertain": -0.02,
        "geometry_bins_only": -0.03,
        "step_scale_unconfirmed": -0.03,
        "no_rag_sources": -0.02,
        "geometry_uncertain": -0.02,
        "numeric_analysis_failed": -0.02,
        "numeric_analysis_timeout": -0.02,
    }
    adjustments: list[tuple[str, float]] = []
    score = base_score
    cad_present = _cad_is_present(state)

    sources = state.get("sources", []) or []
    if "rag_evidence_strong" in flags and len(sources) >= 4:
        adjustments.append(("rag_evidence_strong", 0.02))
        score += 0.02

    # CNC-only: add numeric_analysis_failed/timeout when CAD present but analysis failed
    inputs = state.get("inputs")
    process = getattr(inputs, "process", "") if inputs else ""
    if cad_present and process in ("CNC", "CNC_TURNING"):
        provider = state.get("part_metrics_provider") or ""
        mode = state.get("part_summary_mode") or "bins"
        if mode == "numeric" and provider in ("numeric_cnc_v1_failed", "numeric_cnc_v1_timeout"):
            flag = "numeric_analysis_timeout" if "timeout" in provider else "numeric_analysis_failed"
            if flag not in [str(x).strip().lower() for x in flags]:
                adjustments.append((flag, mapping[flag]))
                score += mapping[flag]

    # step_scale_unconfirmed: only penalize when explicitly unconfirmed (not when missing/confirmed)
    conf_inputs = state.get("confidence_inputs")
    step_explicitly_unconfirmed = (
        conf_inputs is not None
        and hasattr(conf_inputs, "step_scale_confirmed")
        and conf_inputs.step_scale_confirmed is False
    )

    for f in flags:
        key = str(f).strip().lower()
        if key in mapping:
            # Do NOT add missing_cad or geometry_uncertain when CAD is present
            if cad_present and key in ("missing_cad", "geometry_uncertain"):
                continue
            # Do NOT add step_scale_unconfirmed when scale is confirmed or field missing
            if key == "step_scale_unconfirmed" and not step_explicitly_unconfirmed:
                continue
            delta = mapping[key]
            adjustments.append((key, delta))
            score += delta

    score = max(0.0, min(1.0, score))
    return score, adjustments


def _base_confidence_score(state: GraphState) -> float:
    """Compute deterministic base confidence score using transparent heuristics.
    
    Args:
        state: GraphState
        
    Returns:
        Base confidence score in [0.35, 0.90], rounded to 2 decimals
    """
    score = 0.75  # Start at 0.75
    
    inputs = state.get("inputs")
    part = state.get("part_summary")
    findings = state.get("findings", [])
    sources = state.get("sources", [])
    conf_inputs = state.get("confidence_inputs")
    proc_rec = state.get("process_recommendation") or {}
    
    # Penalties
    if conf_inputs:
        if not conf_inputs.has_2d_drawing:
            score -= 0.05
        if conf_inputs and hasattr(conf_inputs, "step_scale_confirmed") and conf_inputs.step_scale_confirmed is False:
            score -= 0.03
    
    # Process mismatch penalty
    if inputs and proc_rec:
        user_selected = getattr(inputs, "process", None)
        primary = proc_rec.get("primary")
        if user_selected and primary and user_selected != primary:
            score -= 0.08
    
    # Findings penalties
    has_high = any(getattr(f, "severity", "") == "HIGH" for f in findings)
    if has_high:
        score -= 0.05  # Cap once
    
    med_count = sum(1 for f in findings if getattr(f, "severity", "") == "MEDIUM")
    if med_count >= 2:
        score -= 0.03
    
    # RAG penalty: rag_enabled but no sources
    rag_enabled = state.get("rag_enabled", False)
    if rag_enabled and not sources:
        score -= 0.03
    
    # Unknown geometry fields penalty
    unknown_count = 0
    if part:
        for field in ["min_internal_radius", "min_wall_thickness", "hole_depth_class", "pocket_aspect_class"]:
            if getattr(part, field, None) == "Unknown":
                unknown_count += 1
    if unknown_count >= 2:
        score -= 0.03
    
    # Bonuses
    sources_count = len(sources) if sources else 0
    if sources_count >= 3:
        score += 0.03
    
    # Clamping faces bonus (CNC)
    if inputs and part:
        process = getattr(inputs, "process", "")
        if process in ("CNC", "CNC_TURNING") and getattr(part, "has_clamping_faces", False):
            score += 0.01
    
    # Clamp to [0.35, 0.90] and round
    score = max(0.35, min(0.90, score))
    return round(score, 2)


def _normalize_for_dedup(text: str) -> str:
    """Normalize text for duplicate detection (lowercase, strip punctuation).
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized string for comparison
    """
    # Remove finding codes in parentheses for comparison
    text_no_code = re.sub(r"\s*\([A-Z0-9]+\)\s*", " ", text)
    # Lowercase and remove punctuation
    normalized = re.sub(r"[^a-z0-9\s]", "", text_no_code.lower())
    # Collapse whitespace
    normalized = " ".join(normalized.split())
    return normalized


def _deduplicate_bullets(bullets: list[str]) -> list[str]:
    """Remove duplicate bullets, preferring those with finding codes.
    
    Args:
        bullets: List of bullet strings
        
    Returns:
        Deduplicated list
    """
    seen_norms = {}
    result = []
    
    for bullet in bullets:
        norm = _normalize_for_dedup(bullet)
        if norm not in seen_norms:
            seen_norms[norm] = bullet
            result.append(bullet)
        else:
            # If current bullet has a finding code and existing doesn't, prefer current
            existing = seen_norms[norm]
            has_code_current = bool(re.search(r"\([A-Z0-9]+\)", bullet))
            has_code_existing = bool(re.search(r"\([A-Z0-9]+\)", existing))
            if has_code_current and not has_code_existing:
                # Replace existing with current
                idx = result.index(existing)
                result[idx] = bullet
                seen_norms[norm] = bullet
    
    return result


def _generate_deterministic_confidence_texts(state: GraphState) -> dict[str, list[str]]:
    """Generate deterministic confidence text lists from findings and inputs.
    
    Args:
        state: GraphState
        
    Returns:
        Dict with high_confidence, medium_confidence, low_confidence, limitations, to_improve lists
    """
    findings = state.get("findings", [])
    sources = state.get("sources", [])
    inputs = state.get("inputs")
    conf_inputs = state.get("confidence_inputs")
    part = state.get("part_summary")
    proc_rec = state.get("process_recommendation") or {}
    
    high_conf = []
    med_conf = []
    low_conf = []
    limitations = []
    to_improve = []
    
    # High confidence bullets: up to 2 from HIGH findings (mitigation statements)
    high_findings = [f for f in findings if getattr(f, "severity", "") == "HIGH"]
    for f in high_findings[:3]:  # Process more, then deduplicate
        fid = getattr(f, "id", "")
        title = getattr(f, "title", "")
        recommendation = getattr(f, "recommendation", "")
        
        # Convert finding to actionable confidence statement
        if title:
            # Extract key guidance from title/recommendation
            if recommendation:
                # Use first sentence of recommendation if available
                rec_first = recommendation.split(".")[0].strip()
                if rec_first:
                    bullet = f"{rec_first} ({fid})." if fid else f"{rec_first}."
                else:
                    bullet = f"{title} ({fid})." if fid else f"{title}."
            else:
                bullet = f"{title} ({fid})." if fid else f"{title}."
            high_conf.append(bullet)
    
    # Deduplicate high confidence bullets
    high_conf = _deduplicate_bullets(high_conf)[:2]
    
    # Medium confidence bullets: up to 2 from MEDIUM findings (PSI1 must appear if present)
    med_findings = [f for f in findings if getattr(f, "severity", "") == "MEDIUM"]
    
    # Prioritize PSI1 if present
    psi1_finding = next((f for f in med_findings if getattr(f, "id", "") == "PSI1"), None)
    if psi1_finding:
        # Generate PSI1-specific bullet
        user_selected = getattr(inputs, "process", None) if inputs else None
        primary = proc_rec.get("primary")
        if user_selected and primary and user_selected != primary:
            # Format: "Process mismatch tradeoffs (X vs Y) need validation (PSI1)."
            med_conf.append(f"Process mismatch tradeoffs ({user_selected} vs {primary}) need validation (PSI1).")
        else:
            # Fallback if process info missing
            title = getattr(psi1_finding, "title", "")
            if title:
                med_conf.append(f"{title} (PSI1).")
            else:
                med_conf.append("Process selection mismatch requires validation (PSI1).")
    
    # Add other MEDIUM findings (excluding PSI1 if already added)
    for f in med_findings:
        if len(med_conf) >= 3:  # Process more, then deduplicate
            break
        fid = getattr(f, "id", "")
        if fid == "PSI1":
            continue  # Already added
        
        title = getattr(f, "title", "")
        recommendation = getattr(f, "recommendation", "")
        
        if title:
            if recommendation:
                rec_first = recommendation.split(".")[0].strip()
                if rec_first:
                    bullet = f"{rec_first} ({fid})." if fid else f"{rec_first}."
                else:
                    bullet = f"{title} ({fid})." if fid else f"{title}."
            else:
                bullet = f"{title} ({fid})." if fid else f"{title}."
            med_conf.append(bullet)
    
    # Deduplicate medium confidence bullets
    med_conf = _deduplicate_bullets(med_conf)[:2]
    
    # Low confidence bullets: uncertainty about geometry, economics, tooling (NOT missing inputs)
    # Only add if there's genuine uncertainty, not just missing inputs
    
    # Uncertainty about geometry (if geometry is partially unknown but not completely missing)
    if part and _has_critical_unknown(part):
        # Only add if some fields are unknown (uncertainty), not if completely missing
        low_conf.append("Geometry analysis based on summary bins; feature-level detail uncertain.")
    
    # Uncertainty about economics (if process mismatch exists but not severe)
    if inputs and proc_rec:
        user_selected = getattr(inputs, "process", None)
        primary = proc_rec.get("primary")
        scores = proc_rec.get("scores", {})
        if user_selected and primary and user_selected != primary:
            score_diff = scores.get(primary, 0) - scores.get(user_selected, 0)
            if 0 < score_diff < 3:  # Small mismatch - economic uncertainty
                low_conf.append("Process economics tradeoffs require volume and tooling validation.")
    
    # Uncertainty about tooling (if no sources but RAG was expected)
    rag_enabled = state.get("rag_enabled", False)
    if rag_enabled and not sources:
        low_conf.append("Tooling and machine constraints inferred from rules; shop-specific factors uncertain.")
    
    # Limit to 3 low confidence bullets
    low_conf = low_conf[:3]
    
    # Limitations: missing inputs only (short noun phrases)
    cad_present = _cad_is_present(state)
    if conf_inputs:
        if not conf_inputs.has_2d_drawing:
            # Only add when CAD not present; do not claim "No CAD" if STEP uploaded
            if not cad_present:
                limitations.append("No detailed CAD geometry provided")
                to_improve.append("Upload a 2D drawing (PDF/DXF) to increase confidence.")
        
        if conf_inputs and hasattr(conf_inputs, "step_scale_confirmed") and conf_inputs.step_scale_confirmed is False:
            limitations.append("STEP model scale not confirmed")
            to_improve.append("Confirm the STEP model represents real-world dimensions.")

    # CNC-only: numeric analysis failed/timeout - distinct from missing CAD
    inputs = state.get("inputs")
    process = getattr(inputs, "process", "") if inputs else ""
    if cad_present and process in ("CNC", "CNC_TURNING"):
        provider = state.get("part_metrics_provider") or ""
        mode = state.get("part_summary_mode") or "bins"
        if mode == "numeric" and provider in ("numeric_cnc_v1_failed", "numeric_cnc_v1_timeout"):
            limitations.append("Numeric CNC analysis unavailable (timeout/error); using bins")

    # Check for missing CAD feature-level geometry (only when CAD not present)
    if not cad_present and part and _has_critical_unknown(part):
        limitations.append("No detailed CAD geometry provided")
    
    # Check for missing numeric tolerances
    if inputs:
        tolerance_crit = getattr(inputs, "tolerance_criticality", "")
        if not tolerance_crit or tolerance_crit == "Low":
            # Only add if truly missing (not just low)
            pass  # Don't add for low tolerance criticality alone
    else:
        limitations.append("No numeric tolerances specified")
    
    # Missing tooling/machine constraints
    if not sources and not rag_enabled:
        limitations.append("Machine/tooling constraints unknown")
    
    # Remove duplicates and limit
    limitations = list(dict.fromkeys(limitations))[:4]
    to_improve = list(dict.fromkeys(to_improve))[:3]
    
    return {
        "high_confidence": high_conf,
        "medium_confidence": med_conf,
        "low_confidence": low_conf,
        "limitations": limitations,
        "to_improve": to_improve,
    }


def _is_generic_placeholder(text: str) -> bool:
    """Check if text is a generic placeholder (counts, generic language).
    
    Args:
        text: Text to check
        
    Returns:
        True if text appears to be a generic placeholder
    """
    text_lower = text.lower()
    
    # Angle brackets and placeholder patterns
    if "<" in text_lower or ">" in text_lower:
        return True
    if "assumpction" in text_lower:
        return True
    if re.search(r"<[^>]{0,30}>", text_lower):
        return True
    
    # Check for generic count patterns
    generic_patterns = [
        r"\d+\s+(high|medium|low)[-\s]severity\s+(issue|finding)",
        r"\d+\s+(finding|issue)[s]?\s+(identified|found)",
        r"identified\s+\d+\s+(finding|issue)",
        r"\d+\s+medium-severity\s+finding",
    ]
    for pattern in generic_patterns:
        if re.search(pattern, text_lower):
            return True
    
    # Check for generic placeholder keywords
    placeholder_keywords = ["todo", "tbd", "placeholder"]
    if any(kw in text_lower for kw in placeholder_keywords):
        return True
    
    # Check for very short or empty content
    stripped = re.sub(r"[^a-z0-9]", "", text_lower)
    if len(stripped) < 10:
        return True
    
    return False


def _normalize_confidence(data: dict, state: GraphState, base_score: float) -> tuple[Confidence, float]:
    """Normalize confidence with optional LLM adjustment (hybrid system).
    
    Args:
        data: Parsed LLM JSON (must contain llm_delta, llm_rationale, uncertainty_flags)
        state: GraphState
        base_score: Deterministic base score
        
    Returns:
        Tuple of (Confidence object, llm_delta applied)
    """
    # Extract LLM delta (required, must be in [-0.10, +0.10])
    llm_delta_raw = data.get("llm_delta")
    
    # Backward compatibility: also check for "delta" or compute from "score"
    if llm_delta_raw is None:
        llm_delta_raw = data.get("delta")
    
    if llm_delta_raw is None:
        # Legacy: compute delta from score if present
        llm_score = data.get("score")
        if llm_score is not None and isinstance(llm_score, (int, float)):
            llm_score_val = max(0.0, min(1.0, float(llm_score)))
            llm_delta_raw = llm_score_val - base_score
        else:
            llm_delta_raw = 0.0
    
    # Validate and clamp delta
    if isinstance(llm_delta_raw, (int, float)):
        llm_delta = max(-0.10, min(0.10, float(llm_delta_raw)))
    else:
        llm_delta = 0.0
    
    # Apply deterministic flag adjustments first
    uncertainty_flags_raw = data.get("uncertainty_flags", [])
    if isinstance(uncertainty_flags_raw, list):
        uncertainty_flags_for_adj = [str(x).strip() for x in uncertainty_flags_raw if str(x).strip()][:8]
    else:
        uncertainty_flags_for_adj = []
    
    adjusted_base, _ = _apply_flag_adjustments(base_score, uncertainty_flags_for_adj, state)
    
    # Compute final confidence: clamp(adjusted_base + llm_delta, 0.30..0.95)
    final_confidence = adjusted_base + llm_delta
    final_confidence = max(0.30, min(0.95, final_confidence))
    final_confidence = round(final_confidence, 2)
    
    # Extract LLM rationale (3-5 items)
    llm_rationale_raw = data.get("llm_rationale", [])
    if isinstance(llm_rationale_raw, list):
        llm_rationale = [str(x).strip() for x in llm_rationale_raw if str(x).strip()][:5]
        # Ensure 3-5 items, pad if needed
        while len(llm_rationale) < 3 and len(llm_rationale) < 5:
            llm_rationale.append("Baseline confidence assessment is appropriate.")
            if len(llm_rationale) >= 5:
                break
        llm_rationale = llm_rationale[:5]
    else:
        llm_rationale = []
    
    # Extract uncertainty flags (max 8) - already parsed above
    if isinstance(uncertainty_flags_raw, list):
        uncertainty_flags = [str(x).strip() for x in uncertainty_flags_raw if str(x).strip()][:8]
    else:
        uncertainty_flags = []
    # CNC-only: remove missing_cad and geometry_uncertain when CAD is present
    cad_present = _cad_is_present(state)
    conf_inputs = state.get("confidence_inputs")
    step_explicitly_unconfirmed = (
        conf_inputs is not None
        and hasattr(conf_inputs, "step_scale_confirmed")
        and conf_inputs.step_scale_confirmed is False
    )
    exclude: set[str] = set()
    if cad_present:
        exclude |= {"missing_cad", "geometry_uncertain"}
    if not step_explicitly_unconfirmed:
        exclude.add("step_scale_unconfirmed")
    if exclude:
        uncertainty_flags = [f for f in uncertainty_flags if str(f).strip().lower() not in exclude]
    # Add numeric_analysis_failed/timeout when CAD present but analysis failed
    if cad_present:
        inputs = state.get("inputs")
        process = getattr(inputs, "process", "") if inputs else ""
        if process in ("CNC", "CNC_TURNING"):
            provider = state.get("part_metrics_provider") or ""
            mode = state.get("part_summary_mode") or "bins"
            if mode == "numeric" and provider in ("numeric_cnc_v1_failed", "numeric_cnc_v1_timeout"):
                flag = "numeric_analysis_timeout" if "timeout" in provider else "numeric_analysis_failed"
                existing = {str(f).strip().lower() for f in uncertainty_flags}
                if flag not in existing and len(uncertainty_flags) < 8:
                    uncertainty_flags.append(flag)

    # Extract text lists from LLM (or use deterministic fallback)
    list_keys = ("high_confidence", "medium_confidence", "low_confidence", "limitations", "to_improve")
    
    # Use LLM text lists if present and valid, otherwise use deterministic
    deterministic_texts = _generate_deterministic_confidence_texts(state)
    
    # Get deterministic texts for fallback and deduplication reference
    det_limitations_norms = {_normalize_for_dedup(lim) for lim in deterministic_texts.get("limitations", [])}
    
    out: dict[str, Any] = {
        "deterministic_confidence": base_score,
        "llm_delta": llm_delta,
        "final_confidence": final_confidence,
        "score": final_confidence,  # Legacy compatibility
        "llm_rationale": llm_rationale,
        "uncertainty_flags": uncertainty_flags,
    }
    
    for k in list_keys:
        val = data.get(k)
        if isinstance(val, list) and val:
            # Filter out generic placeholders from LLM-generated text
            filtered = [str(x) for x in val if not _is_generic_placeholder(str(x))]
            
            # Deduplicate LLM-generated bullets
            if k in ("high_confidence", "medium_confidence", "low_confidence"):
                filtered = _deduplicate_bullets(filtered)
            
            # Remove items that duplicate Limitations content
            if k in ("high_confidence", "medium_confidence", "low_confidence"):
                filtered = [
                    item for item in filtered
                    if _normalize_for_dedup(item) not in det_limitations_norms
                ]
            
            # Apply limits
            max_items = 2 if k == "high_confidence" or k == "medium_confidence" else (3 if k == "low_confidence" else (4 if k == "limitations" else 3))
            filtered = filtered[:max_items]
            
            # If filtering removed all items or too few remain, use deterministic fallback
            if len(filtered) < max_items:
                # Merge: use filtered LLM items + fill from deterministic
                deterministic_items = deterministic_texts.get(k, [])
                # Combine without duplicates
                combined = filtered.copy()
                combined_norms = {_normalize_for_dedup(item) for item in combined}
                
                for det_item in deterministic_items:
                    if len(combined) >= max_items:
                        break
                    det_norm = _normalize_for_dedup(det_item)
                    # Avoid duplicates and items that duplicate Limitations
                    if det_norm not in combined_norms and det_norm not in det_limitations_norms:
                        combined.append(det_item)
                        combined_norms.add(det_norm)
                
                out[k] = combined[:max_items]
            else:
                out[k] = filtered
        else:
            # Use deterministic fallback
            out[k] = deterministic_texts.get(k, [])

    # CNC-only: filter to_improve when CAD+metrics present (no "attach numeric analysis")
    if _numeric_metrics_present(state):
        to_improve = out.get("to_improve", []) or []
        out["to_improve"] = [x for x in to_improve if not _to_improve_suggests_numeric(x)]

    return (Confidence(**out), llm_delta)


def self_review_node(state: GraphState) -> dict:
    # Compute deterministic base score first
    base_score = _base_confidence_score(state)
    trace_delta = [f"self_review: confidence_base={base_score} source=deterministic"]
    trace_delta.append(f"self_review: cad_uploaded={'y' if cad_uploaded(state) else 'n'} cad_status={cad_analysis_status(state)}")

    llm_mode = (os.getenv("LLM_MODE") or getattr(CONFIG, "llm_mode", "remote")).strip().lower()
    # Offline = no cloud; local/hybrid can still use Ollama. Only skip LLM when offline AND remote-only.
    skip_llm = _offline_enabled() and llm_mode == "remote"
    if skip_llm:
        trace_delta.append("self_review: offline mode (remote only) -> deterministic only")
        deterministic_texts = _generate_deterministic_confidence_texts(state)
        confidence = Confidence(
            deterministic_confidence=base_score,
            llm_delta=0.0,
            final_confidence=base_score,
            score=base_score,  # Legacy compatibility
            llm_rationale=[],
            uncertainty_flags=[],
            high_confidence=deterministic_texts["high_confidence"],
            medium_confidence=deterministic_texts["medium_confidence"],
            low_confidence=deterministic_texts["low_confidence"],
            limitations=deterministic_texts["limitations"],
            to_improve=deterministic_texts["to_improve"],
        )
        return {
            "trace": trace_delta,
            "confidence": confidence,
            "usage_by_node": {"self_review": {"attempts": 0, "cache_hit": False}},
        }
    
    # Try LLM for optional adjustment and text lists
    system_tmpl = _read_text(_PROMPTS_DIR / "self_review_system.txt")
    user_payload = _build_user_payload(state)
    # llm_mode already set above (runtime env respected)

    user_msg = (
        "Return ONLY valid JSON. No markdown. No extra keys. Output must start with { and end with }.\n\n"
        + user_payload
    )

    def _invoke_local() -> str:
        """Invoke Ollama for self-review."""
        client = OllamaClient(
            base_url=CONFIG.ollama_base_url,
            model=CONFIG.ollama_model,
            timeout_seconds=CONFIG.llm_timeout_seconds,
        )
        messages = [
            {"role": "system", "content": system_tmpl},
            {"role": "user", "content": user_msg},
        ]
        options = {
            "temperature": 0.1,  # Low but not 0 to reduce template echoes
            "num_ctx": 2048,
            "num_predict": 320,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "stop": ["```", "###", "Here is", "Key Observations:"],
        }
        return client.chat(messages, options=options).strip()

    def _invoke_remote() -> str:
        """Invoke OpenAI for self-review."""
        llm = ChatOpenAINoTemperature(model=CONFIG.model_name, temperature=0.0)
        resp = llm.invoke(
            [
                {"role": "system", "content": system_tmpl},
                {"role": "user", "content": user_msg},
            ]
        )
        return resp.content.strip() if hasattr(resp, "content") else str(resp)

    def _invoke_local_with_parse_validation() -> dict:
        """Call local, parse JSON, validate required keys. Raises ValueError if invalid."""
        raw = _invoke_local()
        parsed = _parse_json(raw)
        if parsed is None:
            raise ValueError("Local LLM output could not be parsed as JSON")
        if not _validate_llm_json_required(parsed):
            raise ValueError("Local LLM output missing required keys (llm_delta, llm_rationale, uncertainty_flags)")
        return parsed

    parsed = None
    attempts = 0
    provider_used = None
    max_attempts_val = CONFIG.retry_max_attempts if CONFIG.enable_retry else 1

    try:
        if llm_mode == "local":
            raw, attempts = run_with_retries(
                "self_review",
                _invoke_local,
                max_attempts_val,
                logger,
                backoff_seconds=CONFIG.retry_backoff_seconds,
            )
            parsed = _parse_json(raw)
            if parsed is not None and not _validate_llm_json_required(parsed):
                parsed = None  # Treat as invalid, fall back to deterministic
            provider_used = "ollama"
        elif llm_mode == "hybrid":
            try:
                parsed, attempts = run_with_retries(
                    "self_review (local)",
                    _invoke_local_with_parse_validation,
                    max_attempts_val,
                    logger,
                    backoff_seconds=CONFIG.retry_backoff_seconds,
                )
                provider_used = "ollama"
            except Exception as e:
                logger.warning(f"Self-review local LLM failed ({e}); falling back to remote (single call)")
                raw = _invoke_remote()
                parsed = _parse_json(raw)
                if parsed is not None and not _validate_llm_json_required(parsed):
                    parsed = None
                attempts = max_attempts_val + 1  # local retries + 1 remote
                provider_used = "openai"
        else:  # remote
            raw, attempts = run_with_retries(
                "self_review",
                _invoke_remote,
                max_attempts_val,
                logger,
                backoff_seconds=CONFIG.retry_backoff_seconds,
            )
            parsed = _parse_json(raw)
            if parsed is not None and not _validate_llm_json_required(parsed):
                parsed = None
            provider_used = "openai"
    except Exception as e:
        attempts = max_attempts_val  # Retries exhausted
        # LLM failed, use deterministic-only (llm_delta=0)
        logger.warning(f"Self-review LLM failed ({e}); using deterministic confidence only")
        deterministic_texts = _generate_deterministic_confidence_texts(state)
        confidence = Confidence(
            deterministic_confidence=base_score,
            llm_delta=0.0,
            final_confidence=base_score,
            score=base_score,  # Legacy compatibility
            llm_rationale=[],
            uncertainty_flags=[],
            high_confidence=deterministic_texts["high_confidence"],
            medium_confidence=deterministic_texts["medium_confidence"],
            low_confidence=deterministic_texts["low_confidence"],
            limitations=deterministic_texts["limitations"],
            to_improve=deterministic_texts["to_improve"],
        )
        return {
            "trace": trace_delta,
            "confidence": confidence,
            "usage_by_node": {"self_review": {"attempts": attempts, "cache_hit": False}},
        }

    usage_node = {"attempts": attempts, "cache_hit": False}
    trace_delta.append("Performed self-critique and confidence scoring")

    if parsed is None:
        # LLM JSON invalid, use deterministic-only (llm_delta=0)
        deterministic_texts = _generate_deterministic_confidence_texts(state)
        confidence = Confidence(
            deterministic_confidence=base_score,
            llm_delta=0.0,
            final_confidence=base_score,
            score=base_score,  # Legacy compatibility
            llm_rationale=[],
            uncertainty_flags=[],
            high_confidence=deterministic_texts["high_confidence"],
            medium_confidence=deterministic_texts["medium_confidence"],
            low_confidence=deterministic_texts["low_confidence"],
            limitations=deterministic_texts["limitations"],
            to_improve=deterministic_texts["to_improve"],
        )
        return {"trace": trace_delta, "confidence": confidence, "usage_by_node": {"self_review": usage_node}}

    try:
        confidence, llm_delta_applied = _normalize_confidence(parsed, state, base_score)
        # Trace breakdown: flag adjustments and final computation
        flags = confidence.uncertainty_flags or []
        _, adjustments = _apply_flag_adjustments(base_score, flags, state)
        adj_str = ", ".join([f"{k}{v:+.2f}" for k, v in adjustments]) if adjustments else "none"
        trace_delta.append(f"self_review: flag_adjustments={adj_str}")
        adjusted_base = base_score + sum(v for _, v in adjustments)
        adjusted_base = max(0.0, min(1.0, adjusted_base))
        trace_delta.append(
            f"self_review: adjusted_base={adjusted_base:.2f} llm_delta={llm_delta_applied:+.2f} "
            f"final={confidence.final_confidence:.2f}"
        )
    except Exception as e:
        logger.error("Self-review confidence validation failed: %s", e, exc_info=True)
        # Fallback to deterministic-only (llm_delta=0)
        deterministic_texts = _generate_deterministic_confidence_texts(state)
        confidence = Confidence(
            deterministic_confidence=base_score,
            llm_delta=0.0,
            final_confidence=base_score,
            score=base_score,  # Legacy compatibility
            llm_rationale=[],
            uncertainty_flags=[],
            high_confidence=deterministic_texts["high_confidence"],
            medium_confidence=deterministic_texts["medium_confidence"],
            low_confidence=deterministic_texts["low_confidence"],
            limitations=deterministic_texts["limitations"],
            to_improve=deterministic_texts["to_improve"],
        )
        return {
            "trace": trace_delta,
            "confidence": confidence,
            "usage_by_node": {"self_review": usage_node},
        }
    
    return {"trace": trace_delta, "confidence": confidence, "usage_by_node": {"self_review": usage_node}}
