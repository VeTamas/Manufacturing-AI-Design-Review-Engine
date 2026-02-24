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


def run_fdm_rules(state: GraphState) -> dict:
    """FDM-specific design review and DFM rules (MVP)."""
    i = state["inputs"]
    s = state["part_summary"]
    findings: list[Finding] = []

    # Overhang / support risk (thin walls, extreme pockets as proxy for complex geometry)
    if s.min_wall_thickness == "Thin":
        sev = "HIGH" if s.part_size != "Small" else "MEDIUM"
        _add(
            findings,
            id="FDM1",
            category="DFM",
            severity=sev,
            title="Thin walls (overhang & support risk)",
            why="Thin FDM walls often need supports, increasing print time, material use, and post-processing.",
            rec="Thicken walls above ~1 mm where possible; orient to minimize overhangs; consider support-free angles.",
        )

    if s.pocket_aspect_class in ("Risky", "Extreme"):
        _add(
            findings,
            id="FDM2",
            category="DFM",
            severity="HIGH" if s.pocket_aspect_class == "Extreme" else "MEDIUM",
            title="Deep/narrow cavities (bridging & support risk)",
            why="Deep narrow features require supports or bridging; can sag or fail.",
            rec="Widen cavities, add drain holes, or split part; avoid fully enclosed volumes.",
        )

    # Small holes
    if s.min_internal_radius == "Small":
        _add(
            findings,
            id="FDM3",
            category="DFM",
            severity="MEDIUM",
            title="Small holes / internal features",
            why="Small holes often need support or drilling post-print; accuracy is limited.",
            rec="Use minimum hole diameter ~2× nozzle; consider drilling after print for precision.",
        )

    # Anisotropy / load direction
    if i.load_type in ("Dynamic", "Shock") and s.min_wall_thickness == "Thin":
        _add(
            findings,
            id="FDM4",
            category="DESIGN_REVIEW",
            severity="HIGH",
            title="Anisotropy risk (load vs. layer direction)",
            why="FDM parts are weaker across layers; thin sections under dynamic load are prone to delamination.",
            rec="Orient layer lines along principal stress; increase wall thickness or add ribs; consider Annealing.",
        )

    # Support requirement proxy (accessibility / complex geometry)
    if s.accessibility_risk in ("Medium", "High"):
        _add(
            findings,
            id="FDM5",
            category="DFM",
            severity="HIGH" if s.accessibility_risk == "High" else "MEDIUM",
            title="Complex geometry (support & orientation)",
            why="Hard-to-reach features imply overhangs and support; affects finish and accuracy.",
            rec="Simplify geometry; design self-supporting; minimize supports; plan build orientation.",
        )

    # Tolerance expectations
    if i.tolerance_criticality == "High":
        _add(
            findings,
            id="FDM6",
            category="DFM",
            severity="MEDIUM",
            title="Tight tolerance expectations for FDM",
            why="FDM typically holds ±0.1–0.5 mm; warping and layer effects limit precision.",
            rec="Relax non-critical tolerances; use machining for critical fits; account for post-processing.",
        )

    # High variety => many retractions, stringing, time
    if s.feature_variety == "High":
        _add(
            findings,
            id="FDM7",
            category="DFM",
            severity="MEDIUM",
            title="High feature variety (print time & reliability)",
            why="Many distinct features increase retractions, stringing risk, and print time.",
            rec="Consolidate geometry where possible; use consistent wall thicknesses and radii.",
        )

    # Large part + no datums => warp, adhesion
    if s.part_size == "Large" and not s.has_clamping_faces:
        _add(
            findings,
            id="FDM8",
            category="DFM",
            severity="HIGH",
            title="Large part without clear build base",
            why="Large prints need a flat, stable base; warp and adhesion issues increase with size.",
            rec="Add flat base; avoid large overhangs at bed; consider splitting part.",
        )

    trace_delta = [f"Rule triggered: {f.title} → HIGH severity" for f in findings if f.severity == "HIGH"]
    return {"findings": findings, "trace": trace_delta}
