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


def run_thermoforming_rules(state: GraphState) -> dict:
    """Thermoforming-specific design review and DFM rules. Deterministic heuristics based on inputs and part_summary."""
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

    # THERMO1: Process fit
    if s.part_size in ("Medium", "Large") and i.production_volume in ("Small batch", "Production"):
        _add(
            findings,
            id="THERMO1",
            category="DFM",
            severity="LOW",
            title="Process fit: large parts, moderate volume, lower tooling cost; one-side detail",
            why="Thermoforming suits large sheet-formed parts at moderate volumes with lower tooling cost than injection molding; detail reproduction is best on one side.",
            rec="Confirm part size and volume economics; plan for one-side detail dominance; consider trimming requirements.",
        )
    elif s.part_size == "Small" and s.feature_variety == "High":
        _add(
            findings,
            id="THERMO1",
            category="DFM",
            severity="MEDIUM",
            title="Small part with high feature variety (process mismatch risk)",
            why="Small parts with many features often favor injection molding or CNC over thermoforming.",
            rec="Evaluate injection molding or CNC alternatives; confirm thermoforming feasibility with supplier.",
        )

    # THERMO2: Wall thinning risk
    if any(kw in user_text for kw in ("deep draw", "deep", "draw ratio", "depth")):
        if s.min_wall_thickness == "Thin":
            _add(
                findings,
                id="THERMO2",
                category="DFM",
                severity="HIGH",
                title="Deep draw with thin gauge (severe thinning risk)",
                why="Deep draw areas stretch significantly; thin starting gauge leads to excessive thinning, especially at corners and bases.",
                rec="Increase starting gauge; use plug assist for deep female cavities; consider multi-step forming; validate thickness distribution.",
            )
        else:
            _add(
                findings,
                id="THERMO2",
                category="DFM",
                severity="MEDIUM",
                title="Deep draw requires thickness management",
                why="Deep draw causes wall thinning; critical load areas need adequate thickness.",
                rec="Plan plug assist or pre-stretch; validate thickness in critical regions; consider thicker starting gauge.",
            )

    # THERMO3: Draft required
    if s.accessibility_risk in ("Medium", "High"):
        _add(
            findings,
            id="THERMO3",
            category="DFM",
            severity="MEDIUM",
            title="Insufficient draft increases release marks and damage risk",
            why="Insufficient draft makes part removal difficult, causing surface marking and potential damage.",
            rec="Increase mold draft angles; improve release geometry; consider surface finish requirements.",
        )

    # THERMO4: Radii/fillets
    if s.min_internal_radius == "Small":
        severity = "HIGH" if any(kw in user_text for kw in ("deep draw", "deep", "load", "stress")) else "MEDIUM"
        _add(
            findings,
            id="THERMO4",
            category="DFM",
            severity=severity,
            title="Sharp corners increase thinning and tearing risk",
            why="Sharp corners concentrate stress during forming and in service; increase thinning and tearing risk.",
            rec="Increase fillet radii (at least equal to wall thickness); use generous blends; avoid abrupt transitions.",
        )

    # THERMO5: Undercuts
    if s.accessibility_risk == "High" and any(kw in user_text for kw in ("undercut", "undercuts", "hook", "snap")):
        _add(
            findings,
            id="THERMO5",
            category="DFM",
            severity="HIGH",
            title="Undercuts require split tooling/slides or redesign",
            why="Undercuts complicate tooling; may require split tooling, slides, or alternative forming strategies.",
            rec="Eliminate undercuts where possible; consider split tooling or matched molds if undercuts are essential; evaluate alternative processes.",
        )

    # THERMO6: Vacuum venting
    if any(kw in user_text for kw in ("detail", "fine detail", "texture", "grain", "lettering")):
        _add(
            findings,
            id="THERMO6",
            category="DFM",
            severity="MEDIUM",
            title="Detail capture depends on vacuum distribution and venting",
            why="Detail reproduction requires adequate vacuum distribution; tradeoff between vent marks and insufficient venting.",
            rec="Plan vacuum hole pattern; balance hole size (too large = visible marks, too small = poor detail); consider porous tooling for complex venting.",
        )

    # THERMO7: Webbing risk
    if any(kw in user_text for kw in ("webbing", "bridging", "wrinkling", "multiple peaks", "multi-cavity")):
        _add(
            findings,
            id="THERMO7",
            category="DFM",
            severity="HIGH",
            title="Webbing/bridging risk from deep pockets or poor spacing",
            why="Webbing occurs when sheet bridges between high points; deep pockets and insufficient spacing increase risk.",
            rec="Increase spacing between molds/features; reduce draw ratio in local areas; optimize heating and vacuum rate; consider plug assist.",
        )
    elif s.pocket_aspect_class in ("Risky", "Extreme") and s.part_size in ("Medium", "Large"):
        _add(
            findings,
            id="THERMO7",
            category="DFM",
            severity="MEDIUM",
            title="Deep pockets increase webbing risk",
            why="Deep narrow cavities increase local draw ratio, increasing webbing and thinning risk.",
            rec="Reduce pocket depth-to-width ratio; increase spacing; plan plug assist or pre-stretch.",
        )

    # THERMO8: Plug assist recommendation
    if any(kw in user_text for kw in ("female", "cavity", "thin bottom", "thin corners", "base thickness")):
        _add(
            findings,
            id="THERMO8",
            category="DFM",
            severity="MEDIUM",
            title="Deep female cavities or thin bottoms/corners → plug assist recommended",
            why="Female molds tend to produce thin bottoms and corners in deep draws; plug assist improves thickness distribution.",
            rec="Use plug assist for deep female cavities; tune plug temperature and shape; minimize plug-to-mold gap for better distribution.",
        )

    # THERMO9: Surface detail side
    if any(kw in user_text for kw in ("cosmetic", "a-surface", "visible", "exposed", "outside", "inside")):
        _add(
            findings,
            id="THERMO9",
            category="DFM",
            severity="LOW",
            title="Pick male vs female/matched molds based on A-surface requirement",
            why="Detail reproduction is best on the mold-contact side; choose forming direction (male vs female) based on which side needs detail.",
            rec="Male (drape) forming favors inside detail; female (straight vacuum) favors outside detail; matched molds for two-side detail.",
        )

    # THERMO10: Tolerances
    if i.tolerance_criticality == "High":
        if any(kw in user_text for kw in ("tight tolerance", "precision", "close tolerance", "tolerance everywhere")):
            _add(
                findings,
                id="THERMO10",
                category="DFM",
                severity="HIGH",
                title="Tight tolerances everywhere conflict with thermoforming limitations",
                why="Thermoforming tolerances are weaker than injection molding due to thickness variation, shrinkage, and thermal gradients.",
                rec="Plan secondary ops (CNC trimming, drilling) for critical interfaces; use datums on mold-contact side; consider matched molds or alternative processes.",
            )
        else:
            _add(
                findings,
                id="THERMO10",
                category="DFM",
                severity="MEDIUM",
                title="Critical tolerances need secondary operations",
                why="Thermoforming tolerances are generally weaker; critical interfaces require secondary machining.",
                rec="Plan secondary operations for critical dimensions; add machining allowance; specify datum strategy.",
            )

    # THERMO11: Tooling choice
    if i.production_volume == "Proto":
        _add(
            findings,
            id="THERMO11",
            category="DFM",
            severity="LOW",
            title="Prototype tooling: wood/resin acceptable with caveats",
            why="Wood and resin tooling are cost-effective for prototypes but have limits (durability, heat conduction, temperature control).",
            rec="Use wood/resin tooling for prototypes; seal wood molds; plan for dimensional changes; upgrade to aluminum for production.",
        )
    elif i.production_volume == "Production":
        _add(
            findings,
            id="THERMO11",
            category="DFM",
            severity="LOW",
            title="Production tooling: aluminum recommended for thermal performance",
            why="Aluminum molds provide strong thermal conductivity and durability for high-volume production.",
            rec="Use aluminum tooling for production; plan for thermal management and cycle time optimization.",
        )

    # THERMO12: Trimming & fixturing
    if any(kw in user_text for kw in ("trim", "trimming", "cutout", "cut-out", "edge", "perimeter")):
        _add(
            findings,
            id="THERMO12",
            category="DFM",
            severity="MEDIUM",
            title="Plan trim flanges, CNC trim, datum features (hidden cost driver)",
            why="Thermoformed parts require trimming; trim scrap and fixturing can dominate cost if not planned.",
            rec="Design trim flanges; plan CNC trimming for accuracy; add locating/datum features; account for trim scrap in cost model.",
        )
    elif s.feature_variety == "High":
        _add(
            findings,
            id="THERMO12",
            category="DFM",
            severity="LOW",
            title="Complex perimeter increases trimming cost",
            why="Complex perimeters and many cutouts increase trimming complexity and cost.",
            rec="Plan trimming strategy; consider CNC trim for accuracy; design for trim access.",
        )

    # THERMO13: Material/heating uniformity
    if any(kw in user_text for kw in ("warp", "warpage", "distortion", "inconsistent", "variation")):
        _add(
            findings,
            id="THERMO13",
            category="DFM",
            severity="MEDIUM",
            title="Uneven heating causes warp/thickness variability",
            why="Non-uniform heating causes sag variation and thickness instability; warpage risk increases.",
            rec="Ensure uniform heating zones; control sheet quality and gauge uniformity; plan for thermal management.",
        )

    # THERMO14: Part consolidation
    if s.part_size in ("Medium", "Large") and s.feature_variety == "Low":
        _add(
            findings,
            id="THERMO14",
            category="DFM",
            severity="LOW",
            title="Large covers/panels benefit from thermoforming; ribs for stiffness",
            why="Large covers and panels are well-suited for thermoforming; use ribbing for stiffness rather than thicker sheet.",
            rec="Optimize for large sheet-formed parts; use ribbing to add stiffness; avoid unnecessarily thick gauge.",
        )

    # THERMO15: Two-sided detail requirement
    if any(kw in user_text for kw in ("two-sided", "both sides", "two side", "matched", "both faces")):
        _add(
            findings,
            id="THERMO15",
            category="DFM",
            severity="MEDIUM",
            title="Two-sided detail requirement: matched mold/pressure forming or alternatives",
            why="Standard thermoforming excels at one-side detail; two-sided detail requires matched molds or pressure forming (higher cost).",
            rec="Consider matched-mold forming or pressure forming for two-side detail; evaluate injection molding alternative; plan for increased tooling cost.",
        )

    # THERMO16: Recycling/scrap
    if i.production_volume in ("Small batch", "Production"):
        _add(
            findings,
            id="THERMO16",
            category="DFM",
            severity="LOW",
            title="Trim scrap can dominate cost; plan recycling strategy",
            why="Trim scrap can be substantial in thermoforming; recycling/regrind impacts economics.",
            rec="Plan trim scrap minimization; evaluate regrind strategy; account for waste in cost model.",
        )

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
