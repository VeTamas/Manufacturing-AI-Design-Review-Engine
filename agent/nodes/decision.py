from __future__ import annotations

from agent.state import GraphState


def decision_node(state: GraphState) -> dict:
    """
    Agentic decision node: determines next action based on findings, confidence, and round count.
    Rule-based (no LLM calls). Returns routing string: "accept" | "rag" | "reassess".
    """
    findings = state.get("findings", [])
    confidence = state.get("confidence")
    decision_round = state.get("decision_round", 0)
    max_rounds = state.get("max_rounds", 2)

    # Extract confidence score (support both Confidence model and dict)
    conf_data = getattr(confidence, "model_dump", None)
    conf_dict = conf_data() if callable(conf_data) else (confidence if isinstance(confidence, dict) else {})
    confidence_score = conf_dict.get("score")
    if not isinstance(confidence_score, (int, float)):
        confidence_score = 0.5

    # Hard stop: prevent infinite loops
    if decision_round >= max_rounds:
        return {
            "trace": ["Agent decision: accept (max rounds reached)"],
            "_decision": "accept",
        }

    # Optional: avoid second RAG loop when we already retrieved and have no new findings
    sources = state.get("sources", [])
    if decision_round >= 1 and sources:
        return {
            "trace": ["Agent decision: accept (RAG already used; proceeding)"],
            "_decision": "accept",
        }

    # Decision policy (rule-based, deterministic but agentic)
    has_high = any(f.severity == "HIGH" for f in findings)
    has_medium = any(f.severity == "MEDIUM" for f in findings)
    part = state.get("part_summary")
    unknown_critical_bins = any(
        getattr(part, key, None) == "Unknown"
        for key in ("min_internal_radius", "min_wall_thickness", "hole_depth_class", "pocket_aspect_class")
    ) if part else False

    inp = state.get("inputs")
    process = getattr(inp, "process", None) if inp else None

    # Check PSI mismatch (process selection recommendation differs from user selection)
    proc_rec = state.get("process_recommendation")
    psi_mismatch = False
    score_diff = 0
    if proc_rec and isinstance(proc_rec, dict) and process:
        rec_primary = proc_rec.get("primary")
        rec_scores = proc_rec.get("scores", {})
        if rec_primary and rec_primary != process:
            primary_score = rec_scores.get(rec_primary, 0)
            user_score = rec_scores.get(process, 0)
            score_diff = primary_score - user_score
            if score_diff >= 2:
                psi_mismatch = True

    # Precompute IM-specific conditions once (used for both routing and trace)
    im_tol_high_no_2d = False
    im_keywords_present = False
    im_scale_not_ok = False
    im_access_keywords = False
    if process == "INJECTION_MOLDING" and inp:
        conf_inputs = state.get("confidence_inputs")
        has_2d = False
        scale_ok = True
        if conf_inputs is not None:
            if isinstance(conf_inputs, dict):
                has_2d = conf_inputs.get("has_2d_drawing", False)
                scale_ok = conf_inputs.get("step_scale_confirmed", True)
            else:
                has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
                scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))
        im_tol_high_no_2d = getattr(inp, "tolerance_criticality", None) == "High" and not has_2d
        im_scale_not_ok = not scale_ok
        user_text = ((state.get("description") or state.get("user_text")) or "").lower()
        im_keywords = (
            "draft", "eject", "ejection", "texture", "textured",
            "gate", "gating", "weld line", "weldline", "knit line",
            "vent", "venting", "sink", "warpage", "warp", "shrink",
            "rib", "boss", "snap", "latch", "living hinge",
            "insert", "overmold", "over-mold", "metal insert",
            "undercut", "side action", "lifter"
        )
        im_keywords_present = any(kw in user_text for kw in im_keywords)
        part = state.get("part_summary")
        if part and getattr(part, "accessibility_risk", None) == "High":
            im_access_keywords = any(kw in user_text for kw in ("eject", "ejection", "insert", "overmold", "over-mold"))

    # Precompute CASTING-specific conditions once (used for both routing and trace)
    cast_keywords_present = False
    cast_tol_high_no_2d = False
    cast_access_high = False
    cast_thin_walls = False
    if process == "CASTING" and inp:
        conf_inputs = state.get("confidence_inputs")
        has_2d = False
        if conf_inputs is not None:
            if isinstance(conf_inputs, dict):
                has_2d = conf_inputs.get("has_2d_drawing", False)
            else:
                has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
        cast_tol_high_no_2d = getattr(inp, "tolerance_criticality", None) == "High" and not has_2d
        user_text = ((state.get("description") or state.get("user_text")) or "").lower()
        cast_keywords = (
            "die cast", "diecasting", "hpdc", "lpdc",
            "investment", "lost wax", "ceramic shell",
            "urethane", "vacuum casting", "silicone mold", "soft tooling",
            "porosity", "shrink", "warpage", "misrun", "cold shut",
            "gating", "gate", "runner", "sprue", "vent", "overflow",
            "parting line", "draft", "ejection", "ejector", "slide", "lifter", "core",
            "weld repair", "heat treat", "radiography", "x-ray"
        )
        cast_keywords_present = any(kw in user_text for kw in cast_keywords)
        part = state.get("part_summary")
        if part:
            cast_access_high = getattr(part, "accessibility_risk", None) == "High"
            cast_thin_walls = getattr(part, "min_wall_thickness", None) == "Thin"

    # Precompute FORGING-specific conditions once (used for both routing and trace)
    forg_keywords_present = False
    forg_tol_high_no_2d = False
    forg_hint = None
    forg_thin_walls = False
    forg_radius_small = False
    forg_access_high = False
    forg_subprocess_hint_present = False
    if process == "FORGING" and inp:
        conf_inputs = state.get("confidence_inputs")
        has_2d = False
        if conf_inputs is not None:
            if isinstance(conf_inputs, dict):
                has_2d = conf_inputs.get("has_2d_drawing", False)
            else:
                has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
        forg_tol_high_no_2d = getattr(inp, "tolerance_criticality", None) == "High" and not has_2d
        user_text = ((state.get("description") or state.get("user_text")) or "").lower()
        forging_keywords = (
            "forging", "forged", "flash", "die", "hammer", "press",
            "closed die", "impression die", "parting line", "draft",
            "grain flow", "laps", "fold", "cold shut", "underfill", "die fill", "flow",
            "rib", "boss", "thin section", "sharp corner", "radius", "fillet",
            "heat treat", "quench", "distortion",
            "open die", "ring rolling",
            "trim", "coining", "die machining",
        )
        forg_keywords_present = any(kw in user_text for kw in forging_keywords)
        forg_hint = state.get("forging_subprocess_hint") or None
        forg_subprocess_hint_present = forg_hint is not None
        part = state.get("part_summary")
        if part:
            forg_thin_walls = getattr(part, "min_wall_thickness", None) == "Thin"
            forg_radius_small = getattr(part, "min_internal_radius", None) == "Small"
            forg_access_high = getattr(part, "accessibility_risk", None) == "High"

    decision: str
    if has_high:
        decision = "rag"
        trace_msg = "Agent decision: enrich via RAG"
    elif confidence_score < 0.65 and has_medium:
        decision = "rag"
        trace_msg = "Agent decision: enrich via RAG"
    elif confidence_score < 0.45:
        decision = "reassess"
        trace_msg = "Agent decision: reassess explanation"
    else:
        decision = "accept"
        trace_msg = "Agent decision: accept"

    # PSI mismatch trigger (only if not already forced RAG and score_diff >= 2)
    if psi_mismatch and decision != "rag" and not state.get("rag_enabled"):
        decision = "rag"
        trace_msg = "Agent decision: enrich via RAG"

    if process == "INJECTION_MOLDING" and decision != "rag" and (im_tol_high_no_2d or im_scale_not_ok or im_keywords_present or im_access_keywords):
        decision = "rag"
        trace_msg = "Agent decision: enrich via RAG"

    if process == "CASTING" and decision != "rag" and (cast_keywords_present or cast_tol_high_no_2d or cast_access_high or cast_thin_walls):
        decision = "rag"
        trace_msg = "Agent decision: enrich via RAG"

    if process == "FORGING" and decision != "rag" and (
        forg_keywords_present or forg_tol_high_no_2d or forg_thin_walls or forg_radius_small
        or forg_access_high or has_high
    ):
        decision = "rag"
        trace_msg = "Agent decision: enrich via RAG"

    assert decision in ("rag", "reassess", "accept"), f"Invalid decision: {decision}"
    trace = [trace_msg]
    if decision == "rag":
        # Priority order: user forced > PSI mismatch > IM keywords > tol no 2D > scale not ok > HIGH findings > unknown bins
        if state.get("rag_enabled"):
            trace.append("RAG forced by user")
        elif psi_mismatch:
            rec_primary = proc_rec.get("primary") if proc_rec and isinstance(proc_rec, dict) else None
            trace.append(f"RAG triggered: process mismatch (recommended {rec_primary} vs selected {process})")
        elif process == "INJECTION_MOLDING":
            if im_keywords_present:
                trace.append("RAG triggered: injection molding keywords present")
            elif im_tol_high_no_2d:
                trace.append("RAG triggered: tight tolerances without 2D drawing")
            elif im_scale_not_ok:
                trace.append("RAG triggered: STEP scale not confirmed")
            elif has_high:
                trace.append("RAG triggered: HIGH severity findings")
        elif process == "CASTING":
            if cast_keywords_present:
                trace.append("RAG triggered: casting keywords present")
            elif cast_tol_high_no_2d:
                trace.append("RAG triggered: tight tolerances without 2D drawing")
            elif cast_thin_walls:
                trace.append("RAG triggered: thin walls / fill risk")
            elif cast_access_high:
                trace.append("RAG triggered: poor access / coring or slides risk")
            elif has_high:
                trace.append("RAG triggered: HIGH severity findings")
        elif process == "FORGING":
            _h = f" (hint={forg_hint})" if forg_hint else ""
            if forg_keywords_present:
                trace.append(f"RAG triggered: forging keywords present{_h}")
            elif forg_tol_high_no_2d:
                trace.append(f"RAG triggered: tight tolerances without 2D drawing{_h}")
            elif forg_thin_walls:
                trace.append(f"RAG triggered: thin walls / flow risk{_h}")
            elif forg_radius_small:
                trace.append(f"RAG triggered: small radii / sharp transitions{_h}")
            elif forg_access_high:
                trace.append(f"RAG triggered: poor access / die complexity risk{_h}")
            elif has_high:
                trace.append(f"RAG triggered: HIGH severity findings{_h}")
        else:
            if has_high:
                trace.append("RAG triggered: HIGH severity findings")
        if unknown_critical_bins and not ((process == "INJECTION_MOLDING" or process == "CASTING" or process == "FORGING") and any(("keywords" in t or "tolerances" in t or "scale" in t or "walls" in t or "access" in t or "geometry" in t or "radii" in t) for t in trace)):
            trace.append("RAG triggered: unknown critical bins present")
    # PSI strong-disagreement trace note (additive, does not change decision)
    proc_rec_d = state.get("process_recommendation") or {}
    primary_rec = proc_rec_d.get("primary")
    scores_d = proc_rec_d.get("scores") or {}
    user_proc = getattr(inp, "process", None) if inp else None
    if decision == "rag" and primary_rec and user_proc and primary_rec != user_proc:
        sd = scores_d.get(primary_rec, 0) - scores_d.get(user_proc, 0)
        if sd >= 4:
            psi_note = f"PSI note: recommended={primary_rec} over selected={user_proc} by {sd} points; RAG retrieval may be biased by selected-process index."
            if psi_note not in trace:
                trace.append(psi_note)
    out: dict = {"trace": trace, "_decision": decision}
    if decision != "accept":
        out["decision_round"] = decision_round + 1
    return out


def _route_decision(state: GraphState) -> str:
    """Conditional edge function: routes based on decision node output."""
    decision = state.get("_decision", "accept")
    if decision not in ("rag", "reassess", "accept"):
        decision = "accept"
    return decision
