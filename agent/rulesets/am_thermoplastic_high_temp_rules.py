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


def run_am_thermoplastic_high_temp_rules(state: GraphState) -> dict:
    """High-temp Thermoplastic AM rules: chamber/temp, warping, material shrink, post-machining, tolerances."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    findings: list[Finding] = []

    # HTP1: Chamber temperature and material requirements
    if "peek" in user_text or "pei" in user_text or "ultem" in user_text:
        _add(findings, id="HTP1", category="DFM", severity="MEDIUM",
             title="High-temperature chamber required (PEEK/PEI/Ultem)",
             why="High-temp thermoplastics require heated build chambers (150–200°C) and specialized printers.",
             rec="Confirm printer capability for high-temp materials; plan for longer cycle times; consider material cost.")

    # HTP2: Warping and thermal management
    if s.part_size in ("Medium", "Large"):
        _add(findings, id="HTP2", category="DFM", severity="HIGH",
             title="Warping risk (high-temp thermoplastic)",
             why="High-temp materials warp significantly due to thermal gradients; large parts are especially sensitive.",
             rec="Use heated chamber; add brim/raft; optimize build orientation; consider annealing for stress relief.")

    # HTP3: Material shrinkage and dimensional accuracy
    if i.tolerance_criticality == "High":
        _add(findings, id="HTP3", category="DFM", severity="MEDIUM",
             title="Material shrinkage and tolerances (high-temp thermoplastic)",
             why="High-temp materials have higher shrinkage; dimensional accuracy requires compensation.",
             rec="Account for material-specific shrinkage; plan machining allowance; validate dimensions post-build.")

    # HTP4: Post-machining and surface finish
    if "machining" in user_text or i.tolerance_criticality == "High":
        _add(findings, id="HTP4", category="DFM", severity="MEDIUM",
             title="Post-machining for tight tolerances (high-temp thermoplastic)",
             why="High-temp materials can be machined but require careful tooling and parameters.",
             rec="Plan machining for critical surfaces; use appropriate tooling; account for material properties.")

    # HTP5: Layer adhesion and interlayer strength
    if i.load_type in ("Dynamic", "Shock"):
        _add(findings, id="HTP5", category="DESIGN_REVIEW", severity="HIGH",
             title="Interlayer adhesion critical (high-temp thermoplastic)",
             why="High-temp materials require optimal print parameters for strong interlayer bonding.",
             rec="Optimize print temperature and speed; orient layers for strength; validate interlayer adhesion.")

    # HTP6: Support removal and surface finish
    if s.accessibility_risk in ("Medium", "High") or "support" in user_text:
        _add(findings, id="HTP6", category="DFM", severity="MEDIUM",
             title="Support removal access (high-temp thermoplastic)",
             why="Supports must be removed; high-temp materials may require careful removal techniques.",
             rec="Design for support removal access; minimize supports in critical areas; plan post-processing.")

    # HTP7: Material cost and availability
    if "cost" in user_text:
        _add(findings, id="HTP7", category="DFM", severity="LOW",
             title="Material cost consideration (high-temp thermoplastic)",
             why="High-temp materials (PEEK/PEI) are significantly more expensive than standard FDM materials.",
             rec="Evaluate material cost vs performance requirements; consider alternatives if cost-sensitive.")

    # HTP8: Temperature resistance and application
    if "high temp" in user_text or "temperature" in user_text:
        _add(findings, id="HTP8", category="DESIGN_REVIEW", severity="MEDIUM",
             title="Temperature resistance verification (high-temp thermoplastic)",
             why="High-temp materials have specific temperature limits; verify suitability for application.",
             rec="Confirm material temperature rating; consider thermal cycling effects; validate for application.")

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
