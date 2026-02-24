from __future__ import annotations

import re

from agent.geometry.cad_presence import cad_analysis_status, cad_evidence_available, cad_uploaded
from agent.nodes.process_selection import CANDIDATES
from agent.state import Finding, GraphState


# Known duplicate ID pairs (explicit mappings)
DUPLICATE_ID_PAIRS = {
    ("DFM9", "TURN3"),
    ("TURN3", "DFM9"),
}


def _norm_title(t: str) -> str:
    """Normalize title: lowercase, remove punctuation, collapse spaces."""
    t = t.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _token_set(t: str) -> set[str]:
    """Extract token set from normalized title."""
    return set(_norm_title(t).split())


def _jaccard(a: set[str], b: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def _severity_rank(sev: str) -> int:
    """Rank severity: HIGH=3, MEDIUM=2, LOW=1, else 0."""
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(sev, 0)


def _merge_findings(findings: list[Finding]) -> tuple[list[Finding], dict[str, list[Finding]]]:
    """
    Merge duplicate/near-duplicate findings.
    Returns: (primary_findings, merged_map) where merged_map[primary_id] = list of duplicates.
    """
    primary_findings: list[Finding] = []
    merged_map: dict[str, list[Finding]] = {}

    for f in findings:
        matched = False
        for p in primary_findings:
            # Check explicit ID pair mapping
            if (p.id, f.id) in DUPLICATE_ID_PAIRS or (f.id, p.id) in DUPLICATE_ID_PAIRS:
                merged_map[p.id].append(f)
                matched = True
                break

            # Check same severity and title similarity
            if p.severity == f.severity:
                norm_p = _norm_title(p.title)
                norm_f = _norm_title(f.title)
                # Substring match
                if norm_p in norm_f or norm_f in norm_p:
                    merged_map[p.id].append(f)
                    matched = True
                    break
                # Token Jaccard similarity
                tokens_p = _token_set(p.title)
                tokens_f = _token_set(f.title)
                if _jaccard(tokens_p, tokens_f) >= 0.75:
                    merged_map[p.id].append(f)
                    matched = True
                    break

        if not matched:
            primary_findings.append(f)
            merged_map[f.id] = []

    return primary_findings, merged_map


def _conf_dict(conf):  # Confidence model or dict
    if conf is None:
        return {}
    if hasattr(conf, "model_dump") and callable(conf.model_dump):
        return conf.model_dump()
    return conf if isinstance(conf, dict) else {}


def should_suggest_prototype_am(inp, part, findings: list[Finding]) -> bool:
    """
    Deterministic gating for prototype 3D-print suggestion.
    Trigger when volume indicates low/early stage AND (feature complexity or risk or existing findings).
    Does not change primary/secondary selection; report-only recommendation.
    """
    if inp is None:
        return False
    volume = getattr(inp, "production_volume", "") or ""
    # Volume rule: low/prototype intent
    low_volume = volume in ("Proto", "Small batch", "Small", "Low", "One-off")
    if not low_volume:
        return False
    # At least one of: feature variety, accessibility risk, or existing MED/HIGH finding
    part_ok = False
    if part is not None:
        fv = getattr(part, "feature_variety", "") or ""
        ar = getattr(part, "accessibility_risk", "") or ""
        if fv in ("Medium", "High") or ar in ("Medium", "High"):
            part_ok = True
    has_med_high = any(getattr(f, "severity", "") in ("MEDIUM", "HIGH") for f in (findings or []))
    return part_ok or has_med_high


def _coerce_cnc_metrics(part_metrics: dict) -> dict:
    """Normalize CNC numeric metric types for correct rendering (CNC-only).
    
    - thin_wall_flag -> bool
    - faces, edges -> int
    - tool_access_proxy -> float (2 decimals)
    - bounding_box_mm -> list[float] (3 values, 2 decimals each)
    """
    if not isinstance(part_metrics, dict):
        return part_metrics
    out = dict(part_metrics)
    if "thin_wall_flag" in out and out["thin_wall_flag"] is not None:
        v = out["thin_wall_flag"]
        out["thin_wall_flag"] = bool(v) if isinstance(v, (bool, int, float)) else v
    for k in ("faces", "edges"):
        if k in out and out[k] is not None:
            v = out[k]
            if isinstance(v, (int, float)):
                out[k] = int(round(v))
    if "tool_access_proxy" in out and out["tool_access_proxy"] is not None:
        v = out["tool_access_proxy"]
        if isinstance(v, (int, float)):
            out["tool_access_proxy"] = round(float(v), 2)
    if "bounding_box_mm" in out and out["bounding_box_mm"] is not None:
        v = out["bounding_box_mm"]
        if isinstance(v, (list, tuple)) and len(v) >= 3:
            out["bounding_box_mm"] = [
                round(float(v[0]), 2),
                round(float(v[1]), 2),
                round(float(v[2]), 2),
            ]
    return out


def report_node(state: GraphState) -> dict:
    # Report-time visibility: check process_recommendation presence
    has_proc = isinstance(state.get("process_recommendation"), dict)
    primary = (state.get("process_recommendation") or {}).get("primary") if has_proc else None
    
    findings = state.get("findings", [])
    actions = state.get("actions", [])
    assumptions = state.get("assumptions", [])
    usage = state.get("usage", {})

    # Merge duplicate/near-duplicate findings
    primary_findings, merged_map = _merge_findings(findings)

    # Report-only fallbacks (do not mutate graph state)
    inp = state.get("inputs")
    process = getattr(inp, "process", None) if inp else None
    process = process or "CNC"
    
    has_high_or_med = any(f.severity in ("HIGH", "MEDIUM") for f in findings)
    if not actions:
        if process == "INJECTION_MOLDING":
            if has_high_or_med:
                actions = [
                    "Address HIGH and MEDIUM findings before tooling commitment.",
                    "Validate draft angles, wall thickness uniformity, and gate/vent locations.",
                    "Plan for shrinkage/warpage compensation and cooling channel design.",
                    "Ensure 2D drawing with GD&T is available for tooling quotes.",
                    "Confirm resin grade selection matches performance requirements.",
                ]
            else:
                actions = [
                    "Review IM design guidelines: draft angles, wall thickness, ribs/bosses.",
                    "Plan tooling ROI analysis for production volume.",
                    "Consider gate/vent/cooling design early in tooling discussion.",
                    "Validate resin selection for application requirements.",
                ]
        else:
            if has_high_or_med:
                actions = [
                    "Address HIGH and MEDIUM findings before release.",
                    "Apply recommended design changes for critical features.",
                    "Re-verify tolerances and interfaces after changes.",
                ]
            else:
                actions = [
                    "No blocking issues; optional improvements may apply.",
                    "Review LOW findings for incremental improvements.",
                    "Confirm part meets functional requirements.",
                ]
    if not assumptions:
        if process == "INJECTION_MOLDING":
            assumptions = [
                "Injection molding process intent is confirmed.",
                "Tooling exists or will be quoted based on design.",
                "Resin grade selection is TBD or as specified.",
                "Draft angles and wall thickness uniformity not validated without CAD review.",
            ]
        else:
            process_val = getattr(inp, "process", None) if inp else None
            if process_val == "AUTO":
                assumptions = [
                    "Inputs and part summary reflect current design intent.",
                    "Manufacturing process was auto-selected based on geometry and inputs.",
                ]
            else:
                assumptions = [
                    "Inputs and part summary reflect current design intent.",
                    "Manufacturing process and material choices are as specified.",
                ]

    def fmt_findings(sev: str) -> str:
        items = [f for f in primary_findings if f.severity == sev]
        if not items:
            return "_None_\n"
        lines = []
        for f in items:
            line = f"- **{f.title}** ({f.id}) — {f.why_it_matters}\n  - Recommendation: {f.recommendation}"
            # Add evidence if present
            ev = getattr(f, "evidence", None)
            if ev and isinstance(ev, dict):
                parts = []
                for k, v in ev.items():
                    if k == "bounding_box_mm" and isinstance(v, (list, tuple)) and len(v) >= 3:
                        parts.append(f"bounding_box_mm={v[0]:.1f}x{v[1]:.1f}x{v[2]:.1f}")
                    elif isinstance(v, (int, float)):
                        parts.append(f"{k}={round(float(v), 2)}")
                    else:
                        parts.append(f"{k}={v}")
                line += f"\n  - Evidence: {', '.join(parts)}"
            # Add proposal if present (Phase 3: CNC numeric)
            prop = getattr(f, "proposal", None)
            if prop and isinstance(prop, str) and prop.strip():
                line += f"\n  - Proposal: {prop.strip()}"
            steps = getattr(f, "proposal_steps", None)
            if steps and isinstance(steps, list) and steps:
                line += "\n  - Proposal steps:"
                for s in steps[:5]:
                    if s and isinstance(s, str) and s.strip():
                        line += f"\n    - {s.strip()}"
            # Add merged items if any
            merged = merged_map.get(f.id, [])
            if merged:
                related_titles = [f"{m.id}: {m.title[:50]}" for m in merged[:3]]
                line += f"\n  - Related: {'; '.join(related_titles)}"
            lines.append(line)
        return "\n".join(lines) + "\n"

    md = []
    md.append("# CNC Design Review + DFM Report\n")

    inputs = state.get("inputs")
    part = state.get("part_summary")

    md.append("## Input summary\n")
    if inputs:
        process = getattr(inputs, "process", None) or "CNC"
        proc_rec = state.get("process_recommendation") or {}
        primary = proc_rec.get("primary")
        
        if process == "AUTO" and primary:
            md.append(f"- Manufacturing process: AUTO\n")
            md.append(f"- Recommended process: {primary}\n")
        else:
            md.append(f"- Manufacturing process: {process}\n")
        md.append(
            f"- Material: {inputs.material}\n"
            f"- Production volume: {inputs.production_volume}\n"
            f"- Load type: {inputs.load_type}\n"
            f"- Tolerance criticality: {inputs.tolerance_criticality}\n"
        )
    if part:
        md.append(
            f"- Part size: {part.part_size}\n"
            f"- Min internal radius: {part.min_internal_radius}\n"
            f"- Min wall thickness: {part.min_wall_thickness}\n"
            f"- Hole depth class: {part.hole_depth_class}\n"
            f"- Pocket aspect class: {part.pocket_aspect_class}\n"
            f"- Feature variety: {part.feature_variety}\n"
            f"- Accessibility risk: {part.accessibility_risk}\n"
            f"- Has clamping faces: {part.has_clamping_faces}\n"
        )

    # CAD presence (used for legacy surfacing: hide full scores when cad_status != ok)
    _cad_status = cad_analysis_status(state)
    md.append("\n## Process recommendation\n")
    proc_rec = state.get("process_recommendation") or state.get("process_recommendations")
    if proc_rec and isinstance(proc_rec, dict):
        primary = proc_rec.get("primary")
        if primary:
            md.append(f"- Primary: **{primary}**\n")
            sec = list(proc_rec.get("secondary", []))  # Make a copy to modify
            
            # Check for hybrid offer (HYBRID1 finding indicates hybrid_offer was active)
            has_hybrid_offer = any(f.id == "HYBRID1" for f in findings)
            hybrid_suitable_processes = {"CASTING", "FORGING", "MIM", "EXTRUSION", "THERMOFORMING", "COMPRESSION_MOLDING"}
            
            if has_hybrid_offer and primary in hybrid_suitable_processes:
                # Add CNC to secondary if not already present
                if "CNC" not in sec:
                    sec.append("CNC")
            
            # Format secondary for display (special case for THERMOFORMING); clarify meaning and optional close-call hint
            if sec:
                sec_display = []
                for s in sec:
                    if s == "CNC" and primary == "THERMOFORMING":
                        sec_display.append("CNC trim")
                    else:
                        sec_display.append(s)
                md.append(f"- Secondary (close alternatives): {', '.join(sec_display)}\n")
                md.append("- Note: Secondary processes are shown as alternative options. They may be less suitable than the primary unless the scores are close.\n")
                # Optional close-call hint when scores available
                scores = proc_rec.get("scores") or {}
                if isinstance(scores, dict) and primary:
                    primary_score = scores.get(primary, 0)
                    top_sec_score = max(scores.get(s, 0) for s in sec) if sec else 0
                    score_diff = primary_score - top_sec_score
                    if abs(score_diff) <= 1:
                        md.append("- Close call: scores were within 1 point(s). Review feasibility details (tooling, flat pattern, setups).\n")
                    elif score_diff <= 2:
                        md.append("- Close call: scores were within 2 point(s). Review feasibility details (tooling, flat pattern, setups).\n")
                    else:
                        md.append("- These alternatives are not close to the primary score; shown for completeness.\n")
            else:
                md.append(f"- Secondary: None\n")
            if proc_rec.get("forced_primary") and "SHEET_METAL" in (sec or []):
                md.append("- Note: SHEET_METAL scored higher, but CNC was selected due to insufficient strong sheet-metal evidence. Review sheet feasibility (bends, flat pattern, tooling).\n")
            nr = proc_rec.get("not_recommended", [])
            md.append(f"- Less suitable (given current inputs): {', '.join(nr) if nr else 'None'}\n")
            # Not applicable (hard gated): list gated-out processes with reasons
            process_gates = proc_rec.get("process_gates") or {}
            eligible_set = set(proc_rec.get("eligible_processes") or [])
            gated_out = [(p, (process_gates.get(p) or {}).get("reason", "not applicable")) for p in CANDIDATES if p not in eligible_set]
            if gated_out:
                gated_str = ", ".join(f"{p} ({r})" for p, r in gated_out[:6])
                md.append(f"- Not applicable (hard gated): {gated_str}\n")
            
            # Split reasons into Primary vs Secondary rationale if secondary exists
            reasons_primary = proc_rec.get("reasons_primary")
            reasons_secondary = proc_rec.get("reasons_secondary")
            reasons = proc_rec.get("reasons", [])
            
            if reasons_primary is not None and reasons_secondary is not None:
                # Use explicit split if provided
                if reasons_primary:
                    md.append("- Primary rationale:\n")
                    for r in reasons_primary:
                        md.append(f"  - {r}\n")
                if reasons_secondary:
                    md.append("- Secondary rationale:\n")
                    for r in reasons_secondary:
                        md.append(f"  - {r}\n")
            elif sec and reasons:
                # Fallback: split existing reasons by keywords
                primary_reasons = []
                secondary_reasons = []
                for r in reasons:
                    r_lower = r.lower()
                    if any(kw in r_lower for kw in ("proto volume", "low volume", "prototype", "small batch")):
                        secondary_reasons.append(r)
                    else:
                        primary_reasons.append(r)
                if primary_reasons:
                    md.append("- Primary rationale:\n")
                    for r in primary_reasons:
                        md.append(f"  - {r}\n")
                if secondary_reasons:
                    md.append("- Secondary rationale:\n")
                    for r in secondary_reasons:
                        md.append(f"  - {r}\n")
            elif reasons:
                # Backward compatible: no secondary, show single "Reasons" section
                md.append("- Reasons:\n")
                for r in reasons:
                    md.append(f"  - {r}\n")
            tradeoffs = proc_rec.get("tradeoffs", [])
            if tradeoffs:
                md.append("- Tradeoffs:\n")
                for t in tradeoffs:
                    md.append(f"  - {t}\n")
            # Legacy surfacing: show full scores only when cad_status==ok (numeric path)
            scores = proc_rec.get("scores", {})
            if isinstance(scores, dict) and _cad_status == "ok":
                parts = [f"{k}={scores.get(k, 0)}" for k in sorted(CANDIDATES)]
                md.append(f"- Scores: {', '.join(parts)}\n")
        else:
            md.append("_Not available._\n")
    elif proc_rec:
        md.append(f"_Process recommendation present but invalid type: {type(proc_rec)}_\n")
    else:
        md.append("_Not available._\n")
    md.append("\n")

    if should_suggest_prototype_am(inputs, part, findings):
        md.append("## Prototype path (optional)\n")
        md.append("\n")
        md.append("- Use for fit/form checks and assembly validation before committing to CNC/tooling.\n")
        md.append("- Not a substitute for final tolerances/surface finish—plan CNC/inspection for critical interfaces.\n")
        md.append("- Helps reduce iteration cost and catch design issues early.\n")
        md.append("\n")

    md.append("## Manufacturing confidence inputs\n")
    # CAD presence (authoritative; never claim "No CAD" when uploaded)
    cad_up = cad_uploaded(state)
    cad_status = _cad_status
    cad_ev_used = cad_evidence_available(state)
    md.append(f"- CAD uploaded: {'yes' if cad_up else 'no'}\n")
    md.append(f"- CAD analysis status: {cad_status}\n")
    md.append(f"- CAD evidence used in rules: {'yes' if cad_ev_used else 'no'}\n")
    # CAD Lite: read from process_recommendation (wired by process_selection)
    proc_rec_conf = state.get("process_recommendation") or {}
    cad_lite = proc_rec_conf.get("cad_lite") or state.get("cad_lite")
    cad_lite_status = cad_lite.get("status", "none") if isinstance(cad_lite, dict) else "none"
    md.append(f"- CAD Lite analysis: {cad_lite_status}\n")
    ext_lite = proc_rec_conf.get("extrusion_lite") or state.get("extrusion_lite")
    ext_lite_status = ext_lite.get("status", "none") if isinstance(ext_lite, dict) else "none"
    md.append(f"- Extrusion Lite analysis: {ext_lite_status}\n")
    ext_lh = proc_rec_conf.get("extrusion_likelihood") or state.get("extrusion_likelihood")
    if isinstance(ext_lh, dict) and ext_lh.get("level") is not None:
        md.append(f"- Extrusion likelihood: {ext_lh.get('level')}" + (f" (source={ext_lh.get('source')})" if ext_lh.get("source") else "") + "\n")
    else:
        md.append("- Extrusion likelihood: none\n")
    sm_lh = proc_rec_conf.get("sheet_metal_likelihood") or state.get("sheet_metal_likelihood")
    if isinstance(sm_lh, dict):
        lvl = sm_lh.get("level")
        src = sm_lh.get("source")
        if lvl is not None:
            md.append(f"- Sheet metal likelihood: {lvl}" + (f" (source={src})" if src else "") + "\n")
    elif sm_lh is not None:
        md.append(f"- Sheet metal likelihood: {sm_lh}\n")
    conf_inputs = state.get("confidence_inputs")
    if conf_inputs is None:
        md.append("_Confidence inputs not provided._\n")
    else:
        has_2d = conf_inputs.get("has_2d_drawing", False) if isinstance(conf_inputs, dict) else bool(getattr(conf_inputs, "has_2d_drawing", False))
        scale_ok = conf_inputs.get("step_scale_confirmed", True) if isinstance(conf_inputs, dict) else bool(getattr(conf_inputs, "step_scale_confirmed", True))
        turning_support = conf_inputs.get("turning_support_confirmed", False) if isinstance(conf_inputs, dict) else bool(getattr(conf_inputs, "turning_support_confirmed", False))
        md.append(f"- 2D drawing provided: {'✅' if has_2d else '❌'}\n")
        md.append(f"- STEP scale confirmed: {'✅' if scale_ok else '❌'}\n")
        md.append(f"- Turning support confirmed: {'✅' if turning_support else '❌'}\n")
    cad_metrics = state.get("cad_metrics") or {}
    ld_ratio = cad_metrics.get("turning_ld_ratio")
    if ld_ratio is not None:
        md.append(f"- Turning L/D ratio (proxy): {ld_ratio}\n")
    md.append("\n")

    # Numeric CNC Geometry Analysis section (CNC/CNC_TURNING only)
    # Render only if provider is numeric_cnc_v1 (not _failed/_timeout) and metrics valid
    process_val = getattr(inp, "process", None) if inp else None
    part_metrics_provider = state.get("part_metrics_provider") or ""
    part_metrics_raw = state.get("part_metrics")
    part_metrics = _coerce_cnc_metrics(part_metrics_raw) if part_metrics_raw else None
    _required_numeric_keys = frozenset({"bounding_box_mm", "volume_mm3", "surface_area_mm2"})
    _metrics_valid = (
        isinstance(part_metrics, dict)
        and part_metrics
        and _required_numeric_keys <= part_metrics.keys()
    )
    _provider_ok = (
        part_metrics_provider == "numeric_cnc_v1"
        and "_failed" not in part_metrics_provider
        and "_timeout" not in part_metrics_provider
    )
    if process_val in ("CNC", "CNC_TURNING") and _provider_ok and _metrics_valid:
        md.append("## Numeric CNC Geometry Analysis\n")
        for k, v in part_metrics.items():
            if v is not None:
                if k == "bounding_box_mm" and isinstance(v, (list, tuple)) and len(v) >= 3:
                    md.append(f"- {k}: {float(v[0]):.2f}x{float(v[1]):.2f}x{float(v[2]):.2f}\n")
                elif k == "tool_access_proxy" and isinstance(v, (int, float)):
                    md.append(f"- {k} (lower is better): {round(float(v), 2)}\n")
                elif k == "thin_wall_flag":
                    md.append(f"- {k}: {bool(v)}\n")
                elif k in ("faces", "edges") and isinstance(v, (int, float)):
                    md.append(f"- {k}: {int(round(v))}\n")
                elif isinstance(v, (int, float)):
                    fv = float(v)
                    md.append(f"- {k}: {int(fv) if fv == int(fv) else round(fv, 2)}\n")
                else:
                    md.append(f"- {k}: {v}\n")
        md.append("\n")
    elif process_val in ("CNC", "CNC_TURNING") and part_metrics_provider in ("numeric_cnc_v1_failed", "numeric_cnc_v1_timeout"):
        reason = "timeout" if "timeout" in part_metrics_provider else "error"
        md.append(f"- Numeric CNC analysis unavailable ({reason}), used bins.\n\n")

    # Detected CNC features (Phase 4): always visible for CNC+numeric mode
    part_summary_mode = state.get("part_summary_mode") or "bins"
    if process_val in ("CNC", "CNC_TURNING") and part_summary_mode == "numeric":
        md.append("## Detected CNC features\n")
        part_features = state.get("part_features")
        if part_features is not None and isinstance(part_features, dict):
            _feat_keys = ("hole_count", "hole_max_ld", "hole_max_depth_mm", "hole_diameters_mm", "pocket_count", "pocket_max_aspect", "pocket_max_depth_mm")
            _defaults = {"hole_count": 0, "hole_max_ld": 0, "hole_max_depth_mm": 0, "hole_diameters_mm": [], "pocket_count": 0, "pocket_max_aspect": 0, "pocket_max_depth_mm": 0}
            for k in _feat_keys:
                v = part_features.get(k)
                if v is None:
                    v = _defaults.get(k, 0)
                if k in ("hole_count", "pocket_count"):
                    md.append(f"- {k}: {int(v)}\n")
                elif k == "hole_diameters_mm":
                    md.append(f"- {k}: {v}\n")
                elif isinstance(v, (int, float)):
                    md.append(f"- {k}: {int(v) if isinstance(v, float) and v == int(v) else round(float(v), 2)}\n")
                else:
                    md.append(f"- {k}: {v}\n")
            # Fallback proxies subsection when proxy keys exist
            _proxy_keys = ("hole_proxy_count", "hole_proxy_max_ld", "hole_proxy_max_depth_mm", "hole_proxy_diameters_mm", "pocket_proxy_count", "pocket_proxy_max_aspect", "pocket_proxy_max_depth_mm")
            has_proxies = any(k in part_features and part_features.get(k) is not None for k in _proxy_keys)
            if has_proxies:
                md.append("\n### Detected CNC features (fallback proxies)\n")
                for k in _proxy_keys:
                    v = part_features.get(k)
                    if v is not None:
                        if k in ("hole_proxy_count", "pocket_proxy_count"):
                            md.append(f"- {k}: {int(v)}\n")
                        elif k == "hole_proxy_diameters_mm":
                            md.append(f"- {k}: {v}\n")
                        elif isinstance(v, (int, float)):
                            md.append(f"- {k}: {int(v) if isinstance(v, float) and v == int(v) else round(float(v), 2)}\n")
                        else:
                            md.append(f"- {k}: {v}\n")
        else:
            md.append(f"Detected CNC features unavailable (numeric analysis {part_metrics_provider or 'none'}); using bins.\n")
        md.append("\n")

    # Top priorities: use refined list from refine node when present, else deterministic from findings
    refined_priorities = state.get("refined_priorities") or []
    md.append("## Top priorities\n")
    if refined_priorities:
        for p in refined_priorities[:6]:
            if p and isinstance(p, str) and p.strip():
                md.append(f"- {p.strip()}\n")
        md.append("\n")
    else:
        proc_rec_top = state.get("process_recommendation") or {}
        relevance_procs = {proc_rec_top.get("primary"), getattr(inp, "process", None) or "CNC"}
        relevance_procs.update(proc_rec_top.get("secondary") or [])
        relevance_procs.discard(None)
        _ECONOMICS_RULE_TO_PROCESS = {
            "IM1": "INJECTION_MOLDING", "MIM1": "MIM", "CAST1": "CASTING", "FORG1": "FORGING",
        }

        def _finding_relevant(f: Finding) -> bool:
            proc = _ECONOMICS_RULE_TO_PROCESS.get(f.id)
            if proc is None:
                return True
            return proc in relevance_procs

        if not primary_findings:
            md.append("_None_\n\n")
        else:
            relevant_findings = [f for f in primary_findings if _finding_relevant(f)]
            def _priority_key(f: Finding) -> tuple[int, int, int]:
                sev_rank = -_severity_rank(f.severity)
                cat_pref = 0 if f.category == "DESIGN_REVIEW" else 1
                stable_idx = relevant_findings.index(f)
                return (sev_rank, cat_pref, stable_idx)

            sorted_findings = sorted(relevant_findings, key=_priority_key)
            top_3 = sorted_findings[:3]
            if top_3:
                for f in top_3:
                    md.append(f"- [{f.severity}] {f.title} ({f.id})\n")
            else:
                md.append("_None_\n")
        md.append("\n")

    # Decision rationale (refine node, when close call)
    decision_rationale = state.get("decision_rationale")
    if decision_rationale and isinstance(decision_rationale, str) and decision_rationale.strip():
        md.append("## Decision rationale\n")
        md.append(decision_rationale.strip() + "\n\n")

    md.append("## Findings (HIGH)\n")
    md.append(fmt_findings("HIGH"))

    md.append("## Findings (MEDIUM)\n")
    md.append(fmt_findings("MEDIUM"))

    md.append("## Findings (LOW)\n")
    md.append(fmt_findings("LOW"))

    md.append("## Action Checklist\n")
    refined_actions = state.get("refined_action_checklist") or []
    if refined_actions:
        md.append("\n".join([f"- [ ] {a}" for a in refined_actions[:10] if a and isinstance(a, str) and a.strip()]) + "\n")
    elif actions:
        # Dedupe actions: remove similar items that begin with the same intent
        seen_intents = set()
        
        def _get_action_intent(action: str) -> str:
            """Extract intent keywords from action (first 3-4 significant words)."""
            words = action.lower().split()
            # Skip common prefixes
            skip_words = {"address", "review", "plan", "ensure", "confirm", "validate", "apply", "re-verify"}
            significant = [w for w in words[:6] if w not in skip_words and len(w) > 3]
            return " ".join(significant[:3]) if significant else action.lower()[:30]
        
        # Prioritize: HIGH findings first, then process mismatch decision step, then others
        high_finding_actions = []
        other_actions = []
        
        # Check for process mismatch (PSI1 finding)
        has_process_mismatch = any(f.id == "PSI1" for f in findings)
        primary_is_am = primary == "AM"
        user_selected = getattr(inp, "process", None) if inp else None
        
        for action in actions:
            intent = _get_action_intent(action)
            # Skip if intent already seen (dedupe)
            if intent in seen_intents:
                continue
            seen_intents.add(intent)
            
            # Categorize action
            action_lower = action.lower()
            if any(kw in action_lower for kw in ["high", "critical", "blocking", "severe"]):
                high_finding_actions.append(action)
            else:
                other_actions.append(action)
        
        # Build prioritized checklist
        prioritized_actions = []
        
        # 1. HIGH finding actions first
        prioritized_actions.extend(high_finding_actions)
        
        # 2. Process mismatch decision step (if applicable) - add before other actions
        if has_process_mismatch and primary_is_am and user_selected != "AM":
            decision_step = "Confirm if AM-only geometry (internal channels/lattice/conformal cooling) is truly required; otherwise CNC is simpler."
            # Check if similar decision step already exists
            has_similar_decision = any(
                "am-only geometry" in a.lower() or 
                ("confirm" in a.lower() and "cnc" in a.lower() and "simpler" in a.lower())
                for a in prioritized_actions
            )
            if not has_similar_decision:
                prioritized_actions.append(decision_step)
        
        # 3. Other actions
        prioritized_actions.extend(other_actions)
        
        # Filter out actions that incorrectly claim missing fields
        # Check part summary to see what's actually provided
        part_provided_fields = set()
        if part:
            categorical_fields = {
                "min_internal_radius": getattr(part, "min_internal_radius", None),
                "min_wall_thickness": getattr(part, "min_wall_thickness", None),
                "hole_depth_class": getattr(part, "hole_depth_class", None),
                "pocket_aspect_class": getattr(part, "pocket_aspect_class", None),
                "feature_variety": getattr(part, "feature_variety", None),
                "accessibility_risk": getattr(part, "accessibility_risk", None),
            }
            # Fields are considered "provided" if they have categorical values (not None, not "Unknown")
            for field_name, value in categorical_fields.items():
                if value and value != "Unknown":
                    part_provided_fields.add(field_name.replace("_", " "))
        
        # Filter out actions that incorrectly claim missing fields when they're actually provided
        filtered_actions = []
        for action in prioritized_actions:
            action_lower = action.lower()
            # Check if action claims a field is missing when it's actually provided
            claims_missing_incorrectly = False
            for field_name in part_provided_fields:
                # Check if action mentions this field and claims it's missing
                field_words = field_name.lower().split()
                if all(word in action_lower for word in field_words):
                    # Field is mentioned, check if action claims it's missing
                    missing_keywords = ["missing", "not provided", "unknown", "not available", "lacks", "without"]
                    if any(kw in action_lower for kw in missing_keywords):
                        claims_missing_incorrectly = True
                        break
            # Only include if it doesn't incorrectly claim missing fields
            if not claims_missing_incorrectly:
                filtered_actions.append(action)
        
        if filtered_actions:
            md.append("\n".join([f"- [ ] {a}" for a in filtered_actions]) + "\n")
        else:
            md.append("_No actions generated._\n")
    else:
        md.append("_No actions generated._\n")

    md.append("## Assumptions\n")
    if assumptions:
        md.append("\n".join([f"- {a}" for a in assumptions]) + "\n")
    else:
        md.append("_None_\n")

    md.append("## Usage (tokens & cost)\n")
    if usage:
        md.append(f"- prompt_tokens: {usage.get('prompt_tokens')}\n")
        md.append(f"- completion_tokens: {usage.get('completion_tokens')}\n")
        md.append(f"- total_tokens: {usage.get('total_tokens')}\n")
        md.append(f"- total_cost_usd: {usage.get('total_cost_usd')}\n\n")
        md.append("_Note: Cost is reported by the callback and depends on model pricing; verify for production._\n")
    else:
        md.append("_Usage not available._\n")

    usage_by_node = state.get("usage_by_node", {}) or {}
    md.append("\n## LLM usage by node\n")
    if not usage_by_node:
        md.append("_Not available._\n")
    else:
        keys_order = ("attempts", "cache_hit", "retrieved_k", "sources_count", "prompt_tokens", "completion_tokens", "total_tokens", "total_cost_usd")
        for node_name, node_usage in sorted(usage_by_node.items()):
            if not isinstance(node_usage, dict):
                continue
            parts = []
            for k in keys_order:
                v = node_usage.get(k)
                if v is not None:
                    parts.append(f"{k}={v}")
            md.append(f"- {node_name}: {', '.join(parts)}\n" if parts else f"- {node_name}: (no metrics)\n")

    sources = state.get("sources", [])
    if sources:
        md.append("\n## Sources used\n")
        for i, src in enumerate(sources[:10], 1):
            # Extract source filename/path with fallback
            source_name = src.get("source") or "(unknown_source)"
            
            # Build metadata suffix from tags
            tags_parts = []
            role = src.get("role")
            process = src.get("process")
            am_tech = src.get("am_tech")
            offer_type = src.get("offer_type")
            
            if role:
                tags_parts.append(f"role={role}")
            if process:
                tags_parts.append(f"process={process}")
            if am_tech:
                tags_parts.append(f"am_tech={am_tech}")
            if offer_type:
                tags_parts.append(f"offer_type={offer_type}")
            
            # Format source title with metadata suffix
            if tags_parts:
                source_display = f"{source_name} ({', '.join(tags_parts)})"
            else:
                source_display = source_name
            
            md.append(f"{i}. **{source_display}**\n")
            md.append(f"   {src.get('text', '')[:200]}...\n\n")

    err = state.get("error")
    if err is not None:
        md.append("\n## Errors encountered\n")
        node = getattr(err, "node", None) if not isinstance(err, dict) else err.get("node")
        msg = getattr(err, "message", None) if not isinstance(err, dict) else err.get("message")
        md.append(f"- {node or 'unknown'}: {msg or 'unknown error'}\n")

    # Agent confidence & limitations
    md.append("\n## Agent confidence & limitations\n")
    conf = _conf_dict(state.get("confidence"))
    if conf:
        md.append(f"- **Score:** {conf.get('score', '—')}\n")
        for key, label in (
            ("high_confidence", "High confidence"),
            ("medium_confidence", "Medium confidence"),
            ("low_confidence", "Low confidence"),
            ("limitations", "Limitations"),
            ("to_improve", "To improve"),
        ):
            items = conf.get(key, [])
            if items:
                md.append(f"- **{label}:** " + "; ".join(items) + "\n")
            else:
                md.append(f"- **{label}:** _None_\n")
    else:
        md.append("_Not available._\n")

    trace_items = [f"report: process_recommendation present={has_proc} primary={primary}"]
    proc_rec_trace = state.get("process_recommendation") or {}
    if isinstance(proc_rec_trace, dict):
        sec_count = len(proc_rec_trace.get("secondary") or [])
        trace_items.append(f"report: secondary_mode=close_alternatives secondary_count={sec_count}")
    if process_val in ("CNC", "CNC_TURNING") and part_metrics_provider in ("numeric_cnc_v1_failed", "numeric_cnc_v1_timeout"):
        reason = "timeout" if "timeout" in part_metrics_provider else "error"
        trace_items.append(f"Numeric CNC analysis unavailable ({reason}), used bins.")
    return {
        "report_markdown": "\n".join(md),
        "trace": trace_items,
    }