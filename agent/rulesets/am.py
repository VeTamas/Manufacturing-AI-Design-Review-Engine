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


def run_am_rules(state: GraphState) -> dict:
    """AM (additive manufacturing) rules: keyword and part_summary based; no LLM. Never CNC."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()
    findings: list[Finding] = []

    # Thin wall / load-bearing (overhang & support risk)
    if s.min_wall_thickness == "Thin":
        if i.load_type in ("Dynamic", "Shock"):
            _add(findings, id="AM4", category="DESIGN_REVIEW", severity="HIGH", title="Load-bearing with thin sections",
                 why="Thin sections under dynamic/shock load are prone to failure; layer direction matters.", rec="Orient layer lines along principal stress; increase wall thickness or add ribs.")
        else:
            sev = "HIGH" if s.part_size != "Small" else "MEDIUM"
            _add(findings, id="AM1", category="DFM", severity=sev, title="Thin walls (overhang & support risk)",
                 why="Thin AM walls often need supports; increase print time and post-processing.", rec="Thicken walls where possible; orient to minimize overhangs; use support-free angles.")
    elif "thin wall" in user_text or "overhang" in user_text:
        _add(findings, id="AM1b", category="DFM", severity="MEDIUM", title="Overhang / thin wall (support risk)",
             why="Overhangs and thin walls often require supports.", rec="Orient to minimize overhangs; thicken walls or add ribs.")

    # Support / bridge
    if "support" in user_text or "bridge" in user_text or s.accessibility_risk in ("Medium", "High"):
        if not any(f.id == "AM2" for f in findings):
            sev = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
            why = "Supports add material, time, and post-processing; bridging can sag. Poor removal access increases risk." if sev == "HIGH" else "Supports add material, time, and post-processing; bridging can sag."
            rec = "Design self-supporting where possible; limit support contact area. Ensure removal access for supports." if sev == "HIGH" else "Design self-supporting where possible; limit support contact area."
            _add(findings, id="AM2", category="DFM", severity=sev, title="Support or bridging (geometry)",
                 why=why, rec=rec)

    # Tolerance / press-fit
    if i.tolerance_criticality == "High":
        has_post_process = any(kw in user_text for kw in ("post-process", "post process", "machining", "ream", "hone", "finish"))
        sev = "HIGH" if not has_post_process else "MEDIUM"
        rec = "Plan machining allowance and post-machining for critical surfaces; relax non-critical tolerances." if sev == "HIGH" else "Relax non-critical tolerances; use machining for critical fits; account for post-processing."
        _add(findings, id="AM3", category="DFM", severity=sev, title="Tight tolerance (AM capability)",
             why="AM typically holds ±0.1–0.5 mm; warping and layer effects limit precision.", rec=rec)
    elif "tolerance" in user_text or "press-fit" in user_text:
        _add(findings, id="AM3b", category="DFM", severity="MEDIUM", title="Tolerance / press-fit (design intent)",
             why="Press-fits and tight fits need stable dimensions; AM can vary.", rec="Allow for AM variability; consider post-machining for critical interfaces.")

    # Load-bearing / structural (text-only)
    if "load-bearing" in user_text or "structural" in user_text:
        _add(findings, id="AM4b", category="DESIGN_REVIEW", severity="MEDIUM", title="Load-bearing / structural (orientation)",
             why="AM parts are anisotropic; orientation affects strength.", rec="Define load direction; orient build for strength along load path.")

    # Orientation / layer direction
    if "orientation" in user_text or "layer direction" in user_text or "layer line" in user_text:
        _add(findings, id="AM5", category="DFM", severity="MEDIUM", title="Orientation / layer direction (design intent)",
             why="Build orientation affects strength, surface finish, and support need.", rec="Document preferred orientation; align layers with principal stress where possible.")
    elif i.load_type in ("Dynamic", "Shock") and "orientation" not in user_text:
        _add(findings, id="AM5b", category="DFM", severity="HIGH", title="Orientation not specified (dynamic load)",
             why="Under dynamic load, layer direction strongly affects fatigue life. Anisotropy and fatigue are critical.", rec="Specify build orientation relative to load path; avoid transverse layers in critical zones.")

    # Post-processing / machining
    if "post-process" in user_text or "post process" in user_text or "machining" in user_text:
        _add(findings, id="AM6", category="DFM", severity="MEDIUM", title="Post-processing / machining (hybrid)",
             why="Post-machining adds ops and fixturing; design for access and datum.", rec="Add datum features for machining; avoid inaccessible surfaces for critical dimensions.")

    # Enclosed cavity / trapped volume (material-aware)
    is_metal = i.material in ("Aluminum", "Steel")
    if s.pocket_aspect_class in ("Risky", "Extreme"):
        sev = "HIGH" if (is_metal and s.pocket_aspect_class == "Extreme") else "MEDIUM"
        if is_metal:
            _add(findings, id="AM7", category="DFM", severity=sev, title="Enclosed cavity / trapped volume",
                 why="Enclosed cavities trap powder in metal AM; can cause defects and contamination.", rec="Add drain holes or avoid fully enclosed volumes; design for powder removal.")
        else:
            _add(findings, id="AM7", category="DFM", severity=sev, title="Enclosed cavity / trapped resin or support access",
                 why="Enclosed cavities can trap resin (SLS) or block support removal; affect cleaning and drainage.", rec="Add drain/vent holes or access for support removal; ensure cleaning access.")
    elif "enclosed" in user_text or "cavity" in user_text or "trapped powder" in user_text or "trapped resin" in user_text:
        sev = "HIGH" if is_metal else "MEDIUM"
        if is_metal:
            _add(findings, id="AM7b", category="DFM", severity=sev, title="Enclosed cavity / trapped powder (design hint)",
                 why="Trapped powder in metal AM causes defects and contamination.", rec="Ensure powder can escape; add vents or drain holes.")
        else:
            _add(findings, id="AM7b", category="DFM", severity=sev, title="Enclosed cavity / trapped resin or support access (design hint)",
                 why="Trapped resin or blocked support removal affects quality and cleaning.", rec="Add vents or drainage; ensure support removal access.")

    # High feature variety (print time & reliability)
    if s.feature_variety == "High":
        _add(findings, id="AM8", category="DFM", severity="MEDIUM", title="High feature variety (print time)",
             why="Many distinct features increase print time and failure risk.", rec="Consolidate geometry where possible; use consistent wall thicknesses.")

    # High volume + simple geometry (AM may be wrong choice)
    if (i.production_volume == "Production" and
        s.feature_variety in ("Low", "Medium") and
        s.pocket_aspect_class == "OK" and
        s.hole_depth_class in ("None", "Moderate")):
        _add(findings, id="AM9", category="DFM", severity="HIGH", title="High volume + relatively simple geometry (AM may be wrong choice)",
             why="AM unit cost often loses to traditional processes at high volumes for simple parts.", rec="Compare against CNC or molding/casting depending on material; use AM for iteration/complexity, not default.")

    # Critical features inaccessible for post-processing/inspection
    if i.tolerance_criticality == "High" and s.accessibility_risk == "High":
        _add(findings, id="AM10", category="DFM", severity="HIGH", title="Tight requirements but poor access for post-processing/inspection",
             why="If precision surfaces can't be reached for machining/finishing/measurement, production quality and acceptance are at risk.", rec="Redesign for access, add datum/reference features, plan machining/inspection approach.")

    # Heuristic hint for RAG: when Plastic, prefer FDM/common docs over metal LPBF
    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    out: dict = {"findings": findings, "trace": trace_delta}
    if i.material == "Plastic":
        out["am_subprocess_hint"] = "FDM"
    return out
