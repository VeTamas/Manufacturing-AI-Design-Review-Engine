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


def run_am_metal_lpbf_rules(state: GraphState) -> dict:
    """Metal LPBF (Laser Powder Bed Fusion) rules: supports, residual stress, heat treat/HIP, machining allowances, min wall/holes, powder removal."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    findings: list[Finding] = []

    # LPBF1: Support structures and overhangs
    if s.min_wall_thickness == "Thin" or s.accessibility_risk in ("Medium", "High"):
        sev = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
        _add(findings, id="LPBF1", category="DFM", severity=sev,
             title="Support structures required (metal LPBF)",
             why="Metal LPBF requires supports for overhangs; supports add cost, time, and post-processing.",
             rec="Design self-supporting geometry; minimize overhangs <45°; ensure support removal access; plan for EDM/saw removal.")

    # LPBF2: Residual stress and distortion
    if s.part_size in ("Medium", "Large") or i.load_type in ("Dynamic", "Shock"):
        _add(findings, id="LPBF2", category="DESIGN_REVIEW", severity="HIGH",
             title="Residual stress and distortion (metal LPBF)",
             why="Metal LPBF generates high residual stresses; large parts and dynamic loads are sensitive.",
             rec="Plan stress relief heat treatment; consider HIP for critical parts; design for distortion compensation.")

    # LPBF3: Heat treatment and HIP
    if i.load_type in ("Dynamic", "Shock") or "heat treat" in user_text:
        _add(findings, id="LPBF3", category="DFM", severity="MEDIUM",
             title="Heat treatment/HIP required (metal LPBF)",
             why="Metal LPBF parts often require stress relief and/or HIP for optimal properties.",
             rec="Plan stress relief cycle; consider HIP for fatigue-critical parts; account for dimensional changes.")

    # LPBF4: Machining allowances
    if i.tolerance_criticality == "High":
        _add(findings, id="LPBF4", category="DFM", severity="HIGH",
             title="Machining allowances for tight tolerances (metal LPBF)",
             why="Metal LPBF surface finish and dimensional accuracy require post-machining for tight tolerances.",
             rec="Add machining stock (0.5–1 mm) on critical surfaces; define datums for machining; plan post-processing.")

    # LPBF5: Minimum wall thickness and feature size
    if s.min_wall_thickness == "Thin":
        _add(findings, id="LPBF5", category="DFM", severity="HIGH",
             title="Minimum wall thickness (metal LPBF)",
             why="Metal LPBF has minimum feature size (~0.3–0.5 mm); thin walls risk failure or incomplete fusion.",
             rec="Increase wall thickness to ≥0.5 mm; avoid extremely thin features; validate with supplier.")

    # LPBF6: Hole size and powder removal
    if s.hole_depth_class in ("Moderate", "Deep"):
        _add(findings, id="LPBF6", category="DFM", severity="MEDIUM",
             title="Hole size and powder removal (metal LPBF)",
             why="Small holes trap powder; powder removal is difficult and can cause defects.",
             rec="Design holes ≥2 mm diameter; add drain holes for enclosed volumes; ensure powder removal access.")

    # LPBF7: Enclosed cavities and powder trapping
    if s.pocket_aspect_class in ("Risky", "Extreme"):
        sev = "HIGH" if s.pocket_aspect_class == "Extreme" else "MEDIUM"
        _add(findings, id="LPBF7", category="DFM", severity=sev,
             title="Enclosed cavities trap powder (metal LPBF)",
             why="Enclosed cavities trap powder; trapped powder causes defects and contamination.",
             rec="Add drain holes (≥2 mm); avoid fully enclosed volumes; design for powder removal.")

    # LPBF8: Surface finish and post-machining
    if "surface finish" in user_text or i.tolerance_criticality == "High":
        _add(findings, id="LPBF8", category="DFM", severity="MEDIUM",
             title="Surface finish and post-machining (metal LPBF)",
             why="Metal LPBF surface finish is rough (Ra 5–15 μm); critical surfaces require post-machining.",
             rec="Plan machining for critical surfaces; specify surface finish requirements; add machining stock.")

    # LPBF9: Build orientation and anisotropy
    if i.load_type in ("Dynamic", "Shock") or "orientation" in user_text:
        _add(findings, id="LPBF9", category="DESIGN_REVIEW", severity="HIGH",
             title="Build orientation affects properties (metal LPBF)",
             why="Metal LPBF parts are anisotropic; orientation affects strength, fatigue, and surface finish.",
             rec="Specify build orientation relative to load path; orient for strength along principal stress; document orientation.")

    # LPBF10: Powder removal and cleaning
    if s.accessibility_risk in ("Medium", "High"):
        _add(findings, id="LPBF10", category="DFM", severity="MEDIUM",
             title="Powder removal access (metal LPBF)",
             why="Trapped powder must be removed; poor access increases cleaning time and risk.",
             rec="Design for powder removal access; add drain holes; plan cleaning procedures.")

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
