from __future__ import annotations

from agent.geometry.cad_presence import cad_analysis_status, cad_evidence_available, cad_evidence_keys, cad_uploaded
from agent.nodes.process_selection import CANDIDATES
from agent.rulesets import run_am_rules, run_am_fdm_rules, run_am_metal_lpbf_rules, run_am_thermoplastic_high_temp_rules, run_am_sla_rules, run_am_sls_rules, run_am_mjf_rules, run_casting_rules, run_cnc_rules, run_compression_molding_rules, run_extrusion_rules, run_fdm_rules, run_forging_rules, run_injection_molding_rules, run_mim_rules, run_sheet_rules, run_thermoforming_rules
from agent.nodes.process_selection import _resolve_am_tech
from agent.process_registry import pretty_process_name
from agent.state import Finding, GraphState


def _add_pass_findings(state: GraphState, findings: list[Finding]) -> list[Finding]:
    """When no findings, add 1–2 LOW PASS findings from PartSummary bins only (no invented geometry)."""
    if findings:
        return findings
    part = state.get("part_summary")
    if not part:
        return findings
    added: list[Finding] = []
    if part.feature_variety == "Low":
        added.append(
            Finding(
                id="PASS1",
                category="DFM",
                severity="LOW",
                title="Low feature variety (favorable for cycle time and tooling)",
                why_it_matters="Low complexity reduces cycle time and tooling risk.",
                recommendation="No change needed.",
            )
        )
    if part.accessibility_risk == "Low":
        added.append(
            Finding(
                id="PASS2",
                category="DFM",
                severity="LOW",
                title="Low accessibility risk (good tool access)",
                why_it_matters="Good tool access reduces setup and machining risk.",
                recommendation="No change needed.",
            )
        )
    if not added and (part.min_wall_thickness in ("Medium", "High") or part.min_internal_radius in ("Medium", "High")):
        added.append(
            Finding(
                id="PASS1",
                category="DFM",
                severity="LOW",
                title="Reasonable geometry bins (wall/radius)",
                why_it_matters="Part summary indicates adequate wall and radius bins.",
                recommendation="No change needed.",
            )
        )
    if not added:
        added.append(
            Finding(
                id="PASS1",
                category="DFM",
                severity="LOW",
                title="Part summary reviewed; no issues flagged",
                why_it_matters="Inputs reviewed; no high- or medium-risk items triggered.",
                recommendation="No change needed.",
            )
        )
    return added[:2]


def _findings_from_score_breakdown(state: GraphState) -> list[Finding]:
    """Derive findings from process_selection score_breakdown (score-first, findings-from-score)."""
    proc_rec = state.get("process_recommendation") or {}
    score_breakdown = proc_rec.get("score_breakdown") or {}
    if not isinstance(score_breakdown, dict):
        return []
    findings: list[Finding] = []
    seen_ids: set[str] = set()
    for proc, entries in score_breakdown.items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            sev = (e.get("severity") or "").lower()
            if sev not in ("high", "med", "medium"):
                continue
            rule_id = e.get("rule_id")
            if not rule_id or rule_id in seen_ids:
                continue
            title = e.get("title") or e.get("reason", "")
            why = e.get("why_it_matters", "")
            rec = e.get("recommendation", "")
            if not title or not why or not rec:
                continue
            seen_ids.add(rule_id)
            severity = "HIGH" if sev == "high" else "MEDIUM"
            findings.append(
                Finding(
                    id=rule_id,
                    category="DFM",
                    severity=severity,
                    title=title,
                    why_it_matters=why,
                    recommendation=rec,
                )
            )
    return findings


