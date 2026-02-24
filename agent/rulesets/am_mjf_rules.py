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


def run_am_mjf_rules(state: GraphState) -> dict:
    """MJF (Multi Jet Fusion) rules: powder removal, warp risk, min feature size, color consistency, tolerances."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    findings: list[Finding] = []

    # MJF1: Powder removal for blind holes/bosses
    if s.hole_depth_class in ("Moderate", "Deep") or "blind" in user_text or "boss" in user_text:
        _add(findings, id="MJF1", category="DFM", severity="HIGH",
             title="Powder removal for blind holes/bosses (MJF)",
             why="Blind holes and bosses trap powder; exit holes/channels and line-of-sight required. Deeper cavities need more exit points (~12.7 mm spacing).",
             rec="Add exit holes/channels for blind holes; ensure line-of-sight; multiple exit points for deep cavities.")

    # MJF2: Warp risk from thick/flat/uneven walls
    if s.min_wall_thickness in ("Thin", "Medium") and s.part_size in ("Medium", "Large"):
        _add(findings, id="MJF2", category="DFM", severity="HIGH",
             title="Warp risk from thick/flat/uneven walls (MJF)",
             why="Thick/flat/broad and uneven wall sections cause warp and dimensional drift.",
             rec="Add ribs; use uniform thickness; add fillets at transitions; orient to reduce large flat cross-sections.")

    # MJF3: Min feature size
    if "fine" in user_text or "detail" in user_text or "small feature" in user_text:
        _add(findings, id="MJF3", category="DFM", severity="MEDIUM",
             title="Min feature size 0.5 mm (MJF)",
             why="Min feature size typically 0.5 mm; layer thickness 80 µm.",
             rec="Design features ≥0.5 mm; avoid finer detail unless post-processed.")

    # MJF4: Cosmetic color consistency
    if "cosmetic" in user_text or "color" in user_text or "dye" in user_text:
        _add(findings, id="MJF4", category="DFM", severity="MEDIUM",
             title="Cosmetic color consistency (MJF)",
             why="Natural gray can be inconsistent; dyed black recommended for cosmetics.",
             rec="Plan dye for cosmetic parts; bead blast or smoothing may shift dimensions.")

    # MJF5: Tolerance reality
    if i.tolerance_criticality in ("Medium", "High"):
        _add(findings, id="MJF5", category="DFM", severity="MEDIUM",
             title="Tolerance reality / critical interfaces (MJF)",
             why="Proto rigid materials: <30mm ±0.7mm; 30–50 ±0.85mm; 50–80 ±1.4mm; >80mm ±1.75%. Critical features need machining.",
             rec="Plan machining for critical datums; design-for-adjustment (slots, shims); relax non-critical tolerances.")

    # MJF6: Hollowing & drain strategy
    if "hollow" in user_text or "cavity" in user_text or "enclosed" in user_text:
        _add(findings, id="MJF6", category="DFM", severity="MEDIUM",
             title="Hollowing & drain strategy (MJF)",
             why="Internal channels and hollow bodies need escape holes; avoid dead-end channels.",
             rec="Add escape holes; adequate diameter for evacuation; avoid sealed cavities.")

    # MJF7: Boss base fillets
    if "boss" in user_text or "bosses" in user_text:
        _add(findings, id="MJF7", category="DFM", severity="MEDIUM",
             title="Boss base fillets (MJF)",
             why="Fillets at boss base reduce stress and improve powder removal.",
             rec="Add generous radii at boss base; avoid tall thin bosses without ribs.")

    # MJF8: Tiny / very large parts process risk
    if s.part_size == "Small" or s.part_size == "Large":
        _add(findings, id="MJF8", category="DFM", severity="MEDIUM",
             title="Tiny / very large parts process risk (MJF)",
             why="Very small or very large parts have different process constraints and economics.",
             rec="Confirm part fits build volume; consider batch repeatability for production.")

    # MJF9: Build volume utilization economics
    _add(findings, id="MJF9", category="DFM", severity="LOW",
         title="Build volume utilization economics (MJF)",
         why="Packing density and z-height affect throughput and cost.",
         rec="Optimize packing; reduce z-height where possible; batch similar parts.")

    # MJF10: Powder trap corners
    if "hollow" in user_text or "channel" in user_text or "lattice" in user_text:
        _add(findings, id="MJF10", category="DFM", severity="MEDIUM",
             title="Powder trap corners (MJF)",
             why="Hollow corners can trap powder; exit holes at corners improve removal.",
             rec="Place exit holes at low points and corners; avoid dead-end corners in hollow geometry.")

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
