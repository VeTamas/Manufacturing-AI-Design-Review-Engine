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


def run_am_sls_rules(state: GraphState) -> dict:
    """SLS (Selective Laser Sintering) rules: warpage, powder removal, drain holes, gap/hole offset, text limits."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    findings: list[Finding] = []

    # SLS1: Warpage / thermal shrink risk
    if s.min_wall_thickness == "Thin" or s.part_size in ("Medium", "Large"):
        sev = "HIGH" if s.min_wall_thickness == "Thin" else "MEDIUM"
        _add(findings, id="SLS1", category="DFM", severity=sev,
             title="Warpage / thermal shrink risk (SLS)",
             why="Thermal gradients cause warp; long/thin and abrupt cross-sections increase risk. L/W >10:1 prone to distortion.",
             rec="Add ribs; use uniform thickness; add fillets at transitions; design symmetry.")

    # SLS2: Hollow parts + powder removal drain holes
    if "hollow" in user_text or "cavity" in user_text or "enclosed" in user_text:
        _add(findings, id="SLS2", category="DFM", severity="HIGH",
             title="Hollow parts + powder removal drain holes (SLS)",
             why="Enclosed volumes trap powder. Min wall 2 mm for hollowing; drain holes ≥5 mm; place at low points on opposite sides.",
             rec="Add ≥2 drain holes on opposite sides; min Ø5 mm; prefer corners for better powder removal.")

    # SLS3: Gap/hole offset for over-sinter shrink
    if "clearance" in user_text or "gap" in user_text or "hole" in user_text:
        _add(findings, id="SLS3", category="DFM", severity="MEDIUM",
             title="Gap/hole offset for over-sinter shrink (SLS)",
             why="Small holes and gaps shrink/over-sinter; offset gap/hole surfaces 0.15–0.20 mm recommended.",
             rec="Offset gap and hole surfaces 0.15–0.20 mm to compensate for over-sinter; plan reaming for critical holes.")

    # SLS4: Line-of-sight for powder removal
    if s.hole_depth_class in ("Moderate", "Deep"):
        _add(findings, id="SLS4", category="DFM", severity="HIGH",
             title="Line-of-sight for powder removal (SLS)",
             why="Through holes and cavities need line-of-sight clearance for powder evacuation; blind holes trap powder.",
             rec="Ensure line-of-sight for cavities; add powder escape paths; avoid dead-end channels.")

    # SLS5: Text/marking legibility limits
    if "text" in user_text or "marking" in user_text or "engrav" in user_text:
        _add(findings, id="SLS5", category="DFM", severity="MEDIUM",
             title="Text/marking legibility limits (SLS)",
             why="Min text thickness ~0.43 mm, min height ~0.56 mm for legible markings.",
             rec="Use stroke thickness ≥0.43 mm and height ≥0.56 mm for text; verify after build.")

    # SLS6: Thin wall robustness
    if s.min_wall_thickness == "Thin":
        _add(findings, id="SLS6", category="DFM", severity="MEDIUM",
             title="Thin wall robustness / long wall aspect (SLS)",
             why="Thin pins/walls fragile due to porous surface and micro-notches; long thin walls warp.",
             rec="Thicken features; add fillets; add ribs for long walls; avoid extreme aspect ratios.")

    # SLS7: Abrupt cross-section transitions
    if s.feature_variety == "High":
        _add(findings, id="SLS7", category="DFM", severity="MEDIUM",
             title="Abrupt cross-section transitions (SLS)",
             why="Thick-to-thin transitions increase thermal stress and warpage risk.",
             rec="Use gradual transitions; add fillets at section changes; avoid sharp thickness jumps.")

    # SLS8: Bosses/fillets guidance
    if "boss" in user_text or "bosses" in user_text:
        _add(findings, id="SLS8", category="DFM", severity="MEDIUM",
             title="Bosses/fillets guidance (SLS)",
             why="Tall thin bosses are weak; fillets at base reduce stress concentration.",
             rec="Add fillets at boss base; avoid tall thin bosses without ribs; connect bosses to walls where possible.")

    # SLS9: Dimensional tolerance expectation
    if i.tolerance_criticality in ("Medium", "High"):
        _add(findings, id="SLS9", category="DFM", severity="MEDIUM",
             title="Dimensional tolerance expectation (SLS)",
             why="SLS typically ±0.2–0.3 mm; critical features need post-machining or relaxation.",
             rec="Plan machining/reaming for critical holes and datums; relax non-critical tolerances.")

    # SLS10: Nesting/packing awareness
    _add(findings, id="SLS10", category="DFM", severity="LOW",
         title="Nesting/packing awareness (SLS)",
         why="SLS supports nesting; packing density affects cost and throughput.",
         rec="Consider build volume utilization; reduce z-height where possible; batch similar parts.")

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
