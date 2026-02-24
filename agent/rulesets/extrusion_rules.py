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


def run_extrusion_rules(state: GraphState) -> dict:
    """Extrusion-specific design review and DFM rules. Deterministic heuristics based on inputs and part_summary."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    findings: list[Finding] = []
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()

    # EXTR1: Variable cross-section / 3D features (process mismatch)
    if any(kw in user_text for kw in ("variable cross", "variable section", "3d feature", "complex 3d", "varying cross")):
        _add(
            findings,
            id="EXTR1",
            category="DFM",
            severity="HIGH",
            title="Variable cross-section or heavy 3D features (extrusion mismatch risk)",
            why="Extrusion produces constant cross-section profiles; variable geometry indicates process mismatch.",
            rec="Consider CNC or casting for variable cross-section; or redesign for constant profile.",
        )

    # EXTR2: Non-uniform wall thickness
    if s.min_wall_thickness == "Thin" and s.part_size in ("Medium", "Large"):
        _add(
            findings,
            id="EXTR2",
            category="DFM",
            severity="HIGH",
            title="Non-uniform wall thickness (distortion/warpage risk)",
            why="Non-uniform thickness leads to uneven cooling, residual stress, and warping in extrusion.",
            rec="Aim for adjacent wall thickness ratio < 2:1; use smooth transitions; avoid thin flanges.",
        )
    elif s.min_wall_thickness == "Thin":
        _add(
            findings,
            id="EXTR2",
            category="DFM",
            severity="MEDIUM",
            title="Thin sections (distortion/warpage risk)",
            why="Thin sections increase distortion and warpage risk in extrusion.",
            rec="Thicken walls; maintain uniform thickness; use radiused transitions.",
        )

    # EXTR3: Abrupt thickness changes
    if s.min_internal_radius == "Small" and s.min_wall_thickness in ("Thin", "Medium"):
        _add(
            findings,
            id="EXTR3",
            category="DFM",
            severity="MEDIUM",
            title="Abrupt thickness changes (stress and flow risk)",
            why="Sharp transitions concentrate stress and disrupt metal flow during extrusion.",
            rec="Use radiused transitions; avoid abrupt section changes; smooth thickness gradients.",
        )

    # EXTR4: Sharp internal corners
    if s.min_internal_radius == "Small":
        severity = "HIGH" if i.load_type in ("Dynamic", "Shock") else "MEDIUM"
        _add(
            findings,
            id="EXTR4",
            category="DFM",
            severity=severity,
            title="Sharp internal corners (die stress / flow issues)",
            why="Sharp corners increase die stress and impede metal flow; cracking risk under load.",
            rec="Increase fillet radii; use generous blends; avoid sharp internal corners.",
        )

    # EXTR5: Thin fins / long unsupported flanges
    if s.min_wall_thickness == "Thin" and s.accessibility_risk in ("Medium", "High"):
        _add(
            findings,
            id="EXTR5",
            category="DFM",
            severity="HIGH",
            title="Thin fins / long unsupported flanges (distortion + die fragility)",
            why="Thin fins and long flanges distort easily and increase die fragility risk.",
            rec="Thicken fins; add ribs; reduce flange length; consider support structure.",
        )

    # EXTR6: Asymmetric profile
    if s.accessibility_risk == "High" and s.feature_variety == "High":
        _add(
            findings,
            id="EXTR6",
            category="DFM",
            severity="MEDIUM",
            title="Highly asymmetric profile (bow/twist/distortion risk)",
            why="Asymmetric profiles increase bow, twist, and distortion risk during extrusion.",
            rec="Balance profile; add symmetry where possible; plan straightening if needed.",
        )

    # EXTR7: Hollow / multi-void profiles
    if any(kw in user_text for kw in ("hollow", "multi-void", "hollow profile", "hollow section")):
        if i.tolerance_criticality == "High":
            _add(
                findings,
                id="EXTR7",
                category="DFM",
                severity="HIGH",
                title="Hollow / multi-void profile with tight tolerance (cost + complexity)",
                why="Hollow profiles increase tooling cost and extrusion speed limits; tight tolerances compound risk.",
                rec="Evaluate solid redesign; confirm die capacity; plan post-machining for critical dims.",
            )
        else:
            _add(
                findings,
                id="EXTR7",
                category="DFM",
                severity="MEDIUM",
                title="Hollow / multi-void profile (cost + tooling complexity)",
                why="Hollow profiles increase tooling cost, slower extrusion speed, higher design complexity.",
                rec="Confirm feasibility with supplier; plan for slower production; consider solid alternative.",
            )

    # EXTR8: Semi-hollow / tongue-like features
    if any(kw in user_text for kw in ("semi-hollow", "tongue", "semihollow", "tongue ratio")):
        _add(
            findings,
            id="EXTR8",
            category="DFM",
            severity="HIGH",
            title="Semi-hollow / tongue-like features (die break risk)",
            why="Semi-hollow shapes with thin tongues create die break risk and tooling fragility.",
            rec="Strengthen tongue; rebalance profile; avoid extreme tongue ratios.",
        )

    # EXTR9: Tight tolerances
    if i.tolerance_criticality == "High":
        _add(
            findings,
            id="EXTR9",
            category="DFM",
            severity="MEDIUM",
            title="Tight tolerances (plan post-machining)",
            why="Extrusion tolerances are good but generally inferior to precision machining; tight interfaces need finishing.",
            rec="Plan post-machining for critical interfaces; add allowance; specify datum strategy.",
        )

    # EXTR10: Surface finish / exposed surfaces
    if any(kw in user_text for kw in ("cosmetic", "exposed", "finish", "anodize", "anodizing", "visible surface")):
        _add(
            findings,
            id="EXTR10",
            category="DFM",
            severity="LOW",
            title="Exposed / cosmetic surfaces (finish handling)",
            why="Exposed surfaces require finish planning; extrusion lines and die marks may be visible.",
            rec="Mark exposed surfaces; plan anodizing/finish sequence; specify surface requirements.",
        )

    # EXTR11: Secondary operations
    if any(kw in user_text for kw in ("drill", "tap", "mill", "machining", "secondary", "post-machining")):
        _add(
            findings,
            id="EXTR11",
            category="DFM",
            severity="MEDIUM",
            title="Secondary operations (allowance + fixturing)",
            why="Drilling, tapping, milling are typically post-extrusion; require allowance and fixturing plan.",
            rec="Add machining allowance; plan fixturing/datum faces; sequence secondary ops.",
        )

    # EXTR12: Assembly consolidation opportunity (positive)
    if any(kw in user_text for kw in ("assembly", "assemblies", "weld", "joining", "multi-part")):
        _add(
            findings,
            id="EXTR12",
            category="DFM",
            severity="LOW",
            title="Assembly consolidation opportunity",
            why="Extrusions allow integration of slots, channels, bosses to reduce assembly and joining.",
            rec="Consider integrated features (slots, channels) to reduce part count and joining cost.",
        )

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
