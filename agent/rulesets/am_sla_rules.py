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


def run_am_sla_rules(state: GraphState) -> dict:
    """SLA (Stereolithography) rules: supports, peel-risk, bridge span, fine detail limits, drain holes, IPA wash."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    findings: list[Finding] = []

    # SLA1: Supports & peel-risk orientation
    if s.accessibility_risk == "High" or any(kw in user_text for kw in ["flat surface", "large overhang"]):
        _add(findings, id="SLA1", category="DFM", severity="HIGH",
             title="Supports & peel-risk orientation (SLA)",
             why="SLA requires supports; <10° surfaces increase peel failure risk. Orientation strongly affects support count and surface quality.",
             rec="Orient model so large flat faces are supportable; avoid <10° critical surfaces; protect datum/mating faces from supports.")

    # SLA2: Bridge/span limit
    _add(findings, id="SLA2", category="DFM", severity="MEDIUM",
         title="Bridge/span limit (SLA)",
         why="Long horizontal bridges (~29mm typical limit for 5×3mm beams) risk sagging or failure.",
         rec="Avoid long unsupported spans; add ribs or supports; break up large flat regions.")

    # SLA3: Fine embossed detail limit
    if "emboss" in user_text or "text" in user_text or "marking" in user_text:
        _add(findings, id="SLA3", category="DFM", severity="MEDIUM",
             title="Fine embossed detail limit (SLA)",
             why="Minimum embossed detail typically ~0.1 mm; finer detail may not print clearly.",
             rec="Use stroke widths ≥0.1 mm for embossed text; prefer embossed over engraved for clarity.")

    # SLA4: Fine engraved detail limit
    if "engrav" in user_text or "text" in user_text:
        _add(findings, id="SLA4", category="DFM", severity="MEDIUM",
             title="Fine engraved detail limit (SLA)",
             why="Minimum engraved detail typically ~0.15 mm; finer detail may fill or close.",
             rec="Use stroke widths ≥0.15 mm for engraved text; ensure engraving survives support removal.")

    # SLA5: Moving/assembly clearance
    if "clearance" in user_text or "assembly" in user_text or "fit" in user_text:
        _add(findings, id="SLA5", category="DFM", severity="HIGH",
             title="Moving/assembly clearance (SLA)",
             why="Min clearance for moving/assembled parts typically ≥0.5 mm; tighter gaps risk binding or cracking.",
             rec="Design ≥0.5 mm clearance between moving/assembled interfaces; verify after post-cure shrinkage.")

    # SLA6: Min hole diameter
    if s.hole_depth_class in ("Moderate", "Deep"):
        _add(findings, id="SLA6", category="DFM", severity="MEDIUM",
             title="Min hole diameter / hole closure risk (SLA)",
             why="Small holes can close partially due to curing and resin drainage; min ~0.5 mm recommended.",
             rec="Oversize holes; plan drilling/reaming for critical holes; add chamfer entry to reduce support scarring.")

    # SLA7: Drain holes for enclosed cavities
    if "hollow" in user_text or "cavity" in user_text or "enclosed" in user_text:
        _add(findings, id="SLA7", category="DFM", severity="HIGH",
             title="Drain holes for enclosed cavities (SLA)",
             why="Hollow shapes trap resin; suction forces can cause print failure. Min drain hole ~2.5 mm for enclosed volumes.",
             rec="Add drain/vent holes (≥2.5 mm) to enclosed cavities; avoid deep concave cavities facing downward; reorient to reduce trapped volume.")

    # SLA8: Thin features / IPA wash fragility
    if s.min_wall_thickness == "Thin":
        _add(findings, id="SLA8", category="DFM", severity="MEDIUM",
             title="Thin features handling / IPA wash fragility (SLA)",
             why="IPA wash and post-cure can weaken thin walls and pins; resin parts are brittle.",
             rec="Thicken thin pins/posts; add temporary breakaway supports; handle carefully during wash and support removal.")

    # SLA9: Post-cure dimensional change
    if i.tolerance_criticality in ("Medium", "High"):
        _add(findings, id="SLA9", category="DFM", severity="MEDIUM",
             title="Post-cure dimensional change / tolerance reality (SLA)",
             why="Post-cure introduces shrinkage and warpage; dimensions shift after UV cure.",
             rec="Plan secondary operations for critical fits; allow allowance for post-cure; define post-cure plan.")

    # SLA10: Support marks on cosmetic/critical surfaces
    if s.accessibility_risk in ("Medium", "High") or "cosmetic" in user_text or "surface" in user_text:
        _add(findings, id="SLA10", category="DFM", severity="MEDIUM",
             title="Support marks on cosmetic/critical surfaces (SLA)",
             why="Support contacts leave marks; down-facing surfaces show stair-stepping and roughness.",
             rec="Orient cosmetic faces upward; keep supports off datum/mating faces; plan post-finish allowance.")

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
