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


def run_sheet_rules(state: GraphState) -> dict:
    """Sheet-metal-specific design review and DFM rules (MVP)."""
    i = state["inputs"]
    s = state["part_summary"]
    findings: list[Finding] = []

    # Min bend radius (internal radius as proxy)
    if s.min_internal_radius == "Small":
        sev = "HIGH" if s.min_wall_thickness == "High" else "MEDIUM"
        _add(
            findings,
            id="SM1",
            category="DFM",
            severity=sev,
            title="Small bend radius (cracking risk)",
            why="Tight bends relative to thickness cause cracking; minimum radius typically ≥1× thickness.",
            rec="Increase bend radius; use relief notches; avoid bending across grain in critical areas.",
        )

    # Hole-to-bend / hole-to-edge (accessibility, feature variety as proxy)
    if s.feature_variety == "High" and s.min_internal_radius == "Small":
        _add(
            findings,
            id="SM2",
            category="DFM",
            severity="MEDIUM",
            title="Holes near bends (distance risk)",
            why="Holes too close to bend lines can deform; minimum distance ~1.5× thickness + radius.",
            rec="Keep holes ≥1.5t + R from bend lines; relocate or use secondary ops if needed.",
        )

    # Too many bends (baseline evidence when feature variety is high)
    if s.feature_variety == "High":
        _add(
            findings,
            id="SM2b",
            category="DFM",
            severity="MEDIUM",
            title="Too many bends (sequence & tolerance stack-up)",
            why="Many bends increase sequence dependency, springback stack-up, and tooling complexity.",
            rec="Reduce bend count where possible; plan bend order; allow ±0.5° on non-critical angles.",
        )

    if s.accessibility_risk == "High":
        _add(
            findings,
            id="SM3",
            category="DFM",
            severity="MEDIUM",
            title="Complex flanges (tool access)",
            why="Nested or hard-to-reach bends limit tool access and increase setups.",
            rec="Simplify bend sequence; ensure clearance for standard tooling; avoid locked-in features.",
        )

    # Bend relief
    if s.pocket_aspect_class in ("Risky", "Extreme"):
        _add(
            findings,
            id="SM4",
            category="DFM",
            severity="HIGH" if s.pocket_aspect_class == "Extreme" else "MEDIUM",
            title="Narrow slots / reliefs (tear risk)",
            why="Slots or cuts without relief at bends can tear; sharp corners concentrate stress.",
            rec="Add bend relief (notch or radius) at ends of cuts; avoid acute corners.",
        )

    # K-factor / tolerance note
    if i.tolerance_criticality == "High":
        _add(
            findings,
            id="SM5",
            category="DFM",
            severity="MEDIUM",
            title="Tight tolerances (K-factor & springback)",
            why="Sheet bend allowance varies with K-factor; springback affects angles.",
            rec="Define bend allowance early; allow ±0.5° on angles; compensate for springback in tooling.",
        )

    if s.part_size == "Large" and s.feature_variety == "High":
        _add(
            findings,
            id="SM6",
            category="DFM",
            severity="LOW",
            title="Large part with many features",
            why="Complex large parts need careful blank layout and bend sequence.",
            rec="Plan bend order and grain direction; minimize scrap; use uniform gauge where possible.",
        )

    # Clamping / datums
    if not s.has_clamping_faces:
        _add(
            findings,
            id="SM7",
            category="DESIGN_REVIEW",
            severity="HIGH",
            title="No clear datum or flat reference",
            why="Sheet parts need flat refs for measurement and assembly.",
            rec="Add flat datum faces or tabs; design for stable fixturing in welding/fastening.",
        )

    # Deep holes (piercing, extruded holes)
    if s.hole_depth_class == "Deep":
        _add(
            findings,
            id="SM8",
            category="DFM",
            severity="MEDIUM",
            title="Deep extruded holes / embossing",
            why="Deep drawn features need multiple stages; thinning and cracking risk.",
            rec="Limit draw depth; use multi-stage tooling; consider alternative fastening.",
        )

    # Keyword fallback: optional user text for extra evidence (no new LLM)
    user_text = ((state.get("description") or state.get("user_text")) or "").strip().lower()

    # SM9: Tight tolerances + coating/finish risk (coating allowance missing)
    if i.tolerance_criticality == "High" and user_text:
        coating_keywords = ("powder coat", "powdercoat", "paint", "plating", "anod", "coat", "finish")
        if any(kw in user_text for kw in coating_keywords):
            if not any(f.id == "SM9" for f in findings):
                _add(findings, id="SM9", category="DFM", severity="HIGH", title="Tight tolerances with coating/finish (allowance risk)",
                     why="Coatings add thickness and can violate tight tolerances; masking/sequence matters.", rec="Add coating allowance; mask critical interfaces; specify which surfaces are functional vs cosmetic.")

    # SM10: Tight tolerances + production (inspection effort)
    if i.tolerance_criticality == "High":
        if not any(f.id == "SM10" for f in findings):
            sev = "HIGH" if i.production_volume == "Production" else "MEDIUM"
            _add(findings, id="SM10", category="DFM", severity=sev, title="Tight tolerances in sheet metal (inspection & variability risk)",
                 why="Sheet metal forming variability and springback make blanket tight tolerances expensive.", rec="Apply tight tolerances only to functional interfaces; define datum scheme; avoid global tight tolerances.")

    # SM11: Sharp corners / tight bend proxy (always HIGH when Small radius)
    if s.min_internal_radius == "Small":
        if not any(f.id == "SM11" for f in findings):
            _add(findings, id="SM11", category="DFM", severity="HIGH", title="Sharp internal corners / tight bend radius risk",
                 why="Tight bends increase cracking/springback risk; sharp corners at bends are failure points.", rec="Increase internal radii; standardize bend radii; validate against material/thickness capability.")

    # SM12: Deburring / edge access risk
    if s.accessibility_risk in ("Medium", "High") and user_text:
        edge_keywords = ("edge", "deburr", "burr", "safe edge", "user-facing", "handle", "touch")
        if any(kw in user_text for kw in edge_keywords):
            if not any(f.id == "SM12" for f in findings):
                sev = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
                _add(findings, id="SM12", category="DFM", severity=sev, title="Edge condition / deburring access risk",
                     why="Burrs and sharp edges affect safety and assembly; inaccessible edges increase labor and risk.", rec="Ensure deburring access; specify edge break on user-facing edges; consider edge-friendly cut method.")

    # SM13: Flat pattern / unfold awareness
    flat_pattern_triggered = False
    if user_text:
        flat_pattern_keywords = ("flat pattern", "unfold", "bend allowance", "k-factor", "convert", "solid-to-sheet", "sheet metal conversion")
        if any(kw in user_text for kw in flat_pattern_keywords):
            flat_pattern_triggered = True
    if not flat_pattern_triggered and s.feature_variety == "High" and s.part_size == "Large":
        flat_pattern_triggered = True
    if flat_pattern_triggered and not any(f.id == "SM13" for f in findings):
        _add(findings, id="SM13", category="DFM", severity="HIGH", title="Flat pattern / bend allowance not validated",
             why="Incorrect bend allowance/unfold leads to dimensional mismatch and scrap.", rec="Validate flat pattern early; use consistent K-factor assumptions; confirm forming sequence.")

    # SM14: Manufacturing efficiency: too many bends/setups proxy
    if s.feature_variety == "High":
        if not any(f.id == "SM14" for f in findings):
            sev = "HIGH" if i.production_volume == "Production" else "MEDIUM"
            _add(findings, id="SM14", category="DFM", severity=sev, title="High process complexity (bends/setups/secondary ops) proxy",
                 why="Many distinct features often correlate with more bends/setups and secondary operations.", rec="Simplify geometry; standardize radii; reduce secondary ops; design for efficient forming sequence.")

    # SM15: Large thin sheet stiffness / warping
    if s.part_size == "Large" and s.min_wall_thickness == "Thin":
        if not any(f.id == "SM15" for f in findings):
            _add(findings, id="SM15", category="DFM", severity="HIGH", title="Large thin sheet risk (warping / low rigidity)",
                 why="Large flat thin sheets are prone to warping/vibration; stiffness often needs flanges/beads.", rec="Add flanges/returns/beads; break up large flats; add ribs/gussets; consider thickness increase.")

    # SM16: Hardware integration access (optional)
    if user_text and s.accessibility_risk in ("Medium", "High"):
        hardware_keywords = ("pem", "stud", "nut", "clinch", "insert", "hardware")
        if any(kw in user_text for kw in hardware_keywords):
            if not any(f.id == "SM16" for f in findings):
                sev = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
                _add(findings, id="SM16", category="DFM", severity=sev, title="Hardware integration without access validation",
                     why="Hardware installation needs tool access and edge distances; bends can interfere.", rec="Validate access and bend clearance; keep hardware away from bends; plan install sequence.")
    if user_text:
        if "bend" in user_text and not any(f.id == "SM_K1" for f in findings):
            _add(findings, id="SM_K1", category="DFM", severity="MEDIUM", title="Bends called out (design intent)",
                 why="Bent features need radius and relief; verify minimum bend radius ≥1× thickness.", rec="Specify bend radius and relief; avoid bending across grain in critical areas.")
        if ("flange" in user_text or "flanges" in user_text) and not any(f.id == "SM_K2" for f in findings):
            _add(findings, id="SM_K2", category="DFM", severity="MEDIUM", title="Flanges (tool access & sequence)",
                 why="Flanges affect bend order and tool clearance; nested flanges can limit access.", rec="Define bend sequence; ensure clearance for standard tooling.")
        if ("sharp corner" in user_text or "sharp corners" in user_text) and not any(f.id == "SM_K3" for f in findings):
            _add(findings, id="SM_K3", category="DFM", severity="MEDIUM", title="Sharp corners (tear & stress)",
                 why="Sharp corners concentrate stress and can tear at bends.", rec="Add bend relief or radius at corners; avoid acute angles.")
        if "bend relief" in user_text and not any(f.id == "SM_K4" for f in findings):
            _add(findings, id="SM_K4", category="DFM", severity="MEDIUM", title="Bend relief (design check)",
                 why="Relief at bend ends reduces tear risk; verify width and placement.", rec="Confirm relief width ≥1.5× thickness; avoid sharp relief corners.")
        if any(x in user_text for x in ("powder coat", "coating", "plating")) and not any(f.id == "SM_K5" for f in findings):
            _add(findings, id="SM_K5", category="DFM", severity="MEDIUM", title="Coating / plating (masking & tolerance)",
                 why="Coatings add thickness and may need masking; affect fit and appearance.", rec="Call out coated vs uncoated zones; allow for coating thickness on fits.")
        if any(x in user_text for x in ("pem", "stud", "insert")) and not any(f.id == "SM_K6" for f in findings):
            _add(findings, id="SM_K6", category="DFM", severity="MEDIUM", title="PEM / stud / insert (pierce & install)",
                 why="PEMs and inserts need hole size and edge distance; install after forming can affect sequence.", rec="Verify hole size per supplier; keep PEMs away from bend lines.")
        if ("weld" in user_text or "rivet" in user_text) and not any(f.id == "SM_K7" for f in findings):
            _add(findings, id="SM_K7", category="DFM", severity="MEDIUM", title="Weld or rivet (secondary ops)",
                 why="Welding and riveting add ops and can distort sheet; need flat reference.", rec="Design for weld access and sequence; add datum for assembly.")
        if "tight tolerance" in user_text and not any(f.id == "SM_K8" for f in findings):
            _add(findings, id="SM_K8", category="DFM", severity="MEDIUM", title="Tight tolerance (K-factor & springback)",
                 why="Sheet bend allowance and springback affect final dimensions.", rec="Define bend allowance; allow ±0.5° on angles; compensate in tooling.")

    trace_delta = [f"Rule triggered: {f.title} → {f.severity} severity" for f in findings]
    return {"findings": findings, "trace": trace_delta}