def rules_node(state: GraphState) -> dict:
    inp = state.get("inputs")
    process = getattr(inp, "process", None) if inp else None
    # If AUTO, use recommended primary from process_selection
    if process == "AUTO":
        proc_rec = state.get("process_recommendation") or {}
        process = proc_rec.get("primary") or "CNC"
    process = process or "CNC"
    if process == "CNC":
        out = run_cnc_rules(state)
    elif process == "AM":
        inp = state.get("inputs")
        user_am_tech = getattr(inp, "am_tech", None) if inp else None
        am_tech, am_tech_source = _resolve_am_tech(state, user_am_tech)
        
        # Route to tech-specific ruleset
        if am_tech == "FDM":
            out = run_am_fdm_rules(state)
            t = out.get("trace", [])
            t.append("ruleset_used=am_fdm")
            out["trace"] = t
        elif am_tech == "METAL_LPBF":
            out = run_am_metal_lpbf_rules(state)
            t = out.get("trace", [])
            t.append("ruleset_used=am_metal_lpbf")
            out["trace"] = t
        elif am_tech == "THERMOPLASTIC_HIGH_TEMP":
            out = run_am_thermoplastic_high_temp_rules(state)
            t = out.get("trace", [])
            t.append("ruleset_used=am_thermoplastic_high_temp")
            out["trace"] = t
        elif am_tech == "SLA":
            out = run_am_sla_rules(state)
            t = out.get("trace", [])
            t.append("ruleset_used=am_sla")
            out["trace"] = t
        elif am_tech == "SLS":
            out = run_am_sls_rules(state)
            t = out.get("trace", [])
            t.append("ruleset_used=am_sls")
            out["trace"] = t
        elif am_tech == "MJF":
            out = run_am_mjf_rules(state)
            t = out.get("trace", [])
            t.append("ruleset_used=am_mjf")
            out["trace"] = t
        else:
            # Fallback to generic AM rules
            out = run_am_rules(state)
            t = out.get("trace", [])
            t.append("ruleset_used=am_generic")
            out["trace"] = t

        # PATCH 2: Generic AM fallback if tech ruleset yields few findings (dedup by code/id/title+severity)
        def _finding_key(f):
            if isinstance(f, dict):
                return f.get("code") or f.get("id") or (f.get("title"), f.get("severity"))
            return getattr(f, "code", None) or getattr(f, "id", None) or (getattr(f, "title", None), getattr(f, "severity", None))

        MIN_FINDINGS_FOR_TECH = 3
        tech_list = ("FDM", "METAL_LPBF", "THERMOPLASTIC_HIGH_TEMP", "SLA", "SLS", "MJF")
        if am_tech in tech_list and len(out.get("findings", [])) < MIN_FINDINGS_FOR_TECH:
            generic = run_am_rules(state)
            existing = set()
            for f in out.get("findings", []):
                k = _finding_key(f)
                if k is not None:
                    existing.add(k)
            for g in generic.get("findings", []):
                k = _finding_key(g)
                if k is None or k in existing:
                    continue
                out["findings"].append(g)
                existing.add(k)
            t = out.get("trace", [])
            t.append("am_fallback_generic=True")
            out["trace"] = t
        else:
            t = out.get("trace", [])
            t.append("am_fallback_generic=False")
            out["trace"] = t

        out["_am_tech_source"] = am_tech_source
    elif process == "FDM":
        out = run_fdm_rules(state)
    elif process == "SHEET_METAL":
        out = run_sheet_rules(state)
    elif process == "INJECTION_MOLDING":
        out = run_injection_molding_rules(state)
    elif process == "CASTING":
        out = run_casting_rules(state)
    elif process == "FORGING":
        out = run_forging_rules(state)
    elif process == "EXTRUSION":
        out = run_extrusion_rules(state)
        t = out.get("trace", [])
        t.append("ruleset_used=extrusion")
        out["trace"] = t
    elif process == "MIM":
        out = run_mim_rules(state)
        t = out.get("trace", [])
        t.append("ruleset_used=mim")
        out["trace"] = t
    elif process == "THERMOFORMING":
        out = run_thermoforming_rules(state)
        t = out.get("trace", [])
        t.append("ruleset_used=thermoforming")
        out["trace"] = t
    elif process == "COMPRESSION_MOLDING":
        out = run_compression_molding_rules(state)
        t = out.get("trace", [])
        t.append("ruleset_used=compression_molding")
        out["trace"] = t
    else:
        out = run_cnc_rules(state)
    # Gate PASS findings: only add for CNC-like processes
    if process in ("CNC", "CNC_TURNING"):
        findings = _add_pass_findings(state, out.get("findings", []))
    else:
        findings = list(out.get("findings", []))

    # Derive findings from score_breakdown (IM1, MIM1, CAST1, FORG1)
    breakdown_findings = _findings_from_score_breakdown(state)
    existing_ids = {f.id for f in findings}
    for bf in breakdown_findings:
        if bf.id not in existing_ids:
            findings.append(bf)
            existing_ids.add(bf.id)

    # Add PSI1/PSI_HARD meta-findings: bins-mode anchor suppresses PSI1 when selected is eligible
    proc_rec = state.get("process_recommendation") or {}
    primary = proc_rec.get("primary")
    user_proc_raw = getattr(inp, "process", None) if inp else None
    # Treat AUTO as no user selection (geometry-driven)
    user_proc = None if user_proc_raw == "AUTO" else user_proc_raw
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()
    cad_status = cad_analysis_status(state)
    process_gates = proc_rec.get("process_gates") or {}
    eligible_processes = proc_rec.get("eligible_processes") or list(CANDIDATES)
    selected_eligible = user_proc in eligible_processes if user_proc else False

    # PSI_HARD: selected process is hard-gated (not applicable)
    if user_proc and not selected_eligible:
        gate_info = process_gates.get(user_proc, {})
        reason = gate_info.get("reason", "not applicable for material family")
        finding_hard = Finding(
            id="PSI_HARD",
            category="PROCESS_SELECTION",
            severity="HIGH",
            title="Selected process is not applicable",
            why_it_matters=f"Selected {user_proc} is not applicable given material family: {reason}.",
            recommendation=f"Choose an applicable process. Recommended: {primary}.",
        )
        findings.append(finding_hard)
        result_trace = out.get("trace", [])
        result_trace.append(f"PSI_HARD: selected={user_proc} ineligible reason={reason}")
        out["trace"] = result_trace

    if primary and user_proc and primary != user_proc and selected_eligible:
        scores = proc_rec.get("scores", {})
        score_diff = scores.get(primary, 0) - scores.get(user_proc, 0) if isinstance(scores, dict) else 0
        
        # Check for AM-only geometry signals (for PSI1 reason text)
        AM_GEOM_KW = {
            "internal channel", "internal channels", "conformal cooling", "lattice", "topology", "gyroid",
            "impossible to machine", "cannot machine", "not machinable", "enclosed cavity",
            "monolithic", "part consolidation", "lightweight lattice",
            "ct scan", "powder removal"
        }
        am_geom_hits = len([kw for kw in AM_GEOM_KW if kw in user_text])
        has_am_geom_signal = am_geom_hits >= 2 and primary == "AM"
        
        # Check for hybrid offer signal (keywords OR structured signals)
        hybrid_suitable_processes = {"CASTING", "FORGING", "MIM", "EXTRUSION", "THERMOFORMING", "COMPRESSION_MOLDING"}
        hybrid_keywords = ["machin", "datum", "tolerance", "drill", "tap", "mill", "trim", "finish", "interface", "critical", "hole", "holes"]
        has_hybrid_keyword_signal = any(kw in user_text for kw in hybrid_keywords)
        
        # Structured signal detection (for cases with minimal user_text)
        part = state.get("part_summary")
        tolerance_criticality = getattr(inp, "tolerance_criticality", "") if inp else ""
        feature_variety = getattr(part, "feature_variety", "") if part else ""
        accessibility_risk = getattr(part, "accessibility_risk", "") if part else ""
        has_clamping_faces = getattr(part, "has_clamping_faces", False) if part else False
        
        hybrid_structured_signal = (
            tolerance_criticality in {"Medium", "High"}
            or feature_variety == "High"
            or accessibility_risk in {"Medium", "High"}
            or has_clamping_faces is True
        )
        
        hybrid_offer = (
            primary in hybrid_suitable_processes
            and (has_hybrid_keyword_signal or hybrid_structured_signal)
            and score_diff >= 4  # Strong mismatch threshold
        )
        
        # Add hybrid offer finding if applicable
        if hybrid_offer and not any(f.id == "HYBRID1" for f in findings):
            secondary_text = "CNC trim and machining of critical interfaces" if primary == "THERMOFORMING" else "CNC for critical datums, tight tolerances, holes, and interfaces"
            if primary == "EXTRUSION":
                secondary_text = "CNC for cut-to-length, drilling, tapping, and milling"
            
            tolerance_crit = getattr(inp, "tolerance_criticality", "") if inp else ""
            severity_hybrid = "HIGH" if (score_diff >= 4 and tolerance_crit == "High") else "MEDIUM"
            finding_hybrid = Finding(
                id="HYBRID1",
                category="PROCESS_SELECTION",
                severity=severity_hybrid,
                title=f"Consider {primary} + CNC finishing",
                why_it_matters=f"Process selection intelligence recommends {primary} (score advantage: {score_diff} points) for near-net shape and economics. User requirements indicate need for secondary finishing operations.",
                recommendation=f"Primary: {primary} for near-net shape and economics at volume. Secondary: {secondary_text}. Design for finishing: define machining datums and leave stock only where needed.",
            )
            findings.append(finding_hybrid)
            result_trace = out.get("trace", [])
            result_trace.append(f"Hybrid offer added: {primary} + CNC finishing")
            out["trace"] = result_trace
        
        # Add PSI1 if not already present and hybrid offer not shown
        # BINS-MODE: suppress PSI1 or downgrade when cad_status != ok and selected is eligible
        if not any(f.id == "PSI1" for f in findings) and not hybrid_offer:
            # Bins-mode: downgrade or suppress PSI1 when selected is eligible
            if cad_status != "ok":
                if score_diff <= 2:
                    severity = "LOW"
                else:
                    severity = "MEDIUM"
                # Trace but do not add HIGH severity in bins-mode for eligible selection
            else:
                severity = "HIGH" if score_diff >= 3 else "MEDIUM"
            secondary = proc_rec.get("secondary", [])
            sec_str = f", {', '.join(secondary[:2])}" if secondary else ""
            
            # Enhanced text for AM offers
            if primary == "AM":
                am_tech, _ = _resolve_am_tech(state, getattr(inp, "am_tech", None) if inp else None)
                material = getattr(inp, "material", "") if inp else ""
                
                # Use centralized registry for pretty name
                am_tech_display = pretty_process_name("AM", am_tech)
                
                # Build "Why AM here" bullets from detected triggers
                why_am_bullets = []
                if am_geom_hits >= 2:
                    detected_geom = []
                    if any(kw in user_text for kw in ["internal channel", "internal channels"]):
                        detected_geom.append("internal channels")
                    if any(kw in user_text for kw in ["lattice", "topology", "gyroid"]):
                        detected_geom.append("lattice/topology")
                    if any(kw in user_text for kw in ["conformal cooling"]):
                        detected_geom.append("conformal cooling")
                    if any(kw in user_text for kw in ["impossible to machine", "cannot machine", "not machinable"]):
                        detected_geom.append("impossible-to-machine geometry")
                    if any(kw in user_text for kw in ["enclosed cavity", "trapped"]):
                        detected_geom.append("enclosed cavities")
                    if any(kw in user_text for kw in ["monolithic", "part consolidation"]):
                        detected_geom.append("monolithic/consolidated design")
                    
                    if detected_geom:
                        why_am_bullets.append(f"• AM-only geometry detected: {', '.join(detected_geom[:3])}")
                    else:
                        why_am_bullets.append("• AM-only geometry signals detected (internal channels/lattice/conformal cooling)")
                
                # Add material-based reason if applicable
                if material in ("Steel", "Aluminum") and am_tech == "METAL_LPBF":
                    why_am_bullets.append(f"• Metal material ({material}) favors {am_tech_display}")
                elif material == "Plastic" and am_tech in ("FDM", "SLA", "SLS", "MJF"):
                    why_am_bullets.append(f"• Plastic/resin material favors {am_tech_display}")
                
                # Build enhanced why_it_matters text
                why_text = f"Process selection intelligence recommends {am_tech_display} (score advantage: {score_diff} points) over selected {user_proc}."
                if why_am_bullets:
                    why_text += "\n\nWhy AM here:\n" + "\n".join(why_am_bullets)
                else:
                    why_text += " This may indicate suboptimal process choice for material, volume, or geometry."
                
                # Build enhanced recommendation with AM + CNC guidance
                rec_text = f"Consider {am_tech_display}{sec_str} as alternatives."
                secondary_list = proc_rec.get("secondary", [])
                if "CNC" in secondary_list or tolerance_criticality in ("Medium", "High") or has_hybrid_keyword_signal:
                    rec_text += "\n\nWhat this means in practice:\n"
                    rec_text += "• Use AM for near-net shape with complex/internal geometry\n"
                    rec_text += "• Plan CNC finishing for critical faces, holes, datums, and tight-tolerance interfaces\n"
                    rec_text += "• Design for hybrid manufacturing: leave stock only where machining is needed"
                else:
                    rec_text += " Evaluate tradeoffs: tooling lead time vs unit cost, tolerance/finish requirements, and volume sensitivity."
                
                finding = Finding(
                    id="PSI1",
                    category="PROCESS_SELECTION",
                    severity=severity,
                    title="Selected process differs from recommended process",
                    why_it_matters=why_text,
                    recommendation=rec_text,
                )
            else:
                # Standard text for non-AM offers
                why_text = f"Process selection intelligence recommends {primary} (score advantage: {score_diff} points) over selected {user_proc}."
                if has_am_geom_signal:
                    why_text += f" AM-only geometry signals (internal channels/lattice/conformal cooling) strongly favor {primary}."
                else:
                    why_text += " This may indicate suboptimal process choice for material, volume, or geometry."
                
                finding = Finding(
                    id="PSI1",
                    category="PROCESS_SELECTION",  # Runtime value; type hint allows DESIGN_REVIEW/DFM but runtime accepts any string
                    severity=severity,
                    title="Selected process differs from recommended process",
                    why_it_matters=why_text,
                    recommendation=f"Consider {primary}{sec_str} as alternatives. Evaluate tradeoffs: tooling lead time vs unit cost, tolerance/finish requirements, and volume sensitivity.",
                )
            
            findings.append(finding)
            result_trace = out.get("trace", [])
            result_trace.append(f"Process selection warning added: selected={user_proc}, recommended={primary}")
            out["trace"] = result_trace
        elif score_diff <= 1 and primary != user_proc:
            # Borderline case: add trace note but no finding
            result_trace = out.get("trace", [])
            result_trace.append(f"PSI borderline: selected={user_proc}, recommended={primary}, score_diff={score_diff} (too close to flag)")
            out["trace"] = result_trace

    # HYBRID_EXTR1: extrusion_likelihood >= med → offer EXTRUSION + CNC finishing (bins-mode)
    if primary and proc_rec:
        ext_lh = proc_rec.get("extrusion_likelihood") or {}
        ext_level = ext_lh.get("level", "none") if isinstance(ext_lh, dict) else "none"
        secondary = proc_rec.get("secondary", []) or []
        extrusion_in_primary_or_secondary = primary == "EXTRUSION" or "EXTRUSION" in secondary
        
        # Enhanced hybrid detection: CNC primary + EXTRUSION secondary with specific conditions
        production_volume = getattr(inp, "production_volume", "") if inp else ""
        material = getattr(inp, "material", "") if inp else ""
        production_volume_lower = production_volume.lower() if production_volume else ""
        material_lower = material.lower() if material else ""
        
        hybrid_conditions_met = (
            ext_level in ("med", "high")
            and (
                (primary == "CNC" and "EXTRUSION" in secondary)
                or (primary == "EXTRUSION" and "CNC" in secondary)
            )
            and (
                any(term in production_volume_lower for term in ("small", "batch", "proto"))
                or "steel" in material_lower
                or production_volume == "Production"  # Also trigger for Production volume
            )
        )
        
        if hybrid_conditions_met and not any(f.id in ("HYBRID1", "HYBRID_EXTR1") for f in findings):
            # Adjust recommendation text based on primary
            if primary == "CNC":
                rec_text = "Primary: CNC for precision and flexibility. Secondary: EXTRUSION for near-net shape and economics. Design for hybrid manufacturing: use extrusion for base profile, CNC for critical features."
            else:
                rec_text = "Primary: EXTRUSION for near-net shape and economics. Secondary: CNC for cut-to-length, drilling, tapping, and milling. Design for finishing: define machining datums and leave stock only where needed."
            
            finding_hybrid_extr = Finding(
                id="HYBRID_EXTR1",
                category="PROCESS_SELECTION",
                severity="MEDIUM",
                title="Consider EXTRUSION + CNC finishing",
                why_it_matters="Geometry indicates extrusion-friendly profile. Secondary CNC for cut-to-length, drilling, tapping, and milling improves fit and interface quality.",
                recommendation=rec_text,
            )
            findings.append(finding_hybrid_extr)
            result_trace = out.get("trace", [])
            result_trace.append("Hybrid offer added: EXTRUSION + CNC finishing (HYBRID_EXTR1)")
            out["trace"] = result_trace

        # EXTR_STEEL1: Steel + EXTRUSION supplier risk finding
        if material == "Steel" and ("EXTRUSION" == primary or "EXTRUSION" in secondary):
            if not any(f.id == "EXTR_STEEL1" for f in findings):
                finding_extr_steel = Finding(
                    id="EXTR_STEEL1",
                    category="PROCESS_SELECTION",
                    severity="MEDIUM",
                    title="Steel extrusion supplier availability / cost risk",
                    why_it_matters="Steel extrusion is less common than aluminum; fewer suppliers and higher cost/lead-time risk, depending on alloy and profile.",
                    recommendation="Confirm alloy, required tolerances, and supplier capability early; consider aluminum extrusion or CNC-from-bar as alternatives if supplier risk is high.",
                )
                findings.append(finding_extr_steel)
                result_trace = out.get("trace", [])
                result_trace.append("Steel extrusion risk finding added: EXTR_STEEL1")
                out["trace"] = result_trace

    trace_list = list(out.get("trace", []))
    cad_up = cad_uploaded(state)
    cad_ok = cad_evidence_available(state)
    ev_keys = list(cad_evidence_keys(state))
    trace_list.append(
        f"rules: cad_uploaded={'y' if cad_up else 'n'} cad_status={cad_analysis_status(state)} evidence_keys={ev_keys}"
    )
    # Diagnostic: CAD evidence available but no keys in state (wiring bug)
    if cad_up and cad_ok and not ev_keys:
        trace_list.append("diagnostic: cad_evidence_available_but_unused (evidence_keys empty)")
    result: dict = {"findings": findings, "trace": trace_list}
    if process == "AM" and "_am_tech_source" in out:
        result["_am_tech_source"] = out["_am_tech_source"]
    if "am_subprocess_hint" in out:
        result["am_subprocess_hint"] = out["am_subprocess_hint"]
    if "casting_subprocess_hint" in out:
        result["casting_subprocess_hint"] = out["casting_subprocess_hint"]
    if "forging_subprocess_hint" in out:
        result["forging_subprocess_hint"] = out["forging_subprocess_hint"]
    return result
