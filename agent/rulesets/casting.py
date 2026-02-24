from __future__ import annotations

from agent.state import Finding, GraphState


def _add(
    findings: list[Finding],
    *,
    id: str,
    category: str,
    severity: str,
    title: str,
    why: str,
    rec: str,
) -> None:
    findings.append(
        Finding(id=id, category=category, severity=severity, title=title, why_it_matters=why, recommendation=rec)
    )


def run_casting_rules(state: GraphState) -> dict:
    """Casting-specific design review and DFM rules. Deterministic heuristics based on inputs and part_summary."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    findings: list[Finding] = []

    # Detect casting subprocess hint from user_text/description keywords
    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    casting_hint = None
    if any(kw in user_text for kw in ("die cast", "diecasting", "hpdc", "lpdc", "high pressure", "slide", "lifter")):
        casting_hint = "DIE_CASTING"
    elif any(kw in user_text for kw in ("investment", "lost wax", "wax", "shell", "ceramic shell")):
        casting_hint = "INVESTMENT_CASTING"
    elif any(kw in user_text for kw in ("urethane", "vacuum casting", "silicone mold", "soft tooling")):
        casting_hint = "URETHANE_CASTING"
    elif any(kw in user_text for kw in ("steel casting", "sfsa", "weld repair", "heat treat")):
        casting_hint = "STEEL_CASTING"

    # CAST1: Tight tolerances assumed as-cast
    if i.tolerance_criticality == "High":
        _add(
            findings,
            id="CAST1",
            category="DFM",
            severity="HIGH",
            title="Tight tolerances assumed as-cast (machining likely required)",
            why="Casting variability, shrinkage, and warpage make precision difficult as-cast; precision usually requires machining and inspection strategy.",
            rec="Add machining allowance, specify datums, plan secondary operations and inspection.",
        )

    # CAST2: Thin walls
    if s.min_wall_thickness == "Thin":
        if s.part_size != "Small" or i.load_type in ("Dynamic", "Shock"):
            severity = "HIGH"
        else:
            severity = "MEDIUM"
        _add(
            findings,
            id="CAST2",
            category="DFM",
            severity=severity,
            title="Thin sections increase misrun/warpage/distortion risk",
            why="Thin sections increase misrun, warpage, and distortion risk; also strength risk under load.",
            rec="Thicken walls, add ribs, smooth transitions, ensure feed/flow.",
        )

    # CAST3: Small internal radius
    if s.min_internal_radius == "Small":
        severity = "HIGH" if i.load_type in ("Dynamic", "Shock") else "MEDIUM"
        _add(
            findings,
            id="CAST3",
            category="DFM",
            severity=severity,
            title="Small internal radius increases stress concentration and crack risk",
            why="Small radii create stress concentration and flow hot-spots, increasing crack risk.",
            rec="Increase radii, avoid sharp corners especially in load paths.",
        )

    # CAST4: Accessibility risk
    if s.accessibility_risk in ("Medium", "High"):
        severity = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
        _add(
            findings,
            id="CAST4",
            category="DFM",
            severity=severity,
            title="Accessibility risk increases cores/slides/parting complexity",
            why="Medium/high accessibility risk increases cores, slides, and parting complexity; harder ejection, cleanup, and inspection.",
            rec="Redesign for access; split part; simplify undercuts; plan parting and ejection.",
        )

    # CAST5: Production volume + high feature variety
    if i.production_volume == "Production" and s.feature_variety == "High":
        _add(
            findings,
            id="CAST5",
            category="DFM",
            severity="HIGH",
            title="Production volume with high feature variety increases tooling complexity",
            why="Complex tooling, core actions, and QC variability balloon cost and lead time at production scale.",
            rec="Simplify; standardize features; evaluate process alternatives or redesign for tooling.",
        )

    # CAST6: Urethane casting hint + production volume
    if casting_hint == "URETHANE_CASTING" and i.production_volume == "Production":
        _add(
            findings,
            id="CAST6",
            category="DFM",
            severity="HIGH",
            title="Urethane casting not suited for true production scale",
            why="Soft tooling not suited for true production scale; consistency and tool life limits.",
            rec="Move to injection molding (plastic) or die casting / permanent mold (metal) depending on material needs.",
        )

    # CAST7: Die casting hint + thin walls + risky pockets
    if casting_hint == "DIE_CASTING" and s.min_wall_thickness == "Thin" and s.pocket_aspect_class in ("Risky", "Extreme"):
        severity = "HIGH" if s.pocket_aspect_class == "Extreme" else "MEDIUM"
        _add(
            findings,
            id="CAST7",
            category="DFM",
            severity=severity,
            title="Deep pockets with thin walls increase fill/porosity/warpage risk",
            why="Deep pockets/cavities increase fill, porosity, and warpage risk and ejection complexity.",
            rec="Reduce depth, add draft, add coring, plan gating/venting, avoid trapped volumes.",
        )

    # CAST8: Investment casting hint + high feature variety
    if casting_hint == "INVESTMENT_CASTING" and s.feature_variety == "High":
        _add(
            findings,
            id="CAST8",
            category="DFM",
            severity="MEDIUM",
            title="High feature variety increases post-process overhead",
            why="Post-process, finishing, and inspection overhead rises with high feature variety.",
            rec="Simplify; group features; plan machining on critical interfaces.",
        )

    # CAST9: Die casting draft/ejection constraints not discussed
    if casting_hint == "DIE_CASTING" and "draft" not in user_text:
        if s.min_internal_radius == "Small" or s.accessibility_risk in ("Medium", "High"):
            severity = "HIGH" if (s.min_internal_radius == "Small" or s.accessibility_risk == "High") else "MEDIUM"
            _add(
                findings,
                id="CAST9",
                category="DFM",
                severity=severity,
                title="Die casting: draft / ejection constraints not discussed",
                why="Draft and ejection strategy strongly affect die cast feasibility and cosmetic damage risk.",
                rec="Confirm draft targets, parting line, ejection surfaces, and any slides/lifters; avoid zero-draft on functional/cosmetic faces.",
            )

    # CAST10: Tight tolerances without 2D drawing
    conf_inputs = state.get("confidence_inputs")
    has_2d_drawing = False
    if conf_inputs is None:
        has_2d_drawing = False
    elif isinstance(conf_inputs, dict):
        has_2d_drawing = bool(conf_inputs.get("has_2d_drawing", False))
    else:
        has_2d_drawing = bool(getattr(conf_inputs, "has_2d_drawing", False))
    if i.tolerance_criticality == "High" and not has_2d_drawing:
        _add(
            findings,
            id="CAST10",
            category="DFM",
            severity="HIGH",
            title="Tight tolerances without 2D drawing (as-cast vs machined ambiguity)",
            why="Casting tolerances vary by process; without a drawing, it's unclear what must be machined/inspected.",
            rec="Provide 2D drawing with datums/GD&T; mark features requiring machining; define inspection method and acceptance.",
        )

    # CAST11: Thermal mass / hot-spot risk
    if s.part_size in ("Medium", "Large") and (s.pocket_aspect_class in ("Risky", "Extreme") or s.hole_depth_class == "Deep"):
        severity = "HIGH" if s.pocket_aspect_class == "Extreme" else "MEDIUM"
        _add(
            findings,
            id="CAST11",
            category="DFM",
            severity=severity,
            title="Thermal mass / hot-spot risk (shrink/porosity/warpage)",
            why="Large thermal gradients and isolated mass can drive shrink porosity and warpage.",
            rec="Reduce isolated thick regions; add coring where possible; smooth thickness transitions; plan gating/feeding and post-machining allowances.",
        )

    # CAST12: Post-processing / inspection access risk
    if s.accessibility_risk in ("Medium", "High") and i.tolerance_criticality in ("Medium", "High"):
        severity = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
        _add(
            findings,
            id="CAST12",
            category="DFM",
            severity=severity,
            title="Post-processing / inspection access risk",
            why="If critical features are hard to reach, machining/finishing and measurement become unreliable or expensive.",
            rec="Redesign for tool/measurement access; define datum scheme; consider splitting part or selecting a different casting process.",
        )

    # Build trace delta
    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings if f.severity == "HIGH"]

    result: dict = {"findings": findings, "trace": trace_delta}
    if casting_hint:
        result["casting_subprocess_hint"] = casting_hint
    return result
