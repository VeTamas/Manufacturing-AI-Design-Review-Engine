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


def run_mim_rules(state: GraphState) -> dict:
    """MIM-specific design review and DFM rules. Deterministic heuristics based on inputs and part_summary."""
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

    # MIM1: Process sanity check
    if i.production_volume == "Proto" or s.part_size == "Large":
        _add(
            findings,
            id="MIM1",
            category="DFM",
            severity="MEDIUM",
            title="MIM process fit: low volume or large part (tooling/economics risk)",
            why="MIM requires tooling investment; best for small precision metal parts at medium/high volume. Large parts or proto volumes may indicate process mismatch.",
            rec="Confirm volume economics; consider casting/forging for large parts; CNC/AM for prototypes.",
        )

    # MIM2: Uniform wall thickness
    if s.min_wall_thickness in ("Thin", "Medium") and s.part_size == "Small":
        # Check for non-uniformity indicators
        if any(kw in user_text for kw in ("thick", "thin", "varying", "non-uniform", "gradient", "transition")):
            _add(
                findings,
                id="MIM2",
                category="DFM",
                severity="HIGH",
                title="Non-uniform wall thickness (sintering distortion risk)",
                why="Non-uniform thickness creates mass gradients that lead to uneven shrinkage and distortion during sintering.",
                rec="Aim for uniform wall thickness; use gradual transitions; avoid abrupt thickness changes.",
            )

    # MIM3: Thickness transitions
    if s.min_internal_radius == "Small" and s.min_wall_thickness in ("Thin", "Medium"):
        _add(
            findings,
            id="MIM3",
            category="DFM",
            severity="MEDIUM",
            title="Abrupt thickness transitions (distortion risk)",
            why="Sharp transitions concentrate mass and create distortion risk during sintering.",
            rec="Use gradual thickness transitions; avoid mass concentrations; smooth section changes.",
        )

    # MIM4: Symmetry / balanced mass
    if s.accessibility_risk == "High" and s.feature_variety == "High":
        _add(
            findings,
            id="MIM4",
            category="DFM",
            severity="HIGH",
            title="Asymmetric mass distribution (warpage risk)",
            why="Asymmetric geometry creates uneven shrinkage and warpage during sintering.",
            rec="Balance mass distribution; add symmetry where possible; use flat support faces; consider sintering supports.",
        )

    # MIM5: Sharp corners
    if s.min_internal_radius == "Small":
        severity = "HIGH" if i.load_type in ("Dynamic", "Shock") else "MEDIUM"
        _add(
            findings,
            id="MIM5",
            category="DFM",
            severity=severity,
            title="Sharp corners (stress concentration / defect risk)",
            why="Sharp corners concentrate stress and increase crack/defect risk during debinding and sintering.",
            rec="Increase fillet radii; use generous blends; avoid sharp internal corners.",
        )

    # MIM6: Debinding pathways
    if any(kw in user_text for kw in ("enclosed", "closed", "hollow", "void", "cavity", "trapped")):
        _add(
            findings,
            id="MIM6",
            category="DFM",
            severity="HIGH",
            title="Enclosed cavities / poor debinding pathways (crack/defect risk)",
            why="Trapped binder or powder in enclosed voids can cause defects or cracks during debinding.",
            rec="Add venting channels; avoid fully enclosed voids; ensure binder removal pathways.",
        )

    # MIM7: Enclosed cavities (explicit check)
    if any(kw in user_text for kw in ("closed void", "sealed cavity", "internal void", "trapped volume")):
        _add(
            findings,
            id="MIM7",
            category="DFM",
            severity="HIGH",
            title="Closed internal voids (binder/powder trap risk)",
            why="Closed voids can trap binder or powder, causing defects during debinding and sintering.",
            rec="Add venting; redesign to avoid closed voids; consider open-cell structure or post-processing.",
        )

    # MIM8: Tolerance expectations
    if i.tolerance_criticality == "High":
        _add(
            findings,
            id="MIM8",
            category="DFM",
            severity="MEDIUM",
            title="Tight tolerances imply post-machining",
            why="MIM achieves good tolerances (~±0.5%) but precision interfaces often require post-machining.",
            rec="Plan post-machining for critical dimensions; add machining allowance; specify datum strategy.",
        )

    # MIM9: Surface finish
    if any(kw in user_text for kw in ("cosmetic", "finish", "polish", "visible", "exposed", "surface quality")):
        _add(
            findings,
            id="MIM9",
            category="DFM",
            severity="LOW",
            title="Cosmetic surface finish requirement",
            why="MIM provides good as-sintered finish (~Ra 0.8–1.6 µm) but cosmetic-critical surfaces may need finishing/polishing.",
            rec="Mark cosmetic surfaces; plan finishing/polishing sequence; specify surface requirements.",
        )

    # MIM10: Part size/weight sweet spot
    if s.part_size == "Large":
        _add(
            findings,
            id="MIM10",
            category="DFM",
            severity="MEDIUM",
            title="Large part size (consider casting/forging alternative)",
            why="MIM is optimized for small parts (<75–100 mm, ~0.5–50 g). Large parts favor casting or forging.",
            rec="Evaluate casting/forging for large parts; confirm MIM feasibility with supplier for oversized parts.",
        )
    elif s.part_size == "Small" and s.feature_variety == "High":
        _add(
            findings,
            id="MIM10",
            category="DFM",
            severity="LOW",
            title="Small complex part (strong MIM fit)",
            why="Small complex metal parts with many features are ideal for MIM economics.",
            rec="Confirm feature density and tooling feasibility; optimize for MIM process.",
        )

    # MIM11: Feature density
    if s.feature_variety == "High" and i.production_volume in ("Small batch", "Production"):
        _add(
            findings,
            id="MIM11",
            category="DFM",
            severity="LOW",
            title="High feature density favors MIM over CNC at scale",
            why="Many small features favor MIM economics over extensive CNC machining at production volumes.",
            rec="Confirm tooling complexity; evaluate MIM vs CNC cost break-even; optimize feature consolidation.",
        )

    # MIM12: Tooling/economics
    if i.production_volume == "Proto":
        _add(
            findings,
            id="MIM12",
            category="DFM",
            severity="MEDIUM",
            title="Low volume penalizes MIM tooling amortization",
            why="MIM requires significant tooling investment; low volumes cannot amortize tooling cost effectively.",
            rec="Consider CNC or AM for prototypes; confirm volume economics before committing to MIM tooling.",
        )

    # MIM13: Threads/fine details
    if any(kw in user_text for kw in ("thread", "threading", "tap", "tapping", "fine detail", "small feature")):
        if i.tolerance_criticality == "High":
            _add(
                findings,
                id="MIM13",
                category="DFM",
                severity="MEDIUM",
                title="Critical threads/fine details may require post-processing",
                why="MIM can mold threads and fine details, but critical tolerance threads often need chasing/tapping for precision.",
                rec="Plan post-machining for critical threads; add allowance; specify thread tolerance requirements.",
            )
        else:
            _add(
                findings,
                id="MIM13",
                category="DFM",
                severity="LOW",
                title="Threads/fine details feasible but may need finishing",
                why="MIM can produce threads and fine details, but precision-critical features may need post-processing.",
                rec="Mark critical threads; plan finishing if tolerance-critical; confirm moldability with supplier.",
            )

    # MIM14: Heat treatment
    if any(kw in user_text for kw in ("heat treat", "hardness", "quench", "temper", "ht", "heat treatment")):
        if i.material in ("Steel", "Aluminum"):
            _add(
                findings,
                id="MIM14",
                category="DFM",
                severity="MEDIUM",
                title="Heat treatment requirement impacts distortion and machining plan",
                why="Heat treatment can distort parts; affects final tolerances and sequencing of machining/finishing.",
                rec="Plan machining after heat treat for critical dimensions; specify hardness/HT condition; add allowance for distortion.",
            )

    # MIM15: Distortion controls
    if s.min_wall_thickness == "Thin" and s.accessibility_risk in ("Medium", "High"):
        _add(
            findings,
            id="MIM15",
            category="DFM",
            severity="HIGH",
            title="Thin cantilevers / unsupported geometry (distortion risk)",
            why="Thin unsupported sections distort easily during sintering; lack of support faces increases warpage risk.",
            rec="Add support flats; avoid thin cantilevers; consider sintering supports/fixturing; balance geometry.",
        )

    # MIM16: Hybrid manufacturing
    if i.tolerance_criticality == "High" and any(kw in user_text for kw in ("critical", "precision", "mating", "interface", "datum")):
        _add(
            findings,
            id="MIM16",
            category="DFM",
            severity="MEDIUM",
            title="Hybrid manufacturing: identify critical faces/holes for post-machining",
            why="MIM provides near-net shape; critical interfaces often require post-machining for precision.",
            rec="Identify critical faces/holes; add machining stock; plan fixturing/datum strategy; sequence operations.",
        )

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
