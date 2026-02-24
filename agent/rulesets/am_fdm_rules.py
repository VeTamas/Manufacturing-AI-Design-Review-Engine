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


def run_am_fdm_rules(state: GraphState) -> dict:
    """FDM (Fused Deposition Modeling) rules: layer adhesion, overhang/supports, anisotropy, warping, tolerances, inserts."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    findings: list[Finding] = []

    # FDM1: Layer adhesion and strength
    if i.load_type in ("Dynamic", "Shock"):
        _add(findings, id="FDM1", category="DESIGN_REVIEW", severity="HIGH",
             title="Layer adhesion critical for dynamic/shock loads",
             why="FDM parts have anisotropic strength; layer adhesion is weakest direction.",
             rec="Orient layers perpendicular to principal stress; consider annealing for improved layer bonding.")

    # FDM2: Overhang and support requirements
    if s.min_wall_thickness == "Thin" or "overhang" in user_text:
        sev = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
        _add(findings, id="FDM2", category="DFM", severity=sev,
             title="Overhang/support risk (FDM)",
             why="FDM requires supports for overhangs >45°; supports add material, time, and post-processing.",
             rec="Design self-supporting geometry; limit overhangs to <45°; ensure support removal access.")

    # FDM3: Anisotropy and orientation
    if "orientation" in user_text or i.load_type in ("Dynamic", "Shock"):
        _add(findings, id="FDM3", category="DFM", severity="MEDIUM",
             title="Anisotropy and build orientation (FDM)",
             why="FDM parts are anisotropic; strength varies significantly with layer direction.",
             rec="Specify build orientation relative to load path; orient layers along principal stress.")

    # FDM4: Warping and bed adhesion
    if s.part_size in ("Medium", "Large"):
        _add(findings, id="FDM4", category="DFM", severity="MEDIUM",
             title="Warping risk (large FDM parts)",
             why="Large FDM parts warp due to thermal contraction; bed adhesion is critical.",
             rec="Use heated bed; add brim/raft; consider part orientation to minimize warping.")

    # FDM5: Tolerances and dimensional accuracy
    if i.tolerance_criticality == "High":
        _add(findings, id="FDM5", category="DFM", severity="HIGH",
             title="Tight tolerances (FDM capability)",
             why="FDM typically holds ±0.1–0.3 mm; layer effects and warping limit precision.",
             rec="Plan machining allowance for critical surfaces; relax non-critical tolerances; consider post-machining.")

    # FDM6: Inserts and embedded features
    if "insert" in user_text or "embedded" in user_text:
        _add(findings, id="FDM6", category="DFM", severity="MEDIUM",
             title="Inserts/embedded features (FDM)",
             why="Metal inserts can be embedded during printing but require careful design.",
             rec="Design insert pockets with clearance; pause print for insert placement; ensure good adhesion.")

    # FDM7: Support removal and surface finish
    if s.accessibility_risk in ("Medium", "High"):
        _add(findings, id="FDM7", category="DFM", severity="MEDIUM",
             title="Support removal access (FDM)",
             why="Supports must be removed; poor access increases post-processing time and risk.",
             rec="Design for support removal access; minimize supports in critical areas; plan post-processing.")

    # FDM8: Material selection and temperature
    if "high temp" in user_text or "temperature" in user_text:
        _add(findings, id="FDM8", category="DFM", severity="MEDIUM",
             title="High-temperature material selection (FDM)",
             why="Standard FDM materials (PLA/ABS) have limited temperature resistance.",
             rec="Consider high-temp materials (PETG, PC, PEEK) for elevated temperature applications.")

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
