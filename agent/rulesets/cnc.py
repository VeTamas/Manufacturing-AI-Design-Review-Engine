"""CNC ruleset. Phase 3: deterministic proposals for numeric findings (DFM-NH1/NH2/NP1/NP2)."""
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
    evidence: dict | None = None,
    proposal: str | None = None,
    proposal_steps: list[str] | None = None,
) -> None:
    findings.append(
        Finding(
            id=id,
            category=category,
            severity=severity,
            title=title,
            why_it_matters=why,
            recommendation=rec,
            evidence=evidence,
            proposal=proposal,
            proposal_steps=proposal_steps,
        )
    )


def run_cnc_rules(state: GraphState) -> dict:
    """CNC-specific design review and DFM rules. Existing logic unchanged."""
    i = state["inputs"]
    s = state["part_summary"]
    findings: list[Finding] = []

    # DESIGN REVIEW (DR1–DR5)
    if i.load_type in ("Dynamic", "Shock") and s.min_wall_thickness == "Thin":
        _add(
            findings,
            id="DR1",
            category="DESIGN_REVIEW",
            severity="HIGH",
            title="Dynamic load + thin sections",
            why="Thin sections under dynamic or shock loads increase fatigue risk and vibration sensitivity.",
            rec="Increase wall thickness, add ribs/gussets, and smooth transitions with fillets.",
        )

    if s.min_internal_radius == "Small":
        sev = "HIGH" if i.load_type in ("Dynamic", "Shock") else "MEDIUM"
        _add(
            findings,
            id="DR2",
            category="DESIGN_REVIEW",
            severity=sev,
            title="Likely stress concentration at internal corners",
            why="Sharp internal corners concentrate stress and can initiate cracks, especially under cyclic loads.",
            rec="Increase internal radii; use relief features; avoid abrupt section changes.",
        )

    if not s.has_clamping_faces:
        _add(
            findings,
            id="DR3",
            category="DESIGN_REVIEW",
            severity="HIGH",
            title="Fixturing risk: no clear clamping/datum faces",
            why="Unclear datums and clamping faces often require complex fixtures and increase setup variation.",
            rec="Add flat datum faces, parallel reference surfaces, or sacrificial tabs for stable fixturing.",
        )

    if i.tolerance_criticality == "High" and i.production_volume in ("Proto", "Small batch"):
        _add(
            findings,
            id="DR4",
            category="DESIGN_REVIEW",
            severity="MEDIUM",
            title="Potential over-tolerancing for low volume",
            why="Tight tolerances increase cycle time, inspection effort, and scrap risk—often unnecessary outside interfaces.",
            rec="Apply tight tolerances only to functional interfaces; relax non-critical features.",
        )

    if i.material == "Plastic" and i.load_type in ("Dynamic", "Shock"):
        _add(
            findings,
            id="DR5",
            category="DESIGN_REVIEW",
            severity="HIGH",
            title="Material-load mismatch risk (plastic under dynamic/shock)",
            why="Many plastics creep and fatigue faster under cyclic or impact loading unless reinforced and properly designed.",
            rec="Consider metal or reinforced polymer; increase section thickness and add ribs where needed.",
        )

    # CNC DFM (DFM1–DFM7)
    if s.min_internal_radius == "Small":
        sev = "HIGH" if (s.part_size == "Large" or s.feature_variety == "High") else "MEDIUM"
        _add(
            findings,
            id="DFM1",
            category="DFM",
            severity=sev,
            title="Small internal corner radius (tooling/cycle-time risk)",
            why="Small radii usually require smaller cutters, leading to longer cycle time and higher tooling risk.",
            rec="Standardize to larger internal radii where possible; consider corner relief (e.g., dogbone) when appropriate.",
        )

    if s.pocket_aspect_class in ("Risky", "Extreme"):
        sev = "HIGH" if s.pocket_aspect_class == "Extreme" else "MEDIUM"
        _add(
            findings,
            id="DFM2",
            category="DFM",
            severity=sev,
            title="Deep/narrow pockets (chatter risk)",
            why="High depth-to-width pockets increase tool deflection and chatter, degrading finish and dimensional accuracy.",
            rec="Widen pockets, reduce depth, split into steps, or redesign for better tool access.",
        )

    if s.hole_depth_class == "Deep":
        sev = "HIGH" if s.feature_variety == "High" else "MEDIUM"
        _add(
            findings,
            id="DFM3",
            category="DFM",
            severity=sev,
            title="Deep holes (drilling risk)",
            why="Deep drilling increases chip evacuation and straightness issues; cycle time and breakage risk rise.",
            rec="Reduce depth if possible; use peck drilling; ream only where needed; consider alternative design.",
        )

    if s.min_wall_thickness == "Thin":
        sev = "HIGH" if (i.load_type in ("Dynamic", "Shock") or s.part_size != "Small") else "MEDIUM"
        _add(
            findings,
            id="DFM4",
            category="DFM",
            severity=sev,
            title="Thin walls (deflection during machining)",
            why="Thin walls can deflect during machining, causing poor surface finish and tolerance drift.",
            rec="Thicken walls, add ribs, or plan roughing/finishing strategy; avoid long unsupported spans.",
        )

    if s.accessibility_risk in ("Medium", "High"):
        sev = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
        _add(
            findings,
            id="DFM5",
            category="DFM",
            severity=sev,
            title="Potential accessibility/undercut issue",
            why="Features not accessible to standard tools may require special cutters, 5-axis, or multiple setups.",
            rec="Redesign for tool access; avoid undercuts; consider splitting part or changing manufacturing approach.",
        )

    if s.feature_variety == "High":
        _add(
            findings,
            id="DFM6",
            category="DFM",
            severity="MEDIUM",
            title="High feature variety (tooling & inspection overhead)",
            why="Many unique diameters/radii/depths increase tool changes, programming time, and inspection effort.",
            rec="Standardize hole sizes, radii, and depths to preferred values; reduce variety where possible.",
        )

    if s.part_size == "Large" and not s.has_clamping_faces:
        _add(
            findings,
            id="DFM7",
            category="DFM",
            severity="HIGH",
            title="Likely multi-setup complexity",
            why="Large parts without clear datums often require multiple setups and complex workholding, increasing variation.",
            rec="Add datum scheme and flat reference surfaces; redesign to reduce setups or simplify fixturing.",
        )

    # DFM8: Tight tolerance + low volume => HIGH
    if i.tolerance_criticality == "High" and i.production_volume in ("Proto", "Small batch"):
        _add(
            findings,
            id="DFM8",
            category="DFM",
            severity="HIGH",
            title="Tight tolerances for low volume (cost/lead-time risk)",
            why="Tight tolerances increase cycle time, inspection burden, and scrap risk; for low volumes this is often unnecessary.",
            rec="Identify truly critical interfaces; relax non-critical dimensions; specify tighter tolerances only where function requires.",
        )

    # DFM9: Tight tolerance + no 2D drawing => HIGH
    conf_inputs = state.get("confidence_inputs")
    if i.tolerance_criticality == "High" and conf_inputs is not None:
        has_2d = conf_inputs.get("has_2d_drawing", False) if isinstance(conf_inputs, dict) else bool(getattr(conf_inputs, "has_2d_drawing", False))
        if not has_2d:
            _add(
                findings,
                id="DFM9",
                category="DFM",
                severity="HIGH",
                title="Tight tolerance requirements without 2D drawing (ambiguity risk)",
                why="Without a drawing, GD&T, datum scheme, and critical dimensions are unclear; inspection and acceptance criteria become ambiguous.",
                rec="Provide 2D drawing with datums, critical dimensions, and tolerance scheme; avoid blanket tight tolerances.",
            )

    # DFM10: Steel + tight tolerance => MEDIUM (or HIGH if also low volume)
    if i.material == "Steel" and i.tolerance_criticality == "High":
        sev = "HIGH" if i.production_volume in ("Proto", "Small batch") else "MEDIUM"
        _add(
            findings,
            id="DFM10",
            category="DFM",
            severity=sev,
            title="Steel + tight tolerances (machinability & inspection risk)",
            why="Harder-to-machine materials increase tool wear and make tight tolerances harder and costlier to hold reliably.",
            rec="Consider relaxing tolerances where possible; choose free-machining grades if allowed; plan inspection strategy.",
        )

    # Turning rules (TURN1, TURN2, TURN3)
    if getattr(i, "process", None) == "CNC_TURNING":
        cad_metrics = state.get("cad_metrics") or {}
        ld = cad_metrics.get("turning_ld_ratio")

        # Determine support flag, scale confirmation, and 2D drawing status
        conf_inputs = state.get("confidence_inputs")
        support = False
        scale_ok = True  # Default to True if not provided
        has_2d = False  # Default to False if not provided
        if conf_inputs is not None:
            if isinstance(conf_inputs, dict):
                support = bool(conf_inputs.get("turning_support_confirmed", False))
                scale_ok = bool(conf_inputs.get("step_scale_confirmed", True))
                has_2d = bool(conf_inputs.get("has_2d_drawing", False))
            else:
                support = bool(getattr(conf_inputs, "turning_support_confirmed", False))
                scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))
                has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))

        # TURN3: Tight tolerance + no 2D drawing => HIGH
        if i.tolerance_criticality == "High" and not has_2d:
            _add(
                findings,
                id="TURN3",
                category="DFM",
                severity="HIGH",
                title="Turning: tight tolerances without 2D drawing (datum/runout ambiguity)",
                why="On turned parts, acceptance often depends on datum scheme, coaxiality/runout, and where/how dimensions are inspected. Without a 2D drawing, critical dimensions and GD&T requirements can be ambiguous, increasing inspection risk and rework.",
                rec="Provide a 2D drawing specifying datums, critical dimensions, and any runout/concentricity requirements; avoid blanket tight tolerances unless functionally justified.",
            )

        if ld is None:
            rec_msg = "Upload a STEP model or provide key dimensions; confirm whether tailstock/steady rest will be used for slender parts."
            if not scale_ok:
                rec_msg += " Confirm STEP real-world scale and provide key dimensions."
            _add(
                findings,
                id="TURN1",
                category="DFM",
                severity="MEDIUM",
                title="Turning: L/D ratio unknown (upload STEP for slenderness check)",
                why="Slenderness strongly affects deflection and chatter risk in turning; without geometry metrics this cannot be assessed reliably.",
                rec=rec_msg,
            )
        else:
            # Base severity by L/D
            if ld >= 10:
                sev = "HIGH"
            elif ld >= 6:
                sev = "MEDIUM"
            else:
                sev = "LOW"

            # Escalate if slender and support not confirmed
            if ld >= 6 and not support:
                sev = "HIGH" if ld >= 10 else "MEDIUM"

            # Scale-aware cap: if scale not confirmed, cap severity to MEDIUM
            if not scale_ok and sev == "HIGH":
                sev = "MEDIUM"

            if sev != "LOW":
                rec_msg = "Confirm tailstock/steady rest support for slender parts; reduce unsupported length, add support features, or change process if needed."
                if not scale_ok:
                    rec_msg += " Note: STEP model scale is not confirmed; L/D-based risk is indicative."
                _add(
                    findings,
                    id="TURN2",
                    category="DFM",
                    severity=sev,
                    title=f"Turning slenderness risk (L/D≈{ld})",
                    why="High L/D increases deflection and chatter, hurting finish, tolerance, and tool life. Workholding/support is often required.",
                    rec=rec_msg,
                )

    # DFM11: Tight tolerance + high feature variety => HIGH
    if i.tolerance_criticality == "High" and s.feature_variety == "High":
        _add(
            findings,
            id="DFM11",
            category="DFM",
            severity="HIGH",
            title="Tight tolerances across many features (inspection & cost explosion)",
            why="Tight tolerances combined with many unique features increase inspection plan complexity, measurement time, and scrap risk.",
            rec="Limit tight tolerances to functional interfaces; standardize features; define datum scheme in drawing.",
        )

    # DFM12: Tight tolerance + difficult accessibility => HIGH (or MEDIUM if only Medium)
    if i.tolerance_criticality == "High" and s.accessibility_risk in ("Medium", "High"):
        sev = "HIGH" if s.accessibility_risk == "High" else "MEDIUM"
        _add(
            findings,
            id="DFM12",
            category="DFM",
            severity=sev,
            title="Tight tolerances on hard-to-access features (setup & accuracy risk)",
            why="Multi-setup / special tooling features are harder to control tightly; stack-up and deflection increase.",
            rec="Improve access, reduce setups, add datum features; relax tolerances where possible.",
        )

    # DFM13: Deep holes + high tolerance criticality => HIGH
    if s.hole_depth_class == "Deep" and i.tolerance_criticality == "High":
        _add(
            findings,
            id="DFM13",
            category="DFM",
            severity="HIGH",
            title="Deep holes with tight tolerances (straightness/finish risk)",
            why="Deep drilling/boring makes straightness, diameter, and finish harder to hold; chip evacuation and tool wander increase.",
            rec="Reduce depth, increase diameter if possible; specify which hole attributes are critical; consider reaming/honing only where needed.",
        )

    # DFM14: Deep pockets + high tolerance criticality => HIGH for Extreme, MEDIUM for Risky
    if s.pocket_aspect_class in ("Risky", "Extreme") and i.tolerance_criticality == "High":
        sev = "HIGH" if s.pocket_aspect_class == "Extreme" else "MEDIUM"
        _add(
            findings,
            id="DFM14",
            category="DFM",
            severity=sev,
            title="Deep pockets with tight tolerances (chatter & finish risk)",
            why="Pocket depth/width extremes increase tool deflection; tight tolerances amplify the risk of out-of-spec walls and poor finish.",
            rec="Reduce depth, add steps, widen pockets, increase corner radii; relax tolerances on non-critical pocket walls.",
        )

    # DFM15: Thin walls + high tolerance criticality => HIGH (unless small part and static)
    if s.min_wall_thickness == "Thin" and i.tolerance_criticality == "High":
        sev = "HIGH" if (s.part_size != "Small" or i.load_type in ("Dynamic", "Shock")) else "MEDIUM"
        _add(
            findings,
            id="DFM15",
            category="DFM",
            severity=sev,
            title="Thin walls with tight tolerances (warping/deflection risk)",
            why="Thin sections move during machining and clamping, making tight tolerance control difficult and increasing scrap risk.",
            rec="Increase thickness, add ribs, change datum strategy; specify which dimensions truly need tight tolerance.",
        )

    # CNC-only numeric-backed rules (trigger only when CNC/CNC_TURNING and part_metrics_evidence present)
    evidence = state.get("part_metrics_evidence") or {}
    process = getattr(i, "process", None)
    if evidence and isinstance(evidence, dict) and process in ("CNC", "CNC_TURNING"):
        # DFM-N1: Thin wall detected (numeric)
        thin_flag = evidence.get("thin_wall_flag") is True
        min_wall_mm = evidence.get("min_wall_thickness_mm")
        if thin_flag or (min_wall_mm is not None and float(min_wall_mm) <= 1.0):
            sev = "HIGH" if thin_flag else "MEDIUM"
            ev_dict = {k: evidence[k] for k in ("min_wall_thickness_mm", "thin_wall_flag") if k in evidence and evidence[k] is not None}
            _add(
                findings,
                id="DFM-N1",
                category="DFM",
                severity=sev,
                title="Thin wall detected (numeric)",
                why="Numeric geometry indicates thin walls; deflection and chatter risk during machining.",
                rec="Increase wall thickness / add ribs / local thickening; avoid long slender walls.",
                evidence=ev_dict if ev_dict else None,
            )
        # DFM-N2: Small internal radius likely increases tooling/time (numeric)
        min_rad_mm = evidence.get("min_internal_radius_mm")
        if min_rad_mm is not None and float(min_rad_mm) <= 0.5:
            ev_dict = {"min_internal_radius_mm": min_rad_mm}
            _add(
                findings,
                id="DFM-N2",
                category="DFM",
                severity="MEDIUM",
                title="Small internal radius likely increases tooling/time (numeric)",
                why="Small internal radii require smaller cutters and increase cycle time.",
                rec="Increase internal fillet radius where possible; match common tool radii.",
                evidence=ev_dict,
            )

        # DFM-NH1: hole_max_ld >= 6.0 (heuristic v2; tune later)
        hole_max_ld = evidence.get("hole_max_ld")
        if hole_max_ld is not None:
            ld_val = float(hole_max_ld)
            if ld_val >= 6.0:
                ev_keys = ["hole_max_ld", "hole_max_depth_mm", "hole_diameters_mm"]
                ev_dict = {k: evidence[k] for k in ev_keys if k in evidence}
                ld_str = str(hole_max_ld) if isinstance(hole_max_ld, (int, float)) else str(ld_val)
                _add(
                    findings,
                    id="DFM-NH1",
                    category="DFM",
                    severity="MEDIUM",
                    title="Deep hole L/D ratio (drilling/reaming risk)",
                    why="High hole depth-to-diameter ratio increases deflection, chip evacuation, and straightness issues.",
                    rec="Consider peck drilling; reduce depth; ream only where needed.",
                    evidence=ev_dict if ev_dict else {"hole_max_ld": hole_max_ld},
                    proposal=f"Reduce maximum hole L/D from {ld_str} to <= 6 by reducing depth, increasing diameter, converting to a through-hole, or adding relief for drill access.",
                    proposal_steps=[
                        "Identify the deepest hole(s) driving max L/D and confirm functional depth requirement.",
                        "If depth is non-functional, reduce hole depth or convert to through-hole.",
                        "If diameter can increase, step up to the next preferred drill size to reduce L/D.",
                        "If neither changes, plan a pilot + finish operation or add a relief pocket/counterbore to shorten effective depth.",
                        "Validate drill reach and deflection risk in CAM with the intended tool stick-out.",
                    ],
                )

        # DFM-NH2: many unique hole diameters (heuristic v2; tune later)
        hole_diams = evidence.get("hole_diameters_mm")
        if isinstance(hole_diams, list) and len(hole_diams) >= 6:
            ev_dict = {"hole_diameters_mm": hole_diams, "hole_count": evidence.get("hole_count")}
            diams_str = ", ".join(str(round(d, 2) if isinstance(d, (int, float)) else d) for d in hole_diams[:12])
            if len(hole_diams) > 12:
                diams_str += ", ..."
            _add(
                findings,
                id="DFM-NH2",
                category="DFM",
                severity="LOW",
                title="Many hole diameters (tooling variety overhead)",
                why="Multiple hole sizes increase tool changes and setup complexity.",
                rec="Standardize hole diameters where possible.",
                evidence=ev_dict,
                proposal=f"Standardize hole diameters (observed unique diameters: {diams_str}) to a smaller preferred set to reduce tool changes and inspection overhead.",
                proposal_steps=[
                    "Consolidate to top 2-3 preferred drill sizes where functionally acceptable.",
                    "Rework outliers with ream/counterbore if consolidation not possible.",
                    "Update drawing notes to specify preferred hole sizes.",
                ],
            )

        # DFM-NP1: pocket_max_aspect >= 4.0 (heuristic v2; tune later)
        pocket_aspect = evidence.get("pocket_max_aspect")
        if pocket_aspect is not None:
            asp_val = float(pocket_aspect)
            if asp_val >= 4.0:
                ev_keys = ["pocket_max_aspect", "pocket_max_depth_mm", "pocket_count"]
                ev_dict = {k: evidence[k] for k in ev_keys if k in evidence}
                asp_str = str(pocket_aspect) if isinstance(pocket_aspect, (int, float)) else str(asp_val)
                _add(
                    findings,
                    id="DFM-NP1",
                    category="DFM",
                    severity="MEDIUM",
                    title="Deep pocket aspect ratio (deflection/chatter risk)",
                    why="High depth-to-width pockets increase tool deflection and chatter.",
                    rec="Widen pockets, reduce depth, or split into steps.",
                    evidence=ev_dict if ev_dict else {"pocket_max_aspect": pocket_aspect},
                    proposal=f"Reduce pocket aspect ratio (observed max: {asp_str}) by decreasing depth, increasing opening/span, adding radii, or splitting into multiple setups/features.",
                    proposal_steps=[
                        "Identify the deepest pocket driving max aspect ratio.",
                        "Reduce depth or widen opening where functionally acceptable.",
                        "Add corner radii to improve tool access and reduce deflection.",
                        "Consider stepped pocket design to reduce effective aspect.",
                        "Validate chatter and deflection in CAM.",
                    ],
                )

        # DFM-NP2: many pockets (heuristic v2; tune later)
        pocket_count = evidence.get("pocket_count")
        if isinstance(pocket_count, int) and pocket_count >= 4:
            ev_dict = {"pocket_count": pocket_count}
            _add(
                findings,
                id="DFM-NP2",
                category="DFM",
                severity="LOW",
                title="Many pockets (cycle time/setup overhead)",
                why="Multiple pockets increase machining time and tool paths.",
                rec="Consolidate pockets where possible; consider process alternatives.",
                evidence=ev_dict,
                proposal=f"Reduce pocket count (observed: {pocket_count}) by merging pockets, standardizing depths, and minimizing unique floor levels.",
                proposal_steps=[
                    "Merge adjacent pockets where functionally acceptable.",
                    "Standardize pocket depths to reduce unique floor levels.",
                    "Remove cosmetic pockets that do not serve a functional purpose.",
                    "Validate function and accessibility after consolidation.",
                ],
            )

    trace_delta = [f"Rule triggered: {f.title} → HIGH severity" for f in findings if f.severity == "HIGH"]
    return {"findings": findings, "trace": trace_delta}
