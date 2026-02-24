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


def run_injection_molding_rules(state: GraphState) -> dict:
    """Injection molding rules: keyword and part_summary based; no LLM."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    findings: list[Finding] = []

    # IM1: derived from process_selection score_breakdown (do not re-evaluate here)

    # IM2: Tight tolerances
    if i.tolerance_criticality == "High":
        sev = "HIGH" if i.production_volume == "Production" else "MEDIUM"
        _add(findings, id="IM2", category="DFM", severity=sev, title="Tight tolerances in injection molding (capability risk)",
             why="Injection molding tolerances are typically looser than CNC; material, thickness, and tool quality dominate accuracy.", rec="Apply tight tolerances only to functional interfaces; use post-machining for critical fits; avoid global tight tolerances.")

    # IM3: Large thin sheet warpage/rigidity risk
    if s.part_size == "Large" and s.min_wall_thickness == "Thin":
        _add(findings, id="IM3", category="DFM", severity="HIGH", title="Large thin part risk (warpage / low rigidity)",
             why="Large flat thin parts are prone to warping; stiffness often needs ribs or thicker sections.", rec="Add ribs/gussets; break up large flats; consider thickness increase; validate flatness requirements.")

    # IM4: Small internal radius (stress + flow)
    if s.min_internal_radius == "Small":
        sev = "HIGH" if i.load_type in ("Dynamic", "Shock") else "MEDIUM"
        _add(findings, id="IM4", category="DFM", severity=sev, title="Sharp corners / tight radii (stress concentration + flow risk)",
             why="Sharp corners concentrate stress and impede material flow; dynamic/shock loads amplify failure risk.", rec="Increase internal radii; standardize radii; validate against material capability; add fillets at stress concentrations.")

    # IM5: High feature variety (complex tool/ops)
    if s.feature_variety == "High":
        sev = "HIGH" if i.production_volume == "Production" else "MEDIUM"
        _add(findings, id="IM5", category="DFM", severity=sev, title="High process complexity (tooling complexity / secondary ops)",
             why="Many distinct features often correlate with complex tooling, side actions, and secondary operations.", rec="Simplify geometry; standardize features; reduce secondary ops; design for efficient molding sequence.")

    # IM6: High accessibility risk (tooling complexity / undercut / ejection)
    if s.accessibility_risk == "High":
        _add(findings, id="IM6", category="DFM", severity="HIGH", title="High accessibility risk (tooling complexity / undercut / ejection risk)",
             why="Poor access often indicates undercuts, side actions, or ejection challenges; increases mold cost and complexity.", rec="Avoid undercuts where possible; replace with snap features or assembly; ensure ejection access; align features with mold open direction.")

    # IM7: Tight tolerances + poor access (critical features hard to inspect/finish)
    if i.tolerance_criticality == "High" and s.accessibility_risk == "High":
        _add(findings, id="IM7", category="DFM", severity="HIGH", title="Tight requirements but poor access for inspection/finishing",
             why="If precision surfaces can't be reached for finishing/measurement, production quality and acceptance are at risk.", rec="Redesign for access; add datum/reference features; plan inspection/finishing approach; consider post-machining for critical surfaces.")

    # IM8: Material-specific behavior (Nylon/POM)
    material_keywords = ("nylon", "pa", "delrin", "pom")
    if any(kw in user_text for kw in material_keywords) and i.tolerance_criticality == "High":
        sev = "HIGH" if i.production_volume == "Production" else "MEDIUM"
        rec = "Account for moisture absorption (Nylon) and dimensional stability; validate shrinkage; avoid sharp corners (POM); consider material-specific creep and anisotropy."
        _add(findings, id="IM8", category="DFM", severity=sev, title="Engineering plastic (Nylon/POM) with tight tolerances (material behavior risk)",
             why="Nylon absorbs moisture and has high shrinkage/anisotropy; POM requires uniform walls and avoids sharp corners. Both need careful tolerance planning.", rec=rec)

    # IM9: Textured surface + low draft risk
    texture_keywords = ("texture", "grain", "spi", "vdi", "textured")
    if any(kw in user_text for kw in texture_keywords) and s.min_internal_radius == "Small":
        # Small radius proxy for potential low draft; texture requires extra draft
        _add(findings, id="IM9", category="DFM", severity="HIGH", title="Textured surface with potential low draft (ejection risk)",
             why="Textured surfaces require additional draft (1° per 0.025mm texture depth); insufficient draft causes ejection damage and surface defects.", rec="Increase draft for textured surfaces; ensure ≥2° per side for standard textures; validate ejection clearance.")

    # IM10: Nylon + moisture not considered
    nylon_keywords = ("nylon", "pa", "polyamide")
    moisture_keywords = ("dry", "moisture", "conditioning", "conditioned", "drying")
    if any(kw in user_text for kw in nylon_keywords) and not any(kw in user_text for kw in moisture_keywords):
        sev = "HIGH" if i.tolerance_criticality == "High" else "MEDIUM"
        _add(findings, id="IM10", category="DFM", severity=sev, title="Nylon without moisture conditioning consideration (dimensional stability risk)",
             why="Nylon absorbs 1.5–3% moisture in ambient conditions, causing 0.1–0.3% dimensional change; parts must be dried before molding and conditioned post-mold.", rec="Specify drying requirements (<0.15% moisture before molding); plan post-mold conditioning (24–48h at 50% RH); account for dimensional change in tolerance planning.")

    # IM11: Insert molding / metal inserts warnings
    insert_keywords = ("insert", "overmold", "metal insert", "threaded insert")
    if any(kw in user_text for kw in insert_keywords):
        sev = "HIGH" if i.production_volume == "Production" else "MEDIUM"
        _add(findings, id="IM11", category="DFM", severity=sev, title="Insert molding / metal inserts (stress cracking risk)",
             why="Metal inserts can cause stress cracking around insert due to differential shrinkage; overmolding increases tool complexity and cost.", rec="Design inserts with adequate wall thickness around insert; consider post-mold insertion for low volumes; avoid sharp corners at insert interface; validate thermal expansion compatibility.")

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
