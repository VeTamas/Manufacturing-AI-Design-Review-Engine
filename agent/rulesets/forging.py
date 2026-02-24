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


def run_forging_rules(state: GraphState) -> dict:
    """Forging-specific design review and DFM rules. Deterministic heuristics based on inputs and part_summary."""
    i = state.get("inputs")
    s = state.get("part_summary")
    if not i or not s:
        return {"findings": [], "trace": []}

    findings: list[Finding] = []
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()

    # Safe read confidence_inputs.has_2d_drawing
    conf_inputs = state.get("confidence_inputs")
    has_2d_drawing = False
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d_drawing = bool(conf_inputs.get("has_2d_drawing", False))
        else:
            has_2d_drawing = bool(getattr(conf_inputs, "has_2d_drawing", False))

    # Detect forging subprocess hint from keywords
    forging_subprocess_hint = None
    if any(kw in user_text for kw in ("closed-die", "closed die", "impression", "flash", "parting line", "draft")):
        forging_subprocess_hint = "CLOSED_DIE"
    elif any(kw in user_text for kw in ("open-die", "open die", "upset", "cogging")):
        forging_subprocess_hint = "OPEN_DIE"
    elif any(kw in user_text for kw in ("blocker", "preform", "hybrid")):
        forging_subprocess_hint = "HYBRID"

    # FORG1: Tight tolerances assumed as-forged
    if i.tolerance_criticality == "High":
        _add(
            findings,
            id="FORG1",
            category="DFM",
            severity="HIGH",
            title="Tight tolerances assumed as-forged",
            why="Forging is near-net-shape; precision features usually require machining + datum plan.",
            rec="Mark machined surfaces; define datums/GD&T; leave stock for machining; plan inspection.",
        )

    # FORG2: Tight tolerances without 2D drawing
    if i.tolerance_criticality == "High" and not has_2d_drawing:
        _add(
            findings,
            id="FORG2",
            category="DFM",
            severity="HIGH",
            title="Tight tolerances without 2D drawing (machining plan ambiguity)",
            why="Without a drawing, it's unclear what must be machined/inspected vs as-forged.",
            rec="Provide 2D drawing with datums/GD&T; identify machined features; specify acceptance.",
        )

    # FORG3: Thin sections / fill-and-flow risk
    if s.min_wall_thickness == "Thin":
        severity = "HIGH" if (i.load_type in ("Dynamic", "Shock") or s.part_size in ("Medium", "Large")) else "MEDIUM"
        _add(
            findings,
            id="FORG3",
            category="DFM",
            severity=severity,
            title="Thin sections / fill-and-flow risk",
            why="Thin/extreme regions can be hard to fill and increase cracking/underfill risk; also weak under load.",
            rec="Increase section thickness; avoid extreme thin webs; smooth transitions; validate with forge supplier.",
        )

    # FORG4: Small radii / sharp transitions
    if s.min_internal_radius == "Small":
        severity = "HIGH" if i.load_type in ("Dynamic", "Shock") else "MEDIUM"
        _add(
            findings,
            id="FORG4",
            category="DFM",
            severity=severity,
            title="Small radii / sharp transitions (strain concentration)",
            why="Sharp transitions concentrate strain during forging and later stress in service; cracking risk rises.",
            rec="Increase fillet radii; use generous blends; avoid abrupt section changes.",
        )

    # FORG5: Die complexity / undercut or access risk
    if s.accessibility_risk in ("Medium", "High"):
        severity = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
        _add(
            findings,
            id="FORG5",
            category="DFM",
            severity=severity,
            title="Die complexity / undercut or access risk",
            why="Complex geometry increases die cost and risk; may force additional operations or process change.",
            rec="Simplify geometry; avoid undercuts; consider split part or alternative process.",
        )

    # FORG6: Production + high complexity
    if i.production_volume == "Production" and s.feature_variety == "High":
        _add(
            findings,
            id="FORG6",
            category="DFM",
            severity="HIGH",
            title="Production + high complexity (tooling + QA overhead)",
            why="High complexity increases die development time, maintenance, and inspection burden at production scale.",
            rec="Standardize features; reduce variety; confirm achievable tolerances with the forging supplier early.",
        )

    # FORG7: Closed-die draft/parting strategy not discussed
    if (
        forging_subprocess_hint == "CLOSED_DIE"
        and "draft" not in user_text
        and (s.min_internal_radius == "Small" or s.accessibility_risk in ("Medium", "High"))
    ):
        severity = "HIGH" if (s.min_internal_radius == "Small" or s.accessibility_risk == "High") else "MEDIUM"
        _add(
            findings,
            id="FORG7",
            category="DFM",
            severity=severity,
            title="Closed-die: draft/parting strategy not discussed",
            why="Draft and parting line decisions strongly affect feasibility, die wear, and surface damage risk.",
            rec="Confirm draft targets, parting line, flash location, and ejection; avoid zero-draft on key faces.",
        )

    # FORG8: Heat treat requirement impacts distortion and machining plan
    ht_keywords = "heat treat" in user_text or "hardness" in user_text or "quench" in user_text
    mat = getattr(i, "material", None) or ""
    if ht_keywords and mat in ("Steel", "Stainless", "Titanium"):
        _add(
            findings,
            id="FORG8",
            category="DFM",
            severity="MEDIUM",
            title="Heat treat requirement impacts distortion and machining plan",
            why="Heat treatment can distort; affects final tolerances and sequencing of machining/finishing.",
            rec="Plan machining after heat treat for critical dims; specify hardness/HT condition; add allowance.",
        )

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    out: dict = {"findings": findings, "trace": trace_delta}
    if forging_subprocess_hint:
        out["forging_subprocess_hint"] = forging_subprocess_hint
    return out
