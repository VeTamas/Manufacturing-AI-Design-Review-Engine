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


def run_compression_molding_rules(state: GraphState) -> dict:
    """Compression molding-specific design review and DFM rules. Deterministic heuristics based on inputs and part_summary."""
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

    # COMP1: Process fit
    if i.production_volume in ("Small batch", "Production"):
        _add(
            findings,
            id="COMP1",
            category="DFM",
            severity="LOW",
            title="Process fit: thermoset/composite parts, moderate/high volume; curing cycle",
            why="Compression molding suits thermoset and composite parts at moderate/high volumes; cure cycle time is a key driver.",
            rec="Confirm material (thermoset/composite) and volume economics; plan for cure cycle time; evaluate tooling cost.",
        )
    elif i.production_volume == "Proto":
        _add(
            findings,
            id="COMP1",
            category="DFM",
            severity="MEDIUM",
            title="Low volume may favor machining or AM over compression molding",
            why="Compression molding requires tooling investment; low volumes may not justify tooling cost.",
            rec="Evaluate machining or AM alternatives for prototypes; confirm volume economics before committing to compression tooling.",
        )

    # COMP2: Cure shrinkage/warpage
    if s.part_size in ("Medium", "Large") and s.feature_variety == "Low":
        _add(
            findings,
            id="COMP2",
            category="DFM",
            severity="MEDIUM",
            title="Large flat surfaces risk warpage from cure shrinkage",
            why="Large flat surfaces are prone to warpage due to cure shrinkage and thermal gradients; asymmetric designs increase risk.",
            rec="Add symmetry where possible; use ribs for stiffness; plan for warpage compensation; consider support during cure.",
        )

    # COMP3: Uniform thickness and mass balance
    if s.min_wall_thickness in ("Thin", "Medium") and any(kw in user_text for kw in ("thick", "heavy", "mass", "island")):
        _add(
            findings,
            id="COMP3",
            category="DFM",
            severity="HIGH",
            title="Thick-heavy islands create flow and cure issues",
            why="Thick-heavy sections create uneven flow, cure gradients, and warpage risk; mass imbalance increases distortion.",
            rec="Avoid thick-heavy islands; use gradual thickness transitions; balance mass distribution; consider ribbing instead of thick sections.",
        )

    # COMP4: Draft & release
    if s.accessibility_risk in ("Medium", "High"):
        _add(
            findings,
            id="COMP4",
            category="DFM",
            severity="MEDIUM",
            title="Draft required for part release; avoid negative draft",
            why="Insufficient draft makes part removal difficult and can cause damage; negative draft requires complex tooling.",
            rec="Add draft angles to all vertical surfaces; avoid undercuts or plan for split tooling; improve release geometry.",
        )

    # COMP5: Radii/fillets
    if s.min_internal_radius == "Small":
        severity = "HIGH" if any(kw in user_text for kw in ("stress", "load", "structural", "fiber")) else "MEDIUM"
        _add(
            findings,
            id="COMP5",
            category="DFM",
            severity=severity,
            title="Sharp corners increase stress concentration and flow issues",
            why="Sharp corners concentrate stress and impede material flow; increase void risk and reduce strength.",
            rec="Increase fillet radii; use generous blends; avoid sharp transitions; improve flow paths.",
        )

    # COMP6: Flash control
    if any(kw in user_text for kw in ("flash", "parting line", "trim", "cosmetic", "visible")):
        _add(
            findings,
            id="COMP6",
            category="DFM",
            severity="MEDIUM",
            title="Flash control: parting line and charge control; trimming required",
            why="Excess material escapes at mold interface creating flash; requires trimming and affects cosmetics.",
            rec="Plan precise charge control; ensure mold sealing quality; design trim flanges; plan trimming operations.",
        )

    # COMP7: Charge placement
    if any(kw in user_text for kw in ("charge", "charge placement", "flow", "fiber", "orientation", "strength")):
        _add(
            findings,
            id="COMP7",
            category="DFM",
            severity="HIGH",
            title="Charge placement impacts flow and fiber orientation; critical for strength zones",
            why="Charge position strongly affects fiber orientation, void formation, and fill completeness; poor placement creates weak zones.",
            rec="Plan charge placement for optimal flow; align with load paths for fiber-reinforced parts; avoid air traps; consider flow study.",
        )

    # COMP8: Fiber orientation effects
    if any(kw in user_text for kw in ("fiber", "glass fiber", "carbon fiber", "composite", "orientation", "anisotropic")):
        _add(
            findings,
            id="COMP8",
            category="DFM",
            severity="MEDIUM",
            title="Fiber orientation affects strength; align with load paths where possible",
            why="Fiber direction determines stiffness, fatigue resistance, and impact performance; orientation depends on flow path and charge placement.",
            rec="Design flow paths to align fibers with load paths; plan charge placement for desired orientation; warn about anisotropy if random fiber.",
        )

    # COMP9: Venting/air traps
    if s.pocket_aspect_class in ("Risky", "Extreme") or any(kw in user_text for kw in ("void", "air trap", "vent", "venting", "sealed", "pocket")):
        _add(
            findings,
            id="COMP9",
            category="DFM",
            severity="HIGH",
            title="Trapped air causes voids; add vents and avoid sealed pockets",
            why="Trapped air creates voids and weak zones; deep pockets and sealed cavities increase void risk.",
            rec="Add venting channels; avoid fully sealed pockets; ensure air escape paths; plan vent locations.",
        )

    # COMP10: Tooling & parting line planning
    if s.accessibility_risk == "High" and any(kw in user_text for kw in ("parting line", "tooling", "mold", "shutoff")):
        _add(
            findings,
            id="COMP10",
            category="DFM",
            severity="MEDIUM",
            title="Define parting line early; minimize complex shutoffs",
            why="Parting line location affects tooling complexity, flash location, and part quality; complex shutoffs increase cost and risk.",
            rec="Define parting line early in design; minimize complex shutoffs; simplify tooling geometry; plan for flash location.",
        )

    # COMP11: Tolerances
    if i.tolerance_criticality == "High":
        _add(
            findings,
            id="COMP11",
            category="DFM",
            severity="MEDIUM",
            title="Thermoset cure variability; critical interfaces need post-machining",
            why="Thermosets shrink during curing causing dimensional variation; tight tolerances require compensation or post-machining.",
            rec="Plan secondary operations for critical interfaces; add machining allowance; specify datum strategy; compensate for shrinkage.",
        )

    # COMP12: Secondary ops
    if any(kw in user_text for kw in ("trim", "trimming", "drill", "machining", "secondary", "post-machining")):
        _add(
            findings,
            id="COMP12",
            category="DFM",
            severity="MEDIUM",
            title="Secondary ops: trimming flash, drilling, machining; plan datums/fixturing",
            why="Compression molded parts require trimming flash and often need drilling or machining for critical features.",
            rec="Plan trimming operations; design trim flanges; plan drilling/machining with fixturing; add datum features for secondary ops.",
        )

    # COMP13: Surface finish/cosmetics
    if any(kw in user_text for kw in ("cosmetic", "surface finish", "visible", "exposed", "a-surface")):
        _add(
            findings,
            id="COMP13",
            category="DFM",
            severity="HIGH",
            title="Flash on cosmetic surfaces is high risk; mold finish drives appearance",
            why="Flash on cosmetic surfaces is highly visible and unacceptable; mold finish quality directly affects part appearance.",
            rec="Plan parting line away from cosmetic surfaces; ensure mold finish quality; plan flash removal carefully; consider secondary finishing.",
        )

    # COMP14: Inserts / features
    if any(kw in user_text for kw in ("insert", "inserts", "boss", "bosses", "feature")):
        _add(
            findings,
            id="COMP14",
            category="DFM",
            severity="MEDIUM",
            title="Inserts require heat and placement consideration; avoid large bosses requiring high flow",
            why="Inserts must withstand cure temperature; large bosses require high material flow and increase void risk.",
            rec="Plan insert placement and heat resistance; avoid large bosses; simplify features requiring high flow; consider post-machining for complex features.",
        )

    # COMP15: Cycle time driver
    if s.min_wall_thickness == "High" or any(kw in user_text for kw in ("thick", "thick section", "cure time", "cycle")):
        _add(
            findings,
            id="COMP15",
            category="DFM",
            severity="MEDIUM",
            title="Thick sections increase cure cycle time and void risk",
            why="Cure time dominates cycle time; thick sections require longer cure and increase void risk.",
            rec="Minimize thick sections; use ribbing for stiffness; plan for longer cycle times; ensure adequate venting for thick sections.",
        )

    # COMP16: Process mismatch
    if s.part_size == "Small" and s.feature_variety == "High" and any(kw in user_text for kw in ("boss", "bosses", "fine detail", "injection")):
        _add(
            findings,
            id="COMP16",
            category="DFM",
            severity="MEDIUM",
            title="Small part with many bosses may favor injection molding",
            why="Small parts with many fine features often favor injection molding over compression molding.",
            rec="Evaluate injection molding alternative; confirm compression molding feasibility; consider process mismatch risk.",
        )

    # COMP17: Material selection
    if any(kw in user_text for kw in ("thermoset", "thermoplastic", "heat resistance", "temperature")):
        _add(
            findings,
            id="COMP17",
            category="DFM",
            severity="LOW",
            title="Thermoset vs thermoplastic implications; heat resistance benefit",
            why="Compression molding typically uses thermosets which offer superior heat resistance; thermoplastics may favor injection molding.",
            rec="Confirm material selection (thermoset vs thermoplastic); evaluate heat resistance requirements; consider process-material compatibility.",
        )

    # COMP18: Hybrid
    if i.tolerance_criticality == "High" and any(kw in user_text for kw in ("critical", "precision", "mating", "interface", "datum")):
        _add(
            findings,
            id="COMP18",
            category="DFM",
            severity="MEDIUM",
            title="Hybrid: machine only critical surfaces post-mold; keep molded features simple",
            why="Compression molding provides near-net shape; critical interfaces often require post-machining for precision.",
            rec="Identify critical surfaces/holes for post-machining; add machining stock; plan fixturing/datum strategy; keep molded features simple.",
        )

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
