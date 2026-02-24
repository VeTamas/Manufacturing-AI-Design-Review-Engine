"""Process selection: geometry- and bin-driven scoring, primary/secondary recommendation.

PORTFOLIO / PUBLIC VERSION:
- Production scoring logic intentionally simplified for public portfolio version.
- Deterministic scoring and tie-break remain functional for demo; detailed proprietary
  heuristics, margin thresholds, and advanced hybrid process rules are reduced or
  marked with TODO where production would use expanded logic.
"""
from __future__ import annotations

from agent.cad.step_ingest import get_bbox_only
from agent.geometry.cad_presence import cad_analysis_status, cad_evidence_available, cad_uploaded
from agent.geometry.cad_lite import run_cad_lite
from agent.geometry.evidence_for_llm import build_cad_lite_evidence_from_rec
from agent.geometry.extrusion_lite import run_extrusion_lite
from agent.geometry.turning_lite import run_turning_lite
from agent.processes.gating import hard_gates
from agent.processes.extrusion_signal import extrusion_likelihood
from agent.processes.turning_signal import turning_likelihood
from agent.processes.sheet_metal_signal import sheet_metal_likelihood
from agent.state import GraphState, Finding
from agent.config import CONFIG
from agent.materials import resolve_material, MaterialProfile
from agent.scoring.portfolio_scoring import compute_portfolio_recommendation

CANDIDATES = ("CNC", "CNC_TURNING", "AM", "SHEET_METAL", "INJECTION_MOLDING", "CASTING", "FORGING", "EXTRUSION", "MIM", "THERMOFORMING", "COMPRESSION_MOLDING")


def _extrusion_level_from_cv(cv: float) -> str:
    """Determine extrusion level from coefficient of variation.
    
    Args:
        cv: Coefficient of variation (std/mean)
        
    Returns:
        "high", "med", "low", or "none"
    """
    if cv <= 0.05:
        return "high"
    if cv <= 0.12:
        return "med"
    if cv <= 0.25:
        return "low"
    return "none"


def _elongation_ratio(bbox_dims: list[float] | None, axis: str) -> float:
    """Compute elongation ratio: L / max(other two dimensions).
    
    Args:
        bbox_dims: Bounding box dimensions [dx, dy, dz]
        axis: Extrusion axis "X", "Y", or "Z"
        
    Returns:
        Elongation ratio (L / max(other two)), or 0.0 if invalid
    """
    if not bbox_dims or len(bbox_dims) < 3:
        return 0.0
    idx_map = {"X": 0, "Y": 1, "Z": 2}
    idx = idx_map.get(axis, 0)
    L = bbox_dims[idx]
    others = [bbox_dims[i] for i in range(3) if i != idx]
    if not others or max(others) <= 0:
        return 0.0
    return L / max(others)


def _normalize_primary_secondary(primary: str | None, secondary: list[str] | None) -> list[str]:
    """Normalize secondary list: remove duplicates and primary.
    
    Args:
        primary: Primary process name (or None)
        secondary: List of secondary process names (or None)
        
    Returns:
        Normalized secondary list (preserves order, removes duplicates and primary)
    """
    if not secondary:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for s in secondary:
        if not s:
            continue
        if primary and s == primary:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _strong_extrusion(extrusion_lite: dict | None, cad_lite: dict | None) -> bool:
    """Determine if geometry strongly matches extrusion profile.
    
    Checks:
    1. extrusion_lite.coeff_var <= 0.15 (strict)
    2. bbox elongation ratio >= 6.0 (L / max(other two))
    
    Args:
        extrusion_lite: Extrusion lite result dict
        cad_lite: CAD lite result dict
        
    Returns:
        True if strong extrusion geometry detected
    """
    if not extrusion_lite or extrusion_lite.get("status") != "ok":
        return False
    
    cv = extrusion_lite.get("coeff_var")
    axis = extrusion_lite.get("axis", "X")
    
    # Get bbox_dims from cad_lite if available, otherwise from extrusion_lite
    bbox_dims = None
    if cad_lite and cad_lite.get("status") == "ok":
        bbox_dims = cad_lite.get("bbox_dims")
    if not bbox_dims:
        bbox_dims = extrusion_lite.get("bbox_dims")
    
    ratio = _elongation_ratio(bbox_dims, axis) if bbox_dims else 0.0
    
    # Strict criteria: coeff_var <= 0.15 AND elongation ratio >= 6.0
    return isinstance(cv, (int, float)) and cv <= 0.15 and ratio >= 6.0


# Keyword buckets for user_text scoring (portfolio: production uses expanded/refined sets)
IM_KW = {
    "draft", "texture", "gate", "gating", "weld line", "weldline", "vent", "venting",
    "sink", "warpage", "warp", "rib", "boss", "ejector", "ejection", "side action",
    "lifter", "insert", "overmold", "over-mold", "undercut", "runner", "sprue",
    "mold", "mould", "cooling", "knit line"
}
SM_KW = {
    "bend", "bending", "flange", "hem", "punch", "laser", "waterjet", "k-factor",
    "flat pattern", "unfold", "relief", "pem", "pe m", "clinch", "rivet",
    "spot weld", "brake", "sheet metal"
}
AM_KW = {
    "support", "supports", "overhang", "bridge", "orientation", "layer", "anisotropy",
    "print", "3d print", "fdm", "sla", "sls", "lpbf", "dmls", "sinter", "resin",
    "additive"
}
AM_GEOM_KW = {
    "internal channel", "internal channels", "conformal cooling", "lattice", "topology", "gyroid",
    "impossible to machine", "cannot machine", "not machinable", "enclosed cavity",
    "monolithic", "part consolidation", "lightweight lattice",
    "ct scan", "powder removal"
}
CNC_MILL_KW = {
    "milling", "endmill", "pocket", "slot", "chamfer", "fillet", "3-axis", "5-axis",
    "toolpath", "fixture", "fixturing", "vice", "deburr", "surface finish", "ra",
    "machin"
}
CNC_TURN_KW = {
    "turning", "lathe", "spindle", "chuck", "tailstock", "steady rest", "runout",
    "concentricity", "bar stock", "live tooling", "grooving", "threading", "turn"
}
FORG_KW = {
    "forging", "forged", "flash", "die", "hammer", "press", "closed die", "impression die",
    "open die", "parting line", "draft", "grain flow", "laps", "fold", "cold shut",
    "underfill", "trim", "coining", "ring rolling"
}
EXTR_KW = {
    "extrusion", "profile", "rail", "channel", "anodize", "6063", "constant cross section",
    "long prismatic", "hollow profile", "extruded", "die swell", "calibration"
}
MIM_KW = {
    "mim", "metal injection molding", "metal injection moulding",
    "powder", "feedstock", "binder", "debinding", "sinter", "sintering",
    "17-4", "17-4ph", "316l", "stainless", "small metal part",
    "high volume", "complex", "near-net"
}
THERMOFORMING_KW = {
    "thermoforming", "thermoform", "vacuum forming", "vacuum form", "pressure forming",
    "sheet forming", "plug assist", "twin-sheet", "twin sheet", "matched mold",
    "trim", "cnc trim", "flange", "draw", "deep draw", "webbing", "vent holes", "vacuum holes",
    "large plastic cover", "housing cover", "panel"
}
COMPRESSION_KW = {
    "compression molding", "compression moulding", "thermoset", "thermosetting",
    "smc", "bmc", "bulk molding compound", "sheet molding compound",
    "phenolic", "epoxy", "polyester resin", "cure", "curing",
    "press", "heated mold", "matched die", "charge", "charge placement",
    "flash", "parting line", "trim flash", "debulking",
    "fiber orientation", "glass fiber", "carbon fiber", "composite"
}


def _has_any(text: str, kws: set[str]) -> bool:
    """Check if text contains any keyword from the set."""
    t = (text or "").lower()
    return any(k in t for k in kws)


# Score breakdown entry: {"delta", "reason", "rule_id", "severity", "title"?, "why_it_matters"?, "recommendation"?}
# severity: "info"|"low"|"med"|"high"
def _apply_material_modifiers(
    scores: dict[str, int],
    eligible_processes: list[str],
    material_profile: MaterialProfile,
    findings: list[Finding],
    trace: list[str],
    score_breakdown: dict[str, list],
) -> None:
    """
    Apply material property modifiers to process scores.
    
    Deterministic rules based on material properties:
    - CNC: machinability affects score
    - SHEET_METAL: formability affects score
    - EXTRUSION: extrudability affects score
    - CASTING: castability affects score
    - AM: am_readiness and am_postprocess_intensity affect score
    
    Mutates scores, findings, trace, score_breakdown.
    """
    props = material_profile.properties
    
    # CNC: machinability modifiers
    if "CNC" in eligible_processes and "CNC" in scores:
        if props.machinability.value == "HARD":
            scores["CNC"] = scores.get("CNC", 0) - 1
            finding = Finding(
                id="MAT_CNC_HARD",
                category="PROCESS_SELECTION",
                severity="MEDIUM",
                title="Material machinability: Hard",
                why_it_matters=f"{material_profile.label} is harder to machine, increasing tool wear and cycle time.",
                recommendation="Consider alternative processes (casting, forging) or optimize tooling strategy for hard materials.",
            )
            findings.append(finding)
            trace.append(f"material_mod: CNC -1 (machinability=HARD)")
            if "CNC" not in score_breakdown:
                score_breakdown["CNC"] = []
            score_breakdown["CNC"].append({"delta": -1, "reason": "Material machinability: Hard", "rule_id": "MAT_CNC_HARD", "severity": "MEDIUM"})
        elif props.machinability.value == "VERY_HARD":
            scores["CNC"] = scores.get("CNC", 0) - 2
            finding = Finding(
                id="MAT_CNC_VERY_HARD",
                category="PROCESS_SELECTION",
                severity="MEDIUM",
                title="Material machinability: Very Hard",
                why_it_matters=f"{material_profile.label} is very hard to machine, significantly increasing tool wear, cycle time, and cost.",
                recommendation="Strongly consider alternative processes (casting, forging, AM) or specialized tooling for very hard materials.",
            )
            findings.append(finding)
            trace.append(f"material_mod: CNC -2 (machinability=VERY_HARD)")
            if "CNC" not in score_breakdown:
                score_breakdown["CNC"] = []
            score_breakdown["CNC"].append({"delta": -2, "reason": "Material machinability: Very Hard", "rule_id": "MAT_CNC_VERY_HARD", "severity": "MEDIUM"})
    
    # SHEET_METAL: formability modifiers
    if "SHEET_METAL" in eligible_processes and "SHEET_METAL" in scores:
        if props.formability.value == "LOW":
            scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) - 2
            finding = Finding(
                id="MAT_SHEET_LOW_FORM",
                category="PROCESS_SELECTION",
                severity="MEDIUM",
                title="Material formability: Low",
                why_it_matters=f"{material_profile.label} has low formability, making sheet metal forming difficult and increasing risk of cracking.",
                recommendation="Consider alternative processes (CNC, casting) or use specialized forming techniques for low-formability materials.",
            )
            findings.append(finding)
            trace.append(f"material_mod: SHEET_METAL -2 (formability=LOW)")
            if "SHEET_METAL" not in score_breakdown:
                score_breakdown["SHEET_METAL"] = []
            score_breakdown["SHEET_METAL"].append({"delta": -2, "reason": "Material formability: Low", "rule_id": "MAT_SHEET_LOW_FORM", "severity": "MEDIUM"})
        elif props.formability.value == "HIGH":
            scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) + 1
            trace.append(f"material_mod: SHEET_METAL +1 (formability=HIGH)")
            if "SHEET_METAL" not in score_breakdown:
                score_breakdown["SHEET_METAL"] = []
            score_breakdown["SHEET_METAL"].append({"delta": 1, "reason": "Material formability: High", "rule_id": "MAT_SHEET_HIGH_FORM", "severity": "info"})
    
    # EXTRUSION: extrudability modifiers
    if "EXTRUSION" in eligible_processes and "EXTRUSION" in scores:
        if props.extrudability.value == "HIGH":
            scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + 2
            trace.append(f"material_mod: EXTRUSION +2 (extrudability=HIGH)")
            if "EXTRUSION" not in score_breakdown:
                score_breakdown["EXTRUSION"] = []
            score_breakdown["EXTRUSION"].append({"delta": 2, "reason": "Material extrudability: High", "rule_id": "MAT_EXTR_HIGH", "severity": "info"})
        elif props.extrudability.value == "LOW":
            scores["EXTRUSION"] = scores.get("EXTRUSION", 0) - 2
            trace.append(f"material_mod: EXTRUSION -2 (extrudability=LOW)")
            if "EXTRUSION" not in score_breakdown:
                score_breakdown["EXTRUSION"] = []
            score_breakdown["EXTRUSION"].append({"delta": -2, "reason": "Material extrudability: Low", "rule_id": "MAT_EXTR_LOW", "severity": "info"})
    
    # CASTING: castability modifiers
    if "CASTING" in eligible_processes and "CASTING" in scores:
        if props.castability.value == "HIGH":
            scores["CASTING"] = scores.get("CASTING", 0) + 2
            trace.append(f"material_mod: CASTING +2 (castability=HIGH)")
            if "CASTING" not in score_breakdown:
                score_breakdown["CASTING"] = []
            score_breakdown["CASTING"].append({"delta": 2, "reason": "Material castability: High", "rule_id": "MAT_CAST_HIGH", "severity": "info"})
        elif props.castability.value == "LOW":
            scores["CASTING"] = scores.get("CASTING", 0) - 2
            trace.append(f"material_mod: CASTING -2 (castability=LOW)")
            if "CASTING" not in score_breakdown:
                score_breakdown["CASTING"] = []
            score_breakdown["CASTING"].append({"delta": -2, "reason": "Material castability: Low", "rule_id": "MAT_CAST_LOW", "severity": "info"})
    
    # AM: am_readiness and am_postprocess_intensity modifiers
    if "AM" in eligible_processes and "AM" in scores:
        if props.am_readiness.value == "HIGH":
            scores["AM"] = scores.get("AM", 0) + 2
            trace.append(f"material_mod: AM +2 (am_readiness=HIGH)")
            if "AM" not in score_breakdown:
                score_breakdown["AM"] = []
            score_breakdown["AM"].append({"delta": 2, "reason": "Material AM readiness: High", "rule_id": "MAT_AM_HIGH", "severity": "info"})
        elif props.am_readiness.value == "MEDIUM":
            scores["AM"] = scores.get("AM", 0) + 1
            trace.append(f"material_mod: AM +1 (am_readiness=MEDIUM)")
            if "AM" not in score_breakdown:
                score_breakdown["AM"] = []
            score_breakdown["AM"].append({"delta": 1, "reason": "Material AM readiness: Medium", "rule_id": "MAT_AM_MED", "severity": "info"})
        elif props.am_readiness.value == "LOW":
            scores["AM"] = scores.get("AM", 0) - 2
            finding = Finding(
                id="MAT_AM_LOW_READINESS",
                category="PROCESS_SELECTION",
                severity="MEDIUM",
                title="Material AM readiness: Low",
                why_it_matters=f"{material_profile.label} has low AM readiness, making additive manufacturing challenging or unsuitable.",
                recommendation="Consider alternative processes (CNC, casting) or specialized AM materials/processes for low-readiness materials.",
            )
            findings.append(finding)
            trace.append(f"material_mod: AM -2 (am_readiness=LOW)")
            if "AM" not in score_breakdown:
                score_breakdown["AM"] = []
            score_breakdown["AM"].append({"delta": -2, "reason": "Material AM readiness: Low", "rule_id": "MAT_AM_LOW_READINESS", "severity": "MEDIUM"})
        
        if props.am_postprocess_intensity.value == "HIGH":
            scores["AM"] = scores.get("AM", 0) - 1
            finding = Finding(
                id="MAT_AM_POSTPROC_HIGH",
                category="PROCESS_SELECTION",
                severity="MEDIUM",
                title="Material AM post-processing: High intensity",
                why_it_matters=f"{material_profile.label} requires intensive post-processing (e.g., heat treatment, support removal), increasing cost and lead time.",
                recommendation="Factor in post-processing costs and time when evaluating AM; consider processes with lower post-processing requirements.",
            )
            findings.append(finding)
            trace.append(f"material_mod: AM -1 (am_postprocess_intensity=HIGH)")
            if "AM" not in score_breakdown:
                score_breakdown["AM"] = []
            score_breakdown["AM"].append({"delta": -1, "reason": "Material AM post-processing: High intensity", "rule_id": "MAT_AM_POSTPROC_HIGH", "severity": "MEDIUM"})


def _add_score(
    proc: str,
    delta: int,
    reason: str,
    rule_id: str,
    scores: dict[str, int],
    score_breakdown: dict[str, list[dict]],
    severity: str = "info",
    title: str | None = None,
    why_it_matters: str | None = None,
    recommendation: str | None = None,
) -> None:
    """Add score delta and record in breakdown. For HIGH/MED entries, include finding metadata."""
    scores[proc] = scores.get(proc, 0) + delta
    entry: dict = {"delta": delta, "reason": reason, "rule_id": rule_id, "severity": severity}
    if title:
        entry["title"] = title
    if why_it_matters:
        entry["why_it_matters"] = why_it_matters
    if recommendation:
        entry["recommendation"] = recommendation
    if proc not in score_breakdown:
        score_breakdown[proc] = []
    score_breakdown[proc].append(entry)


def _resolve_am_tech(state: GraphState, user_selected_am_tech: str | None = None) -> tuple[str, str]:
    """
    Resolve AM technology: AUTO -> detect from material/keywords, else use provided value.
    Returns: (am_tech, resolution_source) where resolution_source in ("explicit","keyword","material","default").
    """
    inp = state.get("inputs")
    user_text = (
        (getattr(inp, "user_text", None) if inp else None) or
        (getattr(inp, "text", None) if inp else None) or
        (getattr(inp, "notes", None) if inp else None) or
        state.get("user_text") or state.get("text") or state.get("description") or ""
    ).lower()
    material_raw = getattr(inp, "material", "") if inp else ""
    material = (material_raw or "").lower()

    am_tech = user_selected_am_tech or (getattr(inp, "am_tech", None) if inp else None) or "AUTO"
    if am_tech and am_tech != "AUTO":
        return am_tech, "explicit"

    # Keyword detection (highest priority)
    if any(kw in user_text for kw in ["dmls", "slm", "lpbf", "laser powder bed", "metal lpbf"]):
        return "METAL_LPBF", "keyword"
    if any(kw in user_text for kw in ["fdm", "fff", "fused deposition"]):
        return "FDM", "keyword"
    if any(kw in user_text for kw in ["peek", "pei", "ultem", "heated chamber"]):
        return "THERMOPLASTIC_HIGH_TEMP", "keyword"
    if any(kw in user_text for kw in ["sla", "resin", "photopolymer", "stereolithography"]):
        return "SLA", "keyword"
    if any(kw in user_text for kw in ["sls", "nylon powder", "pa12"]):
        return "SLS", "keyword"
    if any(kw in user_text for kw in ["mjf", "hp mjf", "multi jet fusion"]):
        return "MJF", "keyword"

    # Material heuristics
    if any(kw in material for kw in ["steel", "stainless", "aluminum", "titanium"]):
        return "METAL_LPBF", "material"
    if any(kw in material for kw in ["plastic", "polymer", "nylon"]) or material == "plastic":
        if any(kw in user_text for kw in ["resin", "photopolymer", "uv cure"]):
            return "SLA", "material"
        if any(kw in user_text for kw in ["hp", "mjf", "multi jet"]):
            return "MJF", "material"
        return "SLS", "material"

    return "FDM", "default"


def _score_im(
    material: str,
    production_volume: str,
    feature_variety: str,
    pocket_aspect_class: str,
    tolerance_criticality: str,
    accessibility_risk: str,
    has_2d: bool,
    conf_present: bool,
    user_text: str = "",
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if material == "Plastic":
        score += 3
        reasons.append("Plastic material favors injection molding")
    
    # Material gating: strong penalty for metal materials unless material-change signal exists
    metal_materials = {"Steel", "Aluminum"}
    material_change_signals = ["plastic ok", "material change ok", "polymer acceptable", "material change", "switch to plastic", "plastic material"]
    has_material_change_signal = any(signal in user_text.lower() for signal in material_change_signals)
    
    if material in metal_materials and not has_material_change_signal:
        score -= 5
        reasons.append("Metal material disfavors injection molding (requires material change)")
    
    if production_volume == "Production":
        score += 3
        reasons.append("Production volume favors IM economics")
    if feature_variety in ("Low", "Medium"):
        score += 1
    if pocket_aspect_class == "OK":
        score += 1
    if tolerance_criticality == "High" and (not conf_present or not has_2d):
        score -= 2
        reasons.append("Tight tolerances without 2D drawing penalize IM")
    if accessibility_risk == "High":
        score -= 1
    return score, reasons


def _score_cnc(
    material: str,
    production_volume: str,
    tolerance_criticality: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if material in ("Aluminum", "Steel"):
        score += 3
        reasons.append("Metal material favors CNC")
    if production_volume in ("Proto", "Small batch"):
        score += 2
        reasons.append("Low volume favors CNC flexibility")
    if tolerance_criticality == "High":
        score += 1
    if production_volume == "Production" and material == "Plastic":
        score -= 2
        reasons.append("Production Plastic often better with IM")
    return score, reasons


def _score_am(
    production_volume: str,
    feature_variety: str,
    pocket_aspect_class: str,
    tolerance_criticality: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if production_volume == "Proto":
        score += 2
        reasons.append("Proto volume favors AM")
    if feature_variety == "High" or pocket_aspect_class in ("Risky", "Extreme"):
        score += 1
    if tolerance_criticality == "High":
        score -= 2
        reasons.append("Tight tolerances penalize AM")
    if production_volume == "Production" and feature_variety in ("Low", "Medium"):
        score -= 2
        reasons.append("Production + simple geometry penalize AM")
    return score, reasons


def _score_sheet_metal(
    min_wall_thickness: str,
    part_size: str,
    feature_variety: str,
    pocket_aspect_class: str,
    tolerance_criticality: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if min_wall_thickness == "Thin" and part_size in ("Medium", "Large"):
        score += 2
        reasons.append("Low wall + medium/large part favors sheet metal")
    if feature_variety == "High":
        score += 1
    if pocket_aspect_class in ("Risky", "Extreme"):
        score -= 2
        reasons.append("Complex pockets disfavor sheet metal")
    if tolerance_criticality == "High":
        score -= 1
    return score, reasons


def _score_cnc_turning(
    user_process: str,
    part_size: str,
    feature_variety: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if user_process == "CNC_TURNING":
        score += 2
        reasons.append("User selected turning")
    if part_size in ("Small", "Medium"):
        score += 1
    if feature_variety == "High":
        score -= 1
    return score, reasons


def _score_mim(
    material: str,
    production_volume: str,
    part_size: str,
    feature_variety: str,
    min_wall_thickness: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    # MIM metal signal: only add if MIM-specific signals present (handled in keyword/geometry section)
    # Do NOT add metal-only boost here
    
    # Volume bucket normalization
    volume_bucket = "PROTO" if production_volume == "Proto" else "LOW" if production_volume == "Small batch" else "MED" if production_volume == "Production" else "UNKNOWN"
    
    if production_volume == "Production":
        score += 2
        reasons.append("Production volume favors MIM economics")
    
    # Volume-aware "small complex metal part" boost
    if part_size == "Small" and feature_variety in ("Medium", "High"):
        if volume_bucket == "MED":  # Production volume
            score += 2
            reasons.append("Small complex metal part favors MIM")
        else:
            # Proto/LOW volume: reduced boost (technical fit only)
            score += 1
            # No reason added for low-volume technical fit
    
    if min_wall_thickness in ("Thin", "Medium") and part_size == "Small":
        score += 1
    if part_size == "Large":
        score -= 2
        reasons.append("Large part disfavors MIM (consider casting/forging)")
    
    # Increased penalties for low volume
    if production_volume == "Proto":
        score -= 3
        reasons.append("Proto volume penalizes MIM tooling economics")
    elif production_volume == "Small batch":
        score -= 2
        reasons.append("Low volume penalizes MIM tooling economics")
    
    return score, reasons


def _score_thermoforming(
    material: str,
    production_volume: str,
    part_size: str,
    feature_variety: str,
    min_wall_thickness: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    # Plastic material: only +1 base (not +3) unless keyword cluster present (handled in keyword section)
    if material == "Plastic":
        score += 1
        # Reason only added if combined with thermoforming indicators (checked later)
    # Production volume: only emit reason if material is Plastic (metal parts shouldn't get this reason)
    if production_volume == "Production":
        delta = 2
        score += delta
        # Only append reason if material is Plastic (thermoforming is primarily for plastic sheet forming)
        if material == "Plastic":
            reasons.append("Production volume favors thermoforming economics")
    # Geometry trigger: only emit reason if material is Plastic
    if part_size in ("Medium", "Large") and feature_variety in ("Low", "Medium"):
        delta = 2
        score += delta
        # Only append reason if material is Plastic
        if material == "Plastic":
            reasons.append("Large sheet-formed profile signal")
    # Negative signal: always emit (it's a warning/disqualifier)
    if part_size == "Small" and feature_variety == "High":
        delta = -1
        score += delta
        reasons.append("Small + high feature variety disfavors thermoforming (IM/CNC often better)")
    # Thin wall trigger: no reason needed (minor boost)
    if min_wall_thickness == "Thin" and part_size in ("Medium", "Large"):
        score += 1
    return score, reasons


def _score_compression_molding(
    material: str,
    production_volume: str,
    part_size: str,
    feature_variety: str,
    min_wall_thickness: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    # Material signal: thermoset/composite materials favor compression molding
    # Note: material enum may not include "Thermoset", so rely on keywords for material detection
    # Production volume: only emit reason if rule contributes (delta is non-zero)
    # Note: Reason will be filtered later if no compression keywords are present
    if production_volume == "Production":
        delta = 2
        score += delta
        # Emit reason (will be filtered later if no compression signals)
        reasons.append("Production volume favors compression molding economics")
    # Geometry trigger: only emit reason if rule contributes
    if part_size in ("Medium", "Large") and feature_variety in ("Low", "Medium"):
        delta = 1
        score += delta
        reasons.append("Medium/large part with moderate complexity favors compression")
    # Negative signal: always emit (it's a warning/disqualifier)
    if part_size == "Small" and feature_variety == "High":
        delta = -1
        score += delta
        reasons.append("Small + high feature variety disfavors compression (IM/CNC often better)")
    return score, reasons


def process_selection_node(state: GraphState) -> dict:
    """Compute process recommendation (primary/secondary/not_recommended) from inputs and part summary.
    Two-path scoring: legacy_bins when cad_status != ok; numeric (same logic + adapter-refined bins) when cad_status == ok.
    """
    trace = ["Process selection node entered"]
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    has_2d = False
    if conf_inputs is not None:
        has_2d = conf_inputs.get("has_2d_drawing", False) if isinstance(conf_inputs, dict) else bool(getattr(conf_inputs, "has_2d_drawing", False))
    conf_present = conf_inputs is not None

    if not inp or not part:
        trace.append("Process selection skipped: missing inputs or part_summary")
        return {
            "process_recommendation": {
                "primary": None,
                "secondary": [],
                "not_recommended": [],
                "reasons": ["Missing inputs/part summary for process selection."],
                "tradeoffs": [],
                "scores": {},
            },
            "trace": trace,
        }

    material = getattr(inp, "material", "") or ""
    production_volume = getattr(inp, "production_volume", "") or ""
    
    # Canonical user_text: check multiple sources for robustness (needed for material resolution)
    user_text = (
        (getattr(inp, "user_text", None) if inp else None) or
        (getattr(inp, "text", None) if inp else None) or
        (getattr(inp, "notes", None) if inp else None) or
        state.get("user_text") or
        state.get("text") or
        state.get("description") or
        ""
    ).strip().lower()
    
    # Resolve material to profile (deterministic, backward compatible)
    # First try with material string, then check user_text for specific material hints if generic
    material_resolution = resolve_material(material_text=material)
    # If resolved to generic and user_text has specific material hints, try resolving from user_text
    if material_resolution.profile.id in ("steel_generic", "aluminum_generic", "plastic_generic") and user_text:
        # Check for specific material keywords in user_text
        if "stainless" in user_text or "304" in user_text or "316" in user_text:
            material_resolution = resolve_material(material_text="stainless")
        elif "titanium" in user_text or "ti6al4v" in user_text or "ti-6al-4v" in user_text:
            material_resolution = resolve_material(material_text="titanium")
    material_profile = material_resolution.profile
    trace.append(f"material: resolved={material_profile.id} source={material_resolution.source}")

    # Hard gating: compute eligible processes
    gates = hard_gates(CANDIDATES, material)
    eligible_processes = [p for p in CANDIDATES if gates.get(p, {}).get("eligible", True)]
    gated_out = [p for p in CANDIDATES if not gates.get(p, {}).get("eligible", True)]
    trace.append(f"process_selection: eligible_processes={sorted(eligible_processes)}")
    trace.append(
        f"process_selection: gated_out={[(p, gates.get(p, {}).get('reason', '')) for p in gated_out]}"
    )
    # Ensure at least one eligible process always exists
    if not eligible_processes:
        eligible_processes = ["CNC"]
        trace.append("fallback_primary_due_to_empty_eligible")
    tolerance_criticality = getattr(inp, "tolerance_criticality", "") or ""
    user_process_raw = getattr(inp, "process", "") or "AUTO"
    # Treat AUTO as no user selection (geometry-driven)
    user_process = None if user_process_raw == "AUTO" else user_process_raw
    is_auto_mode = user_process_raw == "AUTO"
    part_size = getattr(part, "part_size", "") or ""
    min_wall_thickness = getattr(part, "min_wall_thickness", "") or ""
    feature_variety = getattr(part, "feature_variety", "") or ""
    pocket_aspect_class = getattr(part, "pocket_aspect_class", "") or ""
    accessibility_risk = getattr(part, "accessibility_risk", "") or ""
    min_internal_radius = getattr(part, "min_internal_radius", "") or ""

    # Canonical user_text: check multiple sources for robustness
    # (Note: user_text was already extracted above for material resolution)
    text = user_text  # Alias for backward compatibility with existing code
    
    # Trace user_text for debugging
    trace.append(f'PSI: user_text_len={len(user_text)} preview="{user_text[:60]}"')

    # ----- Portfolio demo mode: simplified scoring (public-safe) -----
    if CONFIG.portfolio_mode:
        trace.append("process_selection: PORTFOLIO_MODE=1 using simplified portfolio scoring")
        rec = compute_portfolio_recommendation(
            material=material,
            production_volume=production_volume,
            part_size=part_size,
            feature_variety=feature_variety,
            min_wall_thickness=min_wall_thickness,
            tolerance_criticality=tolerance_criticality,
            user_process_raw=user_process_raw,
            eligible_processes=eligible_processes,
            gates=gates,
            user_text=user_text,
        )
        trace.append(f"Process selection (portfolio): primary={rec['primary']} secondary={rec.get('secondary', [])}")
        return {
            "process_recommendation": rec,
            "trace": trace,
            "findings": list(state.get("findings", [])),
        }

    # ----- Production path: full heuristics and tie-break -----
    all_reasons: list[str] = []
    scores: dict[str, int] = {}
    score_breakdown: dict[str, list[dict]] = {p: [] for p in CANDIDATES}
    findings: list[Finding] = list(state.get("findings", []))  # Get existing findings from state

    sim, rim = _score_im(
        material, production_volume, feature_variety, pocket_aspect_class,
        tolerance_criticality, accessibility_risk, has_2d, conf_present, text,
    )
    scores["INJECTION_MOLDING"] = sim
    all_reasons.extend(rim)

    scnc, rcnc = _score_cnc(material, production_volume, tolerance_criticality)
    scores["CNC"] = scnc
    all_reasons.extend(rcnc)

    sam, ram = _score_am(production_volume, feature_variety, pocket_aspect_class, tolerance_criticality)
    scores["AM"] = sam
    all_reasons.extend(ram)

    ssm, rsm = _score_sheet_metal(min_wall_thickness, part_size, feature_variety, pocket_aspect_class, tolerance_criticality)
    scores["SHEET_METAL"] = ssm
    all_reasons.extend(rsm)

    sturn, rturn = _score_cnc_turning(user_process, part_size, feature_variety)
    scores["CNC_TURNING"] = sturn
    all_reasons.extend(rturn)

    smim, rmim = _score_mim(material, production_volume, part_size, feature_variety, min_wall_thickness)
    scores["MIM"] = smim
    # Only extend reasons if score is non-zero (indicates rule contributed)
    if smim != 0:
        all_reasons.extend(rmim)

    sthermo, rthermo = _score_thermoforming(material, production_volume, part_size, feature_variety, min_wall_thickness)
    scores["THERMOFORMING"] = sthermo
    # Only extend reasons if score is non-zero AND (material is Plastic OR thermoforming keywords present)
    # This prevents thermoforming reasons from leaking for metal parts
    has_thermo_kw = _has_any(text, THERMOFORMING_KW)
    if sthermo != 0 and (material == "Plastic" or has_thermo_kw):
        all_reasons.extend(rthermo)

    scomp, rcomp = _score_compression_molding(material, production_volume, part_size, feature_variety, min_wall_thickness)
    scores["COMPRESSION_MOLDING"] = scomp
    # Only extend reasons if score is non-zero AND (compression keywords present OR score > 1)
    # This prevents "volume economics" reason from leaking for non-compression parts
    has_compression_kw = _has_any(text, COMPRESSION_KW)
    if scomp != 0 and (has_compression_kw or scomp > 1):
        all_reasons.extend(rcomp)

    # Apply material property modifiers to scores (deterministic, based on material profile)
    # Called after base scores but before final tie-break/hybrid logic
    _apply_material_modifiers(
        scores=scores,
        eligible_processes=eligible_processes,
        material_profile=material_profile,
        findings=findings,
        trace=trace,
        score_breakdown=score_breakdown,
    )

    # Economics penalties/boosts (score-first, findings-from-score)
    if production_volume in ("Proto", "Small batch"):
        if "INJECTION_MOLDING" in eligible_processes:
            _add_score(
                "INJECTION_MOLDING", -6,
                "Low volume tooling ROI risk",
                "IM1", scores, score_breakdown,
                severity="high",
                title="Low volume + injection molding (tooling ROI risk)",
                why_it_matters="Injection molding has high upfront tooling cost; unit cost only becomes favorable at high volumes.",
                recommendation="Consider alternative processes (CNC, AM) for low volumes; injection molding best for stable designs at production scale.",
            )
            all_reasons.append("Low volume disfavors injection molding (tooling ROI risk)")
        if "MIM" in eligible_processes:
            _add_score(
                "MIM", -6,
                "Low volume MIM tooling ROI risk",
                "MIM1", scores, score_breakdown,
                severity="high",
                title="Low volume + MIM (tooling ROI risk)",
                why_it_matters="MIM has high upfront tooling cost; unit cost only becomes favorable at production volumes.",
                recommendation="Consider CNC or AM for low volumes; MIM best for stable designs at production scale.",
            )
        if "CASTING" in eligible_processes:
            _add_score(
                "CASTING", -3,
                "Low volume casting tooling risk",
                "CAST1", scores, score_breakdown,
                severity="med",
                title="Low volume + casting (tooling risk)",
                why_it_matters="Casting has significant tooling cost; economics favor production runs.",
                recommendation="Consider CNC or AM for low volumes; casting best at production scale.",
            )
        if "FORGING" in eligible_processes:
            _add_score(
                "FORGING", -3,
                "Low volume forging tooling risk",
                "FORG1", scores, score_breakdown,
                severity="med",
                title="Low volume + forging (tooling risk)",
                why_it_matters="Forging has significant die cost; economics favor production runs.",
                recommendation="Consider CNC or AM for low volumes; forging best at production scale.",
            )
    elif production_volume == "Production":
        if "INJECTION_MOLDING" in eligible_processes:
            _add_score(
                "INJECTION_MOLDING", 2,
                "Production volume favors IM economics",
                "IM_VOL", scores, score_breakdown,
                severity="info",
            )
        if "MIM" in eligible_processes:
            _add_score(
                "MIM", 2,
                "Production volume favors MIM economics",
                "MIM_VOL", scores, score_breakdown,
                severity="info",
            )

    # User text keyword-based scoring adjustments
    keyword_matches: list[str] = []
    
    # Apply keyword score deltas
    if _has_any(text, IM_KW):
        scores["INJECTION_MOLDING"] += 2
        keyword_matches.append("IM")
    if _has_any(text, SM_KW):
        scores["SHEET_METAL"] += 2
        keyword_matches.append("SM")
    if _has_any(text, AM_KW):
        scores["AM"] += 2
        keyword_matches.append("AM")
    
    # AM-only geometry signals: strong boost for impossible-to-machine features
    am_geom_matched = [kw for kw in AM_GEOM_KW if kw in user_text]
    am_geom_hits = len(am_geom_matched)
    if am_geom_hits > 0:
        trace.append(f"PSI: am_geom_hits={am_geom_hits}")
    # AM-only geometry signals: only emit reason if threshold met (reason hygiene)
    # Reason only emitted when am_geom_hits >= 2 (strong signal, +4 score boost)
    if am_geom_hits >= 2:
        scores["AM"] = scores.get("AM", 0) + 4
        all_reasons.append("AM-only geometry signals detected (internal channels/lattice/conformal cooling)")
        keyword_matches.append("AM_GEOM")
    elif am_geom_hits == 1:
        scores["AM"] = scores.get("AM", 0) + 2
        # Score boost applied but no reason emitted (reason hygiene: only strong signals get reasons)
        keyword_matches.append("AM_GEOM")
    if _has_any(text, CNC_MILL_KW):
        scores["CNC"] += 1
        keyword_matches.append("CNC")
    if _has_any(text, CNC_TURN_KW):
        scores["CNC_TURNING"] += 2
        keyword_matches.append("Turning")
    if _has_any(text, FORG_KW):
        scores["FORGING"] = scores.get("FORGING", 0) + 2
        keyword_matches.append("FORGING")
    if _has_any(text, EXTR_KW):
        scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + 2
        keyword_matches.append("EXTRUSION")
    # MIM keyword scoring: ≥2 keywords → +3, exactly 1 → +1
    # Also add metal boost ONLY if MIM-specific signals present
    mim_matched = [kw for kw in MIM_KW if kw in text]
    # Special case: metal/stainless + sinter/debinding counts as ≥2
    metal_kws = {"metal", "stainless", "17-4", "17-4ph", "316l"}
    process_kws = {"sinter", "sintering", "debinding", "powder", "feedstock", "binder"}
    has_metal = any(kw in text for kw in metal_kws)
    has_process = any(kw in text for kw in process_kws)
    has_mim_keyword_signal = len(mim_matched) >= 2 or (has_metal and has_process) or len(mim_matched) == 1
    if len(mim_matched) >= 2 or (has_metal and has_process):
        scores["MIM"] = scores.get("MIM", 0) + 3
        keyword_matches.append("MIM")
    elif len(mim_matched) == 1:
        scores["MIM"] = scores.get("MIM", 0) + 1
        keyword_matches.append("MIM")
    # THERMOFORMING keyword scoring: ≥2 keywords → +3, exactly 1 → +1
    # When keyword cluster present, plastic boost is already covered by keyword boost
    thermo_matched = [kw for kw in THERMOFORMING_KW if kw in text]
    has_thermo_cluster = len(thermo_matched) >= 2
    if has_thermo_cluster:
        scores["THERMOFORMING"] = scores.get("THERMOFORMING", 0) + 3
        # If plastic material, remove the +1 base plastic score (keywords provide the boost)
        if material == "Plastic":
            scores["THERMOFORMING"] = scores.get("THERMOFORMING", 0) - 1
        keyword_matches.append("THERMOFORMING")
    elif len(thermo_matched) == 1:
        scores["THERMOFORMING"] = scores.get("THERMOFORMING", 0) + 1
        keyword_matches.append("THERMOFORMING")
    # COMPRESSION_MOLDING keyword scoring: ≥2 keywords → +3, exactly 1 → +1
    comp_matched = [kw for kw in COMPRESSION_KW if kw in text]
    if len(comp_matched) >= 2:
        scores["COMPRESSION_MOLDING"] = scores.get("COMPRESSION_MOLDING", 0) + 3
        keyword_matches.append("COMPRESSION_MOLDING")
    elif len(comp_matched) == 1:
        scores["COMPRESSION_MOLDING"] = scores.get("COMPRESSION_MOLDING", 0) + 1
        keyword_matches.append("COMPRESSION_MOLDING")

    # Geometry triggers for extrusion: thin wall + medium/large (profile-like)
    if min_wall_thickness == "Thin" and part_size in ("Medium", "Large") and feature_variety in ("Low", "Medium"):
        scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + 1

    # Geometry triggers for MIM: small + high feature variety OR small + thin walls
    # These triggers indicate MIM suitability, so metal boost can apply
    mim_has_geo_trigger = False
    if part_size == "Small" and feature_variety == "High":
        scores["MIM"] = scores.get("MIM", 0) + 1
        mim_has_geo_trigger = True
    if part_size == "Small" and min_wall_thickness == "Thin":
        scores["MIM"] = scores.get("MIM", 0) + 1
        mim_has_geo_trigger = True
    # Negative: very large parts
    if part_size == "Large" and material in ("Steel", "Aluminum"):
        scores["MIM"] = scores.get("MIM", 0) - 1
    
    # Add metal boost ONLY if MIM-specific signals present (keywords OR geometry triggers)
    if (has_mim_keyword_signal or mim_has_geo_trigger) and material in ("Steel", "Aluminum"):
        scores["MIM"] = scores.get("MIM", 0) + 3

    # Metal + thin + medium/large = sheet-metal-like geometry (bins-mode restore)
    if material in ("Steel", "Aluminum") and min_wall_thickness == "Thin" and part_size in ("Medium", "Large"):
        scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) + 3
        all_reasons.append("Metal thin-sheet geometry favors sheet metal forming")

    # CAD Lite + sheet-metal likelihood (bins-mode: when cad_status != ok but STEP uploaded)
    cad_status = cad_analysis_status(state)
    cad_lite_result: dict | None = None
    extrusion_lite_result: dict | None = None
    extrusion_likelihood_result: dict | None = None
    turning_lite_result: dict | None = None
    turning_likelihood_result: dict | None = None
    likelihood: str = "low"
    likelihood_source: str = "none"
    ext_level: str = "none"
    turn_level: str = "none"
    am_likelihood_level: str = "low"
    am_likelihood_source: str = "bins_only"
    # Sheet metal evidence flags (for AUTO mode tie-breaks)
    strong_sheet_evidence: bool = False
    ok_sheet_evidence: bool = False
    # Extrusion geometry metrics (for AUTO mode tie-breaks)
    ext_axis_ratio: float | None = None
    ext_cv: float | str = "?"
    if cad_uploaded(state) and cad_status != "ok":
        step_path = state.get("step_path")
        if step_path:
            cad_lite_result = run_cad_lite(str(step_path))
            state_with_cad = {**state, "cad_lite": cad_lite_result}
            # Bbox fallback when cad_lite fails (cheap thinness proxy for SM2)
            if cad_lite_result.get("status") != "ok":
                bbox_fb = get_bbox_only(str(step_path))
                if bbox_fb:
                    state_with_cad = {**state_with_cad, "bbox_fallback": bbox_fb}
            likelihood, likelihood_source, thinness_bbox = sheet_metal_likelihood(state_with_cad)
            if cad_lite_result.get("status") == "ok":
                trace.append(
                    f"process_selection: cad_lite status=ok t_est={cad_lite_result.get('t_est')} "
                    f"av_ratio={cad_lite_result.get('av_ratio')} t_over_min_dim={cad_lite_result.get('t_over_min_dim')}"
                )
            else:
                trace.append(f"process_selection: cad_lite status={cad_lite_result.get('status', 'failed')}")
            thin_str = f" thinness_bbox={thinness_bbox}" if thinness_bbox is not None else ""
            # Add flatness info if available from cad_lite
            flatness_info = ""
            a_sm, b_sm, c_sm = None, None, None
            flatness, thinness = None, None
            if cad_lite_result and cad_lite_result.get("status") == "ok" and cad_lite_result.get("bbox_dims"):
                bbox_dims_sm = cad_lite_result.get("bbox_dims")
                if bbox_dims_sm and len(bbox_dims_sm) >= 3:
                    dims_sorted_desc = sorted(bbox_dims_sm, reverse=True)
                    a_sm, b_sm, c_sm = dims_sorted_desc[0], dims_sorted_desc[1], dims_sorted_desc[2]
                    if b_sm > 1e-6:
                        flatness = c_sm / b_sm
                        thinness = c_sm / a_sm if a_sm > 1e-6 else None
                        flatness_info = f" flatness={flatness:.3f}"
                        if thinness is not None:
                            flatness_info += f" thinness={thinness:.3f}"
            a_str = f"{a_sm:.1f}" if a_sm is not None else "N/A"
            b_str = f"{b_sm:.1f}" if b_sm is not None else "N/A"
            c_str = f"{c_sm:.1f}" if c_sm is not None else "N/A"
            trace.append(f"process_selection: sheet_metal_likelihood={likelihood} (source={likelihood_source}){thin_str}{flatness_info} [sheet_metal_lite: a={a_str} b={b_str} c={c_str} level={likelihood}]")
            
            # Detect strong sheet metal evidence from geometry (for AUTO mode upgrade)
            # Gate using t_over_min_dim to prevent blocky parts (e.g., CNC2) from being mistaken for sheet metal
            # t_over_min_dim <= 0.05 indicates thin sheet-like geometry; higher values indicate thicker/blockier parts
            t_over_min_dim = cad_lite_result.get("t_over_min_dim") if cad_lite_result and cad_lite_result.get("status") == "ok" else None
            is_sheet_thin = (t_over_min_dim is not None) and (t_over_min_dim <= 0.05)
            strong_sheet_evidence = False
            ok_sheet_evidence = False
            if flatness is not None and thinness is not None:
                # strong_sheet: very flat and thin (strong sheet metal geometry) AND must pass thickness gate
                strong_sheet_evidence = is_sheet_thin and (flatness >= 0.90 and thinness >= 0.60)
                # ok_sheet: reasonably flat and thin (good sheet metal geometry) AND must pass thickness gate
                ok_sheet_evidence = is_sheet_thin and (flatness >= 0.60 and thinness >= 0.40)
                if strong_sheet_evidence:
                    trace.append(f"process_selection: strong sheet metal evidence detected (flatness={flatness:.3f} >= 0.90, thinness={thinness:.3f} >= 0.60, t_over_min_dim={t_over_min_dim:.4f} <= 0.05)")
                elif ok_sheet_evidence:
                    trace.append(f"process_selection: ok sheet metal evidence detected (flatness={flatness:.3f} >= 0.60, thinness={thinness:.3f} >= 0.40, t_over_min_dim={t_over_min_dim:.4f} <= 0.05)")
                elif not is_sheet_thin and (flatness >= 0.60 or thinness >= 0.40):
                    # Log when geometry suggests sheet but thickness gate fails (prevents false positives like CNC2)
                    trace.append(f"process_selection: sheet-like geometry detected but thickness gate failed (t_over_min_dim={t_over_min_dim:.4f} > 0.05, not sheet metal)")
            # Extrusion Lite + extrusion likelihood
            extrusion_lite_result = run_extrusion_lite(str(step_path))
            state_with_cad = {**state_with_cad, "extrusion_lite": extrusion_lite_result}
            # Extrusion Lite + extrusion likelihood (compute before sheet metal capping)
            ext_lh = extrusion_likelihood(state_with_cad)
            extrusion_likelihood_result = ext_lh
            ext_level = ext_lh.get("level", "none")
            
            # Cap sheet_metal_likelihood when extrusion_lite times out (avoid false SHEET_METAL picks)
            # Only cap if extrusion evidence is UNKNOWN (timeout), not if it's LOW (which is valid)
            if extrusion_lite_result and extrusion_lite_result.get("status") == "timeout":
                if likelihood == "high" and ext_level == "none":
                    # Extrusion timeout means we can't rule out extrusion, so cap sheet metal
                    likelihood = "med"
                    likelihood_source = f"{likelihood_source}_capped_extrusion_timeout"
                    trace.append("process_selection: sheet_metal_likelihood capped to med (extrusion_lite timeout, extrusion unknown)")
            # AUTO mode: cap sheet_metal_likelihood to "med" if only thinness drives it (no explicit sheet evidence)
            if user_process_raw == "AUTO" and likelihood == "high" and likelihood_source in ("bbox_fallback", "bins_only"):
                likelihood = "med"
                likelihood_source = f"{likelihood_source}_capped_auto"
                trace.append("process_selection: AUTO mode - sheet_metal_likelihood capped to med (only thinness evidence)")
            # Turning Lite + turning likelihood
            turning_lite_result = run_turning_lite(str(step_path))
            state_with_cad = {**state_with_cad, "turning_lite": turning_lite_result}
            turn_lh = turning_likelihood(state_with_cad)
            turning_likelihood_result = turn_lh
            turn_level = turn_lh.get("level", "none")
            if turn_level != "none":
                turn_roundness = turning_lite_result.get("roundness") if turning_lite_result else None
                turn_slenderness = turning_lite_result.get("slenderness") if turning_lite_result else None
                turn_dims = turning_lite_result.get("bbox_dims") if turning_lite_result else None
                roundness_str = f"{turn_roundness:.3f}" if turn_roundness is not None else "N/A"
                slenderness_str = f"{turn_slenderness:.3f}" if turn_slenderness is not None else "N/A"
                if turn_dims and len(turn_dims) >= 3:
                    dims_sorted_desc = sorted(turn_dims, reverse=True)
                    a_turn, b_turn, c_turn = dims_sorted_desc[0], dims_sorted_desc[1], dims_sorted_desc[2]
                    trace.append(f"process_selection: turning_likelihood={turn_level} [turning_lite: a={a_turn:.1f} b={b_turn:.1f} c={c_turn:.1f} roundness={roundness_str} slenderness={slenderness_str} level={turn_level}]")
                else:
                    trace.append(f"process_selection: turning_likelihood={turn_level} roundness={roundness_str} slenderness={slenderness_str} (source={turn_lh.get('source', '?')})")
            else:
                trace.append(f"process_selection: turning_likelihood=none")
            # Bbox-based long_profile hint: upgrade ext_level by one (none->low, low->med, med->high)
            long_profile = False
            bbox_dims = extrusion_lite_result.get("bbox_dims") if extrusion_lite_result else None
            if not bbox_dims and state_with_cad.get("bbox_fallback"):
                bbox_dims = state_with_cad["bbox_fallback"].get("bbox_dims")
            if bbox_dims and len(bbox_dims) >= 3:
                dims_sorted = sorted(bbox_dims, reverse=True)
                max_dim, mid_dim, min_dim = dims_sorted[0], dims_sorted[1], dims_sorted[2]
                long_profile = (max_dim / max(1e-6, mid_dim) >= 3.0) and (max_dim / max(1e-6, min_dim) >= 6.0)
                if long_profile and ext_level != "high":
                    prev = ext_level
                    ext_level = "low" if ext_level == "none" else ("med" if ext_level == "low" else "high")
                    if ext_level != prev:
                        extrusion_likelihood_result = {**ext_lh, "level": ext_level, "long_profile_upgrade": True}
                        trace.append(f"process_selection: long_profile upgrade extrusion_likelihood {prev} -> {ext_level}")
            ext_cv = ext_lh.get('coeff_var', '?')
            ext_axis = ext_lh.get('axis', '?')
            ext_axis_ratio = ext_lh.get('axis_ratio')
            ext_status = extrusion_lite_result.get("status", "unknown") if extrusion_lite_result else "none"
            axis_ratio_str = f"{ext_axis_ratio:.3f}" if ext_axis_ratio is not None else "N/A"
            trace.append(f"process_selection: extrusion_likelihood={ext_level} coeff_var={ext_cv} axis={ext_axis} axis_ratio={axis_ratio_str} (extrusion_lite status={ext_status})")
            # If extrusion_lite timed out, treat extrusion likelihood as UNKNOWN (not LOW)
            # This prevents false classification flips when extrusion analysis fails
            if ext_status == "timeout" and ext_level == "none":
                trace.append("process_selection: extrusion_lite timeout - treating extrusion as UNKNOWN (not LOW) to prevent false classification")
            # Turning guard: do not boost extrusion when user confirmed turning or selected CNC_TURNING
            turning_confirmed = bool(
                conf_inputs and (
                    conf_inputs.get("turning_support_confirmed", False)
                    if isinstance(conf_inputs, dict)
                    else getattr(conf_inputs, "turning_support_confirmed", False)
                )
            )
            
            # Enhanced extrusion scoring: use coeff_var directly if available
            extr_cv = None
            if extrusion_lite_result and extrusion_lite_result.get("status") == "ok":
                extr_cv = extrusion_lite_result.get("coeff_var")
                if extr_cv is not None:
                    # Compute extrusion level from CV
                    computed_extr_level = _extrusion_level_from_cv(extr_cv)
                    # Use computed level if better than ext_level from extrusion_likelihood
                    if computed_extr_level != "none":
                        ext_level = computed_extr_level
            
            # Only apply extrusion boost if extrusion_lite didn't timeout (timeout = UNKNOWN, not LOW)
            extrusion_known = (
                extrusion_lite_result is None
                or extrusion_lite_result.get("status") != "timeout"
            )
            apply_extrusion_boost = (
                ext_level in ("high", "med", "low")
                and material in ("Steel", "Aluminum")
                and "EXTRUSION" in eligible_processes
                and not turning_confirmed
                and user_process != "CNC_TURNING"
                and extrusion_known  # Don't boost if extrusion analysis timed out
            )
            if not extrusion_known and ext_level == "none":
                trace.append("process_selection: skipping extrusion boost (extrusion_lite timeout, extrusion unknown)")
            if "EXTRUSION" in eligible_processes:
                scores.setdefault("EXTRUSION", 0)
            if apply_extrusion_boost:
                # New bonus structure: HIGH +8, MED +6, LOW +2
                boost = {"high": 8, "med": 6, "low": 2}.get(ext_level, 0)
                if boost:
                    # AUTO mode: detect strong extrusion geometry (high axis_ratio + good coeff_var)
                    # This helps EDGE2 extrusion cases where geometry strongly indicates extrusion
                    strong_extrusion_geometry = (
                        ext_level in ("med", "high")
                        and ext_axis_ratio is not None and ext_axis_ratio >= 3.0
                        and ext_cv != "?" and isinstance(ext_cv, (int, float)) and ext_cv >= 0.30
                        and turn_level == "none"
                        and not ok_sheet_evidence
                    )
                    
                    # AUTO mode + Steel + non-Production: apply penalty to prevent EXTRUSION from winning
                    # BUT reduce penalty if strong_extrusion_geometry is detected (allows EDGE2 to win)
                    if is_auto_mode and material == "Steel" and production_volume != "Production":
                        penalty = -5 if ext_level == "high" else (-4 if ext_level == "med" else -2)
                        if strong_extrusion_geometry:
                            # Reduce penalty by 3 for strong extrusion geometry (helps EDGE2)
                            penalty = penalty + 3
                            trace.append(f"process_selection: AUTO Steel non-Production EXTRUSION penalty reduced due to strong geometry (penalty={penalty}, axis_ratio={ext_axis_ratio:.3f} >= 3.0, coeff_var={ext_cv:.3f} >= 0.30)")
                        boost = boost + penalty
                        trace.append(f"process_selection: AUTO Steel non-Production EXTRUSION penalty {penalty} (final boost={boost})")
                    elif is_auto_mode and strong_extrusion_geometry:
                        # AUTO mode: add extra boost for strong extrusion geometry (non-Steel or Production cases)
                        boost = boost + 3
                        trace.append(f"process_selection: AUTO strong extrusion geometry boost +3 (axis_ratio={ext_axis_ratio:.3f} >= 3.0, coeff_var={ext_cv:.3f} >= 0.30)")
                    
                    scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + boost
                    if ext_level == "high":
                        scores["CNC"] = scores.get("CNC", 0) - 1
                        all_reasons.append("Extrusion Lite geometry indicates strong constant-section signal")
                
                # Slenderness bonus: axis length / transverse width
                if bbox_dims and len(bbox_dims) >= 3:
                    dims_sorted = sorted(bbox_dims, reverse=True)
                    axis_length = dims_sorted[0]
                    transverse_width = dims_sorted[1] if len(dims_sorted) > 1 else dims_sorted[0]
                    if transverse_width > 1e-6:
                        slenderness_ratio = axis_length / transverse_width
                        if slenderness_ratio >= 10:
                            scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + 1
                            trace.append(f"process_selection: slenderness bonus +1 (ratio={slenderness_ratio:.2f})")
                        elif slenderness_ratio >= 6:
                            scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + 2
                            trace.append(f"process_selection: slenderness bonus +2 (ratio={slenderness_ratio:.2f})")
                
                trace.append(f"extrusion_score adjusted: level={ext_level} score={scores.get('EXTRUSION', 0)}")
        
        # Turning Lite boost: if turning_likelihood is high/med, strongly prefer CNC_TURNING over CNC
        # In AUTO mode: apply stronger boost to ensure CNC_TURNING wins
        if turn_level in ("high", "med") and "CNC_TURNING" in eligible_processes:
            if turn_level == "high":
                boost = 10 if is_auto_mode else 8
                scores["CNC_TURNING"] = scores.get("CNC_TURNING", 0) + boost
                if "CNC" in scores:
                    penalty = -3 if is_auto_mode else -2
                    scores["CNC"] = scores.get("CNC", 0) + penalty
                all_reasons.append("Turning Lite geometry indicates strong lathe-like signal")
                trace.append(f"process_selection: turning_likelihood high boost CNC_TURNING +{boost} CNC {penalty}")
            elif turn_level == "med":
                boost = 7 if is_auto_mode else 5
                scores["CNC_TURNING"] = scores.get("CNC_TURNING", 0) + boost
                if "CNC" in scores:
                    penalty = -2 if is_auto_mode else -1
                    scores["CNC"] = scores.get("CNC", 0) + penalty
                all_reasons.append("Turning Lite geometry indicates lathe-like signal")
                trace.append(f"process_selection: turning_likelihood med boost CNC_TURNING +{boost} CNC {penalty}")
        
        # Legacy bins: apply likelihood-based score deltas for metal
        if material in ("Steel", "Aluminum"):
            # AUTO mode: upgrade likelihood to "high" if strong sheet metal evidence detected
            effective_likelihood = likelihood
            if is_auto_mode and likelihood == "med":
                # Check for strong sheet metal evidence (computed earlier from flatness/thinness)
                if cad_lite_result and cad_lite_result.get("status") == "ok":
                    bbox_dims_check = cad_lite_result.get("bbox_dims")
                    if bbox_dims_check and len(bbox_dims_check) >= 3:
                        dims_sorted_desc = sorted(bbox_dims_check, reverse=True)
                        a_check, b_check, c_check = dims_sorted_desc[0], dims_sorted_desc[1], dims_sorted_desc[2]
                        if b_check > 1e-6 and a_check > 1e-6:
                            flatness_check = c_check / b_check
                            thinness_check = c_check / a_check
                            strong_sheet = (flatness_check >= 0.90 and thinness_check >= 0.60)
                            if strong_sheet:
                                effective_likelihood = "high"
                                trace.append(f"process_selection: AUTO mode - upgraded sheet_metal_likelihood med->high (strong evidence: flatness={flatness_check:.3f} >= 0.90, thinness={thinness_check:.3f} >= 0.60)")
            
            # Adaptive sheet metal boost (geometry-driven; no blind +5 to avoid extrusion/CNC imbalance)
            if effective_likelihood == "high":
                boost = 6 if is_auto_mode else 6  # strong geometry
                scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) + boost
                scores["CNC"] = scores.get("CNC", 0) - 2
                all_reasons.append("CAD Lite geometry indicates strong sheet-metal signal")
                trace.append(f"process_selection: AUTO mode - SHEET_METAL HIGH boost +{boost} (geometry-driven)")
            elif effective_likelihood == "med":
                if is_auto_mode and cad_lite_result and cad_lite_result.get("status") == "ok":
                    bbox_dims_med = cad_lite_result.get("bbox_dims")
                    t_over_min_med = cad_lite_result.get("t_over_min_dim")
                    flat_m, thin_m = None, None
                    if bbox_dims_med and len(bbox_dims_med) >= 3:
                        dims_sorted = sorted(bbox_dims_med, reverse=True)
                        a_m, b_m, c_m = dims_sorted[0], dims_sorted[1], dims_sorted[2]
                        if b_m > 1e-6 and a_m > 1e-6:
                            flat_m = c_m / b_m
                            thin_m = c_m / a_m
                    # Adaptive: thin plate → 5; moderately flat → 4; weak → 3
                    if t_over_min_med is not None and t_over_min_med <= 0.05:
                        boost = 5  # thin plate, strong evidence
                    elif flat_m is not None and flat_m >= 0.4:
                        boost = 4  # moderately flat part
                    else:
                        boost = 3  # weak sheet evidence
                else:
                    boost = 5 if is_auto_mode else 3
                scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) + boost
                trace.append(f"process_selection: AUTO sheet boost adaptive: {boost}")
                # AUTO mode: only cap if flatness gate failed AND not strong/ok sheet evidence (prevents impeller, but allows real sheet metal)
                if is_auto_mode:
                    # Check if flatness gate passed (if cad_lite available)
                    flatness_gate_passed = True
                    has_strong_or_ok_sheet = False
                    if cad_lite_result and cad_lite_result.get("status") == "ok":
                        bbox_dims_check = cad_lite_result.get("bbox_dims")
                        if bbox_dims_check and len(bbox_dims_check) >= 3:
                            dims_sorted_desc = sorted(bbox_dims_check, reverse=True)
                            a_check, b_check, c_check = dims_sorted_desc[0], dims_sorted_desc[1], dims_sorted_desc[2]
                            if b_check > 1e-6 and a_check > 1e-6:
                                flatness_check = c_check / b_check
                                thinness_check = c_check / a_check
                                flatness_gate_passed = (flatness_check <= 0.60 and thinness_check <= 0.20)
                                # Check for strong/ok sheet evidence
                                strong_sheet = (flatness_check >= 0.90 and thinness_check >= 0.60)
                                ok_sheet = (flatness_check >= 0.60 and thinness_check >= 0.40)
                                has_strong_or_ok_sheet = strong_sheet or ok_sheet
                    # Only cap if flatness gate failed AND no strong/ok sheet evidence
                    if not flatness_gate_passed and not has_strong_or_ok_sheet:
                        # Flatness gate failed - cap to prevent impeller misclassification
                        cnc_score_before = scores.get("CNC", 0)
                        sheet_score = scores.get("SHEET_METAL", 0)
                        max_sheet_score = max(0, cnc_score_before - 1)
                        if sheet_score > max_sheet_score:
                            scores["SHEET_METAL"] = max_sheet_score
                            trace.append(f"process_selection: AUTO mode - capped SHEET_METAL score from {sheet_score} to {max_sheet_score} (flatness gate failed, prevents impeller)")
                    elif has_strong_or_ok_sheet:
                        trace.append(f"process_selection: AUTO mode - NOT capping SHEET_METAL (strong/ok sheet evidence present)")

            # CNC tie guard: prevent CNC dominance on borderline sheet parts when scores are within 1
            if is_auto_mode and likelihood in ("med", "high") and "SHEET_METAL" in scores and "CNC" in scores:
                t_guard = cad_lite_result.get("t_over_min_dim") if cad_lite_result and cad_lite_result.get("status") == "ok" else None
                if t_guard is not None and t_guard <= 0.06:
                    cnc_s = scores.get("CNC", 0)
                    sm_s = scores.get("SHEET_METAL", 0)
                    if abs(cnc_s - sm_s) <= 1:
                        scores["SHEET_METAL"] = sm_s + 1
                        trace.append("process_selection: AUTO sheet tie guard applied")

    # Bins-mode deterministic heuristics (legacy_bins only)
    if cad_status != "ok":
        # FIX A — AM likelihood boost
        if cad_lite_result and cad_lite_result.get("am_likelihood_level"):
            am_likelihood_level = cad_lite_result.get("am_likelihood_level", "low")
            am_likelihood_source = "cad_lite"
        else:
            if (
                feature_variety == "High"
                and accessibility_risk in ("High", "Medium")
                and min_internal_radius == "Small"
            ):
                am_likelihood_level = "med"
            else:
                am_likelihood_level = "low"
            am_likelihood_source = "bins_only"
        trace.append(f"process_selection: am_likelihood={am_likelihood_level} (source={am_likelihood_source})")
        if "AM" in eligible_processes:
            if am_likelihood_level == "high":
                scores["AM"] = scores.get("AM", 0) + 5
                trace.append("process_selection: bins_boost AM +5")
            elif am_likelihood_level == "med":
                scores["AM"] = scores.get("AM", 0) + 3
                trace.append("process_selection: bins_boost AM +3")
            if am_likelihood_level in ("high", "med") and scores.get("CNC", 0) >= scores.get("AM", 0):
                scores["CNC"] = min(scores.get("CNC", 0), scores.get("AM", 0) - 1)

        # FIX B — MIM penalty when extrusion_likelihood high/med (EXTRUSION boost already in step_path)
        if ext_level in ("high", "med") and "EXTRUSION" in eligible_processes:
            if ext_level == "high":
                if "MIM" in eligible_processes and "MIM" in scores:
                    scores["MIM"] = scores.get("MIM", 0) - 6
                trace.append("process_selection: bins_boost EXTRUSION high +5; bins_penalize MIM -6")
            elif ext_level == "med":
                if "MIM" in eligible_processes and "MIM" in scores:
                    scores["MIM"] = scores.get("MIM", 0) - 3
                trace.append("process_selection: bins_boost EXTRUSION med +3; bins_penalize MIM -3")

        # Strong extrusion geometry override: boost EXTRUSION primary when geometry strongly matches
        if "EXTRUSION" in eligible_processes:
            is_strong_extrusion = _strong_extrusion(extrusion_lite_result, cad_lite_result)
            if is_strong_extrusion:
                # Strong boost for production volume (die ROI OK), moderate for proto
                if production_volume == "Production":
                    boost = 10
                elif production_volume == "Proto":
                    boost = 6
                else:
                    boost = 10  # Small batch also gets strong boost
                
                scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + boost
                scores["CNC"] = scores.get("CNC", 0) + 3  # CNC finishing
                if "CASTING" in scores:
                    scores["CASTING"] = scores.get("CASTING", 0) - 2  # Penalize casting for profile-like geometry
                trace.append(f"process_selection: strong_extrusion boost EXTRUSION +{boost} CNC +3 CASTING -2")

        # Bins-only extrusion fallback: Aluminum + extrusion-like geometry when ext_level low
        if (
            ext_level not in ("high", "med")
            and material == "Aluminum"
            and "EXTRUSION" in eligible_processes
            and min_wall_thickness == "Thin"
            and part_size in ("Medium", "Large")
            and feature_variety in ("Low", "Medium")
        ):
            scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + 5
            scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) - 2
            if "MIM" in eligible_processes and "MIM" in scores:
                scores["MIM"] = scores.get("MIM", 0) - 4
            trace.append("process_selection: bins_boost EXTRUSION fallback (thin+Al) +5; SM -2; MIM -4")

        # FIX C — Material realism: MIM cap for Aluminum
        if material == "Aluminum" and "MIM" in scores:
            if ext_level in ("high", "med"):
                scores["MIM"] = min(scores.get("MIM", 0), -2)
            else:
                scores["MIM"] = min(scores.get("MIM", 0), 0)
            trace.append("process_selection: bins_guard MIM cap for Aluminum")

        # FIX D — Sheet metal bins-only boost when cad_lite fails (Steel only; Aluminum thin can be extrusion)
        if (
            material == "Steel"
            and min_wall_thickness == "Thin"
            and part_size in ("Medium", "Large")
        ):
            scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) + 4
            if "CNC" in scores:
                scores["CNC"] = scores.get("CNC", 0) - 1
            trace.append("process_selection: bins_boost SHEET_METAL thin+metal +4")
        
        # AUTO mode: Ensure INJECTION_MOLDING wins over THERMOFORMING for Plastic + Production
        if is_auto_mode and material == "Plastic" and production_volume == "Production":
            im_score = scores.get("INJECTION_MOLDING", 0)
            thermo_score = scores.get("THERMOFORMING", 0)
            if thermo_score > im_score:
                # Boost INJECTION_MOLDING to ensure it wins
                boost = thermo_score - im_score + 2
                scores["INJECTION_MOLDING"] = im_score + boost
                trace.append(f"process_selection: AUTO mode - boosted INJECTION_MOLDING +{boost} over THERMOFORMING (Plastic+Production)")

    # THERMOFORMING size gate: allow only when part_size == Large or (CAD with max(bbox) >= 250mm)
    if "THERMOFORMING" in eligible_processes and material == "Plastic" and part_size != "Large":
        allow = False
        if cad_lite_result and cad_lite_result.get("status") == "ok":
            bbox = cad_lite_result.get("bbox_dims") or (extrusion_lite_result or {}).get("bbox_dims")
            if bbox and len(bbox) >= 3:
                allow = max(bbox) >= 250.0
        if not allow:
            gates["THERMOFORMING"] = {"eligible": False, "reason": "size gate (thermoforming)"}
            eligible_processes = [p for p in eligible_processes if p != "THERMOFORMING"]
            gated_out = [p for p in CANDIDATES if not gates.get(p, {}).get("eligible", True)]
            trace.append("process_selection: THERMOFORMING gated (size gate)")

    # Apply gating: ineligible processes get zero score (excluded from ranking)
    for p in CANDIDATES:
        if not gates.get(p, {}).get("eligible", True):
            scores[p] = -100  # Ensure they never win

    # Geometry trigger for THERMOFORMING already handled in _score_thermoforming() (+2)
    # No duplicate trigger here
    # Negative signals for THERMOFORMING
    if any(kw in text for kw in ("tight tolerance everywhere", "two-sided detail", "internal bosses everywhere", "precision both sides")):
        scores["THERMOFORMING"] = scores.get("THERMOFORMING", 0) - 2
        all_reasons.append("Tight tolerance / two-sided detail conflicts with thermoforming limitations")

    # Negative signals for COMPRESSION_MOLDING
    if any(kw in text for kw in ("thin sheet", "vacuum formed", "thermoformed", "thermoforming")):
        scores["COMPRESSION_MOLDING"] = scores.get("COMPRESSION_MOLDING", 0) - 2
        all_reasons.append("Thermoforming-style thin sheet conflicts with compression molding")
    if any(kw in text for kw in ("thermoplastic injection", "high detail small part", "many small bosses")):
        scores["COMPRESSION_MOLDING"] = scores.get("COMPRESSION_MOLDING", 0) - 1

    # Conflict dampener: IM keywords + non-Production volume
    if _has_any(text, IM_KW) and production_volume != "Production":
        scores["INJECTION_MOLDING"] -= 1
    
    # Add keyword-based reasons
    if _has_any(text, IM_KW):
        all_reasons.append("User notes mention molding-specific concerns (draft/gating/ejection).")
    if _has_any(text, SM_KW):
        all_reasons.append("User notes mention sheet-metal features (bends/flanges/flat pattern).")
    if _has_any(text, AM_KW):
        all_reasons.append("User notes mention AM constraints (supports/orientation/overhangs).")
    if _has_any(text, FORG_KW):
        all_reasons.append("User notes mention forging concerns (draft/parting line/flash/grain flow).")
    if _has_any(text, EXTR_KW):
        all_reasons.append("User notes mention extrusion concerns (profile/rail/channel/constant cross-section).")
    # MIM keyword cluster detection
    mim_matched = [kw for kw in MIM_KW if kw in text]
    metal_kws = {"metal", "stainless", "17-4", "17-4ph", "316l"}
    process_kws = {"sinter", "sintering", "debinding", "powder", "feedstock", "binder"}
    has_metal = any(kw in text for kw in metal_kws)
    has_process = any(kw in text for kw in process_kws)
    has_mim_keyword_signal = len(mim_matched) >= 2 or (has_metal and has_process) or len(mim_matched) == 1
    # Check geometry triggers for MIM
    mim_has_geo_trigger = (part_size == "Small" and feature_variety in ("Medium", "High")) or (part_size == "Small" and min_wall_thickness == "Thin")
    # Only add MIM reasons if MIM-specific signals present (keywords or geometry triggers)
    mim_score = scores.get("MIM", 0)
    if has_mim_keyword_signal or mim_has_geo_trigger:
        if len(mim_matched) >= 2 or (has_metal and has_process):
            all_reasons.append("MIM keyword cluster detected (powder/sintering/debinding/small complex metal part).")
        elif len(mim_matched) == 1:
            all_reasons.append("User notes mention MIM concerns (powder/sintering/debinding/small complex metal part).")
        # Only add metal reason if MIM signals present AND metal material AND MIM score > 0
        if (has_mim_keyword_signal or mim_has_geo_trigger) and material in ("Steel", "Aluminum") and mim_score > 0:
            all_reasons.append("Metal material with MIM-specific signals favors MIM")
    # THERMOFORMING keyword cluster detection
    thermo_matched = [kw for kw in THERMOFORMING_KW if kw in text]
    has_thermo_cluster = len(thermo_matched) >= 2
    has_thermo_geometry = part_size in ("Medium", "Large") and feature_variety in ("Low", "Medium")
    if has_thermo_cluster:
        all_reasons.append("Thermoforming keyword cluster detected (vacuum forming/sheet forming/plug assist/trimming).")
        # Only mention plastic if combined with thermoforming indicators
        if material == "Plastic":
            all_reasons.append("Plastic sheet-formed signal")
    elif len(thermo_matched) == 1:
        all_reasons.append("User notes mention thermoforming concerns (vacuum forming/sheet forming/trimming).")
    elif has_thermo_geometry and material == "Plastic":
        # Geometry + plastic signal (no keywords)
        all_reasons.append("Plastic sheet-formed profile signal")
    # COMPRESSION_MOLDING keyword cluster detection
    comp_matched = [kw for kw in COMPRESSION_KW if kw in text]
    if len(comp_matched) >= 2:
        all_reasons.append("Compression molding keyword cluster detected (thermoset/composite/press-cure).")
        all_reasons.append("Thermoset/composite press-cure signal")
    elif len(comp_matched) == 1:
        all_reasons.append("User notes mention compression molding concerns (thermoset/composite/cure).")

    # Scorer path routing: legacy_bins when cad_status != ok; numeric when cad_status == ok
    cad_status = cad_analysis_status(state)
    scorer_path = "legacy_bins" if cad_status != "ok" else "numeric"
    trace.append(f"process_selection: scorer_path={scorer_path} cad_status={cad_status}")

    # Score snapshot for debugging (before final primary selection)
    trace.append(
        f"PSI: scores_snapshot: CNC={scores.get('CNC', 0)}, SHEET_METAL={scores.get('SHEET_METAL', 0)}, EXTRUSION={scores.get('EXTRUSION', 0)}, AM={scores.get('AM', 0)}, CNC_TURNING={scores.get('CNC_TURNING', 0)}, IM={scores.get('INJECTION_MOLDING', 0)}"
    )
    # Primary: highest score among ELIGIBLE only; tie-break prefer user's process (if not AUTO).
    # TODO (portfolio): Production uses additional tie-break rules (margin thresholds,
    # user-intent anchor when CAD unavailable, hybrid extrusion/CNC overrides).
    sorted_by_score = sorted(
        eligible_processes,
        key=lambda p: (scores.get(p, 0), 1 if user_process and p == user_process else 0),
        reverse=True,
    )
    primary = sorted_by_score[0] if sorted_by_score else "CNC"
    primary_score = scores.get(primary, 0)
    
    # AUTO mode: prevent SHEET_METAL from becoming primary only when margin is below threshold (score-aware)
    # Allow SHEET_METAL when likelihood is "high" OR strong sheet evidence OR when SHEET_METAL wins by clear margin
    SHEET_PRIMARY_MARGIN = 2  # points
    sheet_primary_prevented = False  # set True when we force primary away from SHEET_METAL (borderline)
    raw_best_process: str | None = None
    raw_best_score = 0
    raw_second_process: str | None = None
    raw_second_score = 0
    forced_reason: str | None = None
    if user_process_raw == "AUTO" and primary == "SHEET_METAL" and likelihood != "high":
        has_strong_sheet_evidence = strong_sheet_evidence or ok_sheet_evidence
        cnc_sc = scores.get("CNC", 0)
        sm_sc = scores.get("SHEET_METAL", 0)
        margin = sm_sc - cnc_sc  # >= 0 when primary is SHEET_METAL

        if not has_strong_sheet_evidence and margin < SHEET_PRIMARY_MARGIN:
            # Borderline: prevent and put SM in secondary
            raw_best_process = "SHEET_METAL"
            raw_best_score = sm_sc
            forced_reason = f"likelihood={likelihood}; no strong evidence; margin={margin} < threshold={SHEET_PRIMARY_MARGIN}"
            for p in sorted_by_score[1:]:
                if p != "SHEET_METAL":
                    primary = p
                    primary_score = scores.get(p, 0)
                    raw_second_process = p
                    raw_second_score = primary_score
                    sheet_primary_prevented = True
                    trace.append(f"process_selection: AUTO - prevented SHEET_METAL primary (wins by margin={margin}, below threshold={SHEET_PRIMARY_MARGIN})")
                    break
        else:
            if not has_strong_sheet_evidence:
                trace.append(f"process_selection: AUTO - allowed SHEET_METAL primary (wins by margin={margin}, likelihood=med)")
            else:
                trace.append(f"process_selection: AUTO mode - allowing SHEET_METAL primary (likelihood={likelihood}, strong/ok sheet evidence present)")
    
    # AUTO-only tie-break override for sheet metal: prefer SHEET_METAL when tied with CNC and ok_sheet evidence exists
    if user_process_raw == "AUTO" and primary == "CNC" and ok_sheet_evidence:
        sheet_metal_score = scores.get("SHEET_METAL", 0)
        if sheet_metal_score == primary_score:
            primary = "SHEET_METAL"
            primary_score = sheet_metal_score
            trace.append(f"process_selection: AUTO tie-break - choosing SHEET_METAL over CNC (scores tied at {primary_score}, ok_sheet evidence present)")

    # BINS-MODE USER INTENT ANCHOR: if cad_status != ok and user_selected is eligible,
    # favor user_selected when within margin of top score (skip if AUTO)
    selected_eligible = user_process is not None and user_process in eligible_processes
    if cad_status != "ok" and selected_eligible and user_process != primary:
        top_score = scores.get(sorted_by_score[0], 0) if sorted_by_score else 0
        user_score = scores.get(user_process, 0)
        BINS_ANCHOR_MARGIN = 2
        if (top_score - user_score) <= BINS_ANCHOR_MARGIN:
            primary = user_process
            primary_score = user_score
            trace.append(f"process_selection: bins_anchor applied selected={user_process} margin={BINS_ANCHOR_MARGIN} top_was={sorted_by_score[0] if sorted_by_score else '?'}")
    
    # Second-best and score_diff (recomputed after any override; used for trace and tie-aware secondary)
    second_process: str | None = None
    second_score = 0
    score_diff = 0
    # Stabilized tie-break policy with deterministic rules
    if len(sorted_by_score) >= 2:
        # Recompute second from actual scores (after prevention) so tie-break uses correct score_diff
        primary_score = scores.get(primary, 0)
        sorted_by_score_final = sorted(eligible_processes, key=lambda p: (scores.get(p, 0), 1 if user_process and p == user_process else 0), reverse=True)
        second_process = next((p for p in sorted_by_score_final if p != primary), None)
        second_score = scores.get(second_process, 0) if second_process else 0
        score_diff = primary_score - second_score
        # Tie-break policy (skip if AUTO - geometry-driven selection)
        if user_process is not None:
            # Check for strong mismatch signals
            am_score = scores.get("AM", 0)
            user_score = scores.get(user_process, 0)
            has_strong_am_signal = am_geom_hits >= 2
            has_material_mismatch = (
                (material == "Steel" and user_process == "INJECTION_MOLDING") or
                (material == "Aluminum" and user_process == "INJECTION_MOLDING") or
                (material == "Plastic" and user_process in {"FORGING", "CASTING"})
            )
            
            # Tie-break policy:
            # - score_diff <= 1: prefer user_selected if compatible AND no strong mismatch signals
            # - score_diff == 2: allow override only if mismatch signals are strong
            if score_diff <= 1:
                # Check if AM-only geometry override applies (strong signal)
                am_geom_override = (
                    has_strong_am_signal
                    and am_score >= user_score
                    and user_process in {"CNC", "CNC_TURNING"}
                )
                if am_geom_override:
                    # AM-only geometry signals are strong; let best score win (don't prefer user-selected CNC)
                    trace.append(f"PSI override: AM-only geometry signals strong (am_geom_hits={am_geom_hits}); skipping CNC tie-break")
                else:
                    # Check compatibility: user_selected must be compatible with material/volume
                    is_compatible = True
                    if has_material_mismatch:
                        is_compatible = False
                    elif user_process == "INJECTION_MOLDING" and material not in ("Plastic",):
                        is_compatible = False
                    elif user_process in {"FORGING", "CASTING"} and material == "Plastic":
                        is_compatible = False
                    
                    # Check if user_selected is in top2 and is a flexible process
                    top2_processes = {sorted_by_score[0], sorted_by_score[1]}
                    if (user_process in top2_processes 
                        and user_process in {"CNC", "AM", "CNC_TURNING"}
                        and is_compatible
                        and not has_strong_am_signal):
                        primary = user_process
                        primary_score = scores.get(primary, 0)
                        trace.append(f"PSI tie-break: prefer user-selected flexible process ({user_process}) when score_diff <= 1 (compatible, no strong mismatch)")
            elif score_diff == 2:
                # For score_diff == 2, only override if strong mismatch signals exist
                if has_strong_am_signal and am_score > user_score and user_process in {"CNC", "CNC_TURNING"}:
                    # Strong AM geometry signal overrides user selection even at score_diff == 2
                    # Check if AM is in top2 and user_selected is the primary
                    if primary == user_process:
                        am_idx = next((i for i, p in enumerate(sorted_by_score) if p == "AM"), None)
                        if am_idx is not None and am_idx < 2:  # AM is in top2
                            primary = "AM"
                            primary_score = am_score
                            trace.append(f"PSI override: strong AM geometry signal (am_geom_hits={am_geom_hits}) overrides user_selected at score_diff==2")
                elif has_material_mismatch:
                    # Material mismatch is strong enough to override at score_diff == 2
                    trace.append(f"PSI: material mismatch detected (material={material}, user_selected={user_process}), allowing primary={primary}")

    # Final recompute: primary may have changed in tie-break; second must reflect actual scores for trace and secondary
    primary_score = scores.get(primary, 0)
    sorted_by_score_final = sorted(eligible_processes, key=lambda p: (scores.get(p, 0), 1 if user_process and p == user_process else 0), reverse=True)
    second_process = next((p for p in sorted_by_score_final if p != primary), None)
    second_score = scores.get(second_process, 0) if second_process else 0
    score_diff = primary_score - second_score
    trace.append(f"PSI: score_diff={score_diff} (primary={primary}={primary_score}, second={second_process or 'none'}={second_score})")

    # Secondary: up to 2 highest-scoring non-primary ELIGIBLE processes within SECONDARY_DELTA points
    SECONDARY_DELTA = 3
    secondary: list[str] = []
    secondary_candidates = [
        p for p in eligible_processes
        if p != primary
        and scores.get(p, 0) > 0
        and abs(scores.get(p, 0) - primary_score) <= SECONDARY_DELTA
    ]
    # Sort by score descending, with tie-break for user's selected process (if not AUTO)
    secondary_candidates.sort(
        key=lambda p: (scores.get(p, 0), 1 if user_process and p == user_process else 0),
        reverse=True,
    )
    # SHEET_METAL secondary: legacy path allows geometry-based; numeric path requires keywords
    has_sm_kw = _has_any(text, SM_KW)
    has_sm_geometry = material in ("Steel", "Aluminum") and min_wall_thickness == "Thin" and part_size in ("Medium", "Large")
    if not has_sm_kw and not (scorer_path == "legacy_bins" and has_sm_geometry):
        secondary_candidates = [p for p in secondary_candidates if p != "SHEET_METAL"]
    
    # INJECTION_MOLDING guard: exclude IM from secondary if material is metal and no material-change signal
    metal_materials = {"Steel", "Aluminum"}
    material_change_signals = ["plastic ok", "material change ok", "polymer acceptable", "material change", "switch to plastic", "plastic material"]
    has_material_change_signal = any(signal in text.lower() for signal in material_change_signals)
    if material in metal_materials and not has_material_change_signal:
        secondary_candidates = [p for p in secondary_candidates if p != "INJECTION_MOLDING"]
    
    # Take up to 2
    secondary = secondary_candidates[:2]

    # When prevention happened (borderline SHEET_METAL), force SHEET_METAL into secondary
    if sheet_primary_prevented and "SHEET_METAL" not in secondary and "SHEET_METAL" in eligible_processes:
        secondary.append("SHEET_METAL")
        secondary = secondary[:2]
        trace.append("process_selection: AUTO - SHEET_METAL added to secondary (prevention was applied)")

    # AUTO tie-aware secondary: use recomputed second_process; when score_diff == 0, expose runner-up and add ambiguity note.
    if user_process_raw == "AUTO" and second_process is not None and second_score > 0:
        runner_up = second_process  # already the actual second-best by score
        # When score_diff == 0, always expose runner-up as secondary
        if score_diff == 0 and runner_up != primary:
            if runner_up not in secondary:
                secondary.append(runner_up)
                secondary = secondary[:2]  # Keep max 2
                trace.append(f"AUTO tie: exposing {runner_up} as secondary (scores tied at {primary_score})")
            # Add ambiguity recommendation (LOW, no RAG trigger)
            findings.append(Finding(
                id="AMBIG_TIE1",
                category="PROCESS_SELECTION",
                severity="LOW",
                title=f"Close call: {primary} vs {runner_up}",
                why_it_matters="Top scores tied. Review both processes before committing.",
                recommendation=f"Top scores tied. Review both {primary} and {runner_up} feasibility before finalizing process selection.",
            ))

    # Hybrid decision rule: EXTRUSION + CNC finishing (prefer HYBRID when extrusion needs finishing).
    # TODO (portfolio): Production uses additional hybrid process modeling rules here.
    extrusion_score = scores.get("EXTRUSION", 0)
    cnc_score = scores.get("CNC", 0)
    production_volume_lower = production_volume.lower() if production_volume else ""
    material_lower = material.lower() if material else ""
    
    # Prefer HYBRID when: extrusion signal exists but volume is not Production OR Steel material OR CNC competitive
    # In AUTO mode: be more aggressive about keeping CNC primary when extrusion needs finishing
    hybrid_extrusion_eligible = (
        ext_level in ("high", "med")
        and (
            production_volume in ("Proto", "Small batch")
            or material == "Steel"
            or (cnc_score >= extrusion_score - 2 and cnc_score > 0)
            or (is_auto_mode and material != "Aluminum")  # AUTO: prefer hybrid unless Aluminum
        )
        and "EXTRUSION" in eligible_processes
        and "CNC" in eligible_processes
    )
    
    if hybrid_extrusion_eligible:
        # Guard: do NOT flip CNC_TURNING to CNC if turning_likelihood is med/high and CNC_TURNING score beats CNC by >= 2
        turning_score = scores.get("CNC_TURNING", 0)
        should_preserve_turning = (
            primary == "CNC_TURNING"
            and turn_level in ("med", "high")
            and (turning_score - cnc_score) >= 2
        )
        
        # AUTO mode: do NOT let hybrid decision override primary. AUTO scoring/tie-break has already chosen
        # SHEET_METAL or EXTRUSION; hybrid remains a secondary offer (add EXTRUSION to secondary, findings)
        # but must not force primary=CNC. Preserves geometry-driven AUTO selection.
        hybrid_may_override_primary = not is_auto_mode and not should_preserve_turning
        # Also avoid overriding SHEET_METAL when ok_sheet evidence present (AUTO or not)
        if primary == "SHEET_METAL" and ok_sheet_evidence:
            hybrid_may_override_primary = False
        
        if should_preserve_turning:
            trace.append(f"process_selection: preserving CNC_TURNING primary (turning_likelihood={turn_level}, turning_score={turning_score} vs cnc_score={cnc_score}, diff={turning_score - cnc_score} >= 2)")
        elif hybrid_may_override_primary:
            # Set primary to CNC, add EXTRUSION to secondary if not already there
            if primary != "CNC" and cnc_score > 0:
                # Override if CNC is competitive (within 2 points) or volume/material favor CNC
                if cnc_score >= extrusion_score - 2:
                    primary = "CNC"
                    primary_score = cnc_score
                    trace.append(f"process_selection: hybrid decision - primary=CNC (extrusion_score={extrusion_score}, cnc_score={cnc_score}, level={ext_level})")
        elif is_auto_mode:
            trace.append(f"process_selection: hybrid decision - not overriding primary in AUTO mode (primary={primary}, keeping geometry-driven choice)")
        if "EXTRUSION" not in secondary and extrusion_score > 0:
            secondary.append("EXTRUSION")
            # Keep only top 2
            secondary = secondary[:2]
            trace.append(f"process_selection: hybrid decision - added EXTRUSION to secondary")
    
    # Production override: ONLY when strong extrusion signal + Production volume + Aluminum + extrusion clearly wins
    # In AUTO mode: require Aluminum material to flip to EXTRUSION primary
    production_override = (
        ext_level in ("high", "med")
        and production_volume == "Production"
        and material == "Aluminum"  # Only Aluminum, not Steel or other materials
        and extrusion_score > cnc_score + 2  # Extrusion must be clearly better (not just +1)
        and "EXTRUSION" in eligible_processes
    )
    
    if production_override:
        primary = "EXTRUSION"
        primary_score = extrusion_score
        if "CNC" not in secondary and cnc_score > 0:
            secondary.insert(0, "CNC")
            secondary = secondary[:2]
        trace.append(f"process_selection: production override - primary=EXTRUSION (level={ext_level}, volume={production_volume}, extrusion_score={extrusion_score} vs cnc_score={cnc_score})")
    
    # AUTO-only strong extrusion tie-break: prefer EXTRUSION when tied with CNC and strong extrusion geometry exists
    if user_process_raw == "AUTO" and primary == "CNC":
        # Check for strong extrusion geometry (computed earlier)
        strong_extrusion_geometry = (
            ext_level in ("med", "high")
            and ext_axis_ratio is not None and ext_axis_ratio >= 3.0
            and ext_cv != "?" and isinstance(ext_cv, (int, float)) and ext_cv >= 0.30
            and turn_level == "none"
            and not ok_sheet_evidence
        )
        if strong_extrusion_geometry:
            extrusion_score_final = scores.get("EXTRUSION", 0)
            if extrusion_score_final == primary_score:
                primary = "EXTRUSION"
                primary_score = extrusion_score_final
                trace.append(f"process_selection: AUTO tie-break - choosing EXTRUSION over CNC (scores tied at {primary_score}, strong extrusion geometry: axis_ratio={ext_axis_ratio:.3f} >= 3.0, coeff_var={ext_cv:.3f} >= 0.30)")

    # Not recommended: only ELIGIBLE processes with low score; exclude gated processes
    not_recommended = []
    excluded_set = {primary} | set(secondary)
    for p in eligible_processes:
        if p in excluded_set:
            continue
        score_p = scores.get(p, 0)
        # Never list user's selected process (skip if AUTO)
        if user_process and p == user_process:
            continue
        # Stricter rule: only add if score <= 1 AND primary_score - score >= 5
        # Also, do NOT put CNC_TURNING unless user explicitly implies turning and it's still low score
        if p == "CNC_TURNING":
            turning_mentioned = any(kw in text for kw in ("turn", "turning", "lathe"))
            if not (turning_mentioned and score_p <= 1):
                continue
        if score_p <= 1 and (primary_score - score_p) >= 5:
            not_recommended.append(p)

    # AM selected but not favored: add clarity reason (skip if AUTO)
    if user_process == "AM" and primary != "AM":
        am_score = scores.get("AM", 0)
        primary_score_val = scores.get(primary, 0)
        if primary_score_val > am_score:
            all_reasons.append(f"AM chosen but {primary} is recommended at {production_volume.lower()} volume unless geometry requires AM (internal channels/lattice/complex features).")
    
    # Build primary rationale from score_breakdown of primary process ONLY (fix rationale mixing)
    primary_breakdown = score_breakdown.get(primary, [])
    reasons_primary = [e["reason"] for e in primary_breakdown if e.get("reason")]
    reasons_secondary_list: list[str] = []
    if secondary:
        for sec_proc in secondary[:2]:
            sec_breakdown = score_breakdown.get(sec_proc, [])
            reasons_secondary_list.extend(e["reason"] for e in sec_breakdown if e.get("reason"))
    reasons_secondary_list = list(dict.fromkeys(reasons_secondary_list))[:4]

    # Legacy reasons for backward compat (dedupe, cap at 6)
    reasons = list(dict.fromkeys(all_reasons))[:6]
    if secondary and not reasons:
        sec_list = ", ".join(secondary)
        reasons.append(f"Close alternatives scored similarly: {sec_list}")
    
    # Honest PSI logging: avoid misleading "final score_diff=0" when primary was forced
    if sheet_primary_prevented and raw_best_process and raw_second_process is not None:
        raw_diff = raw_best_score - raw_second_score
        eff_second = second_process  # already recomputed
        eff_second_sc = second_score
        eff_diff = primary_score - eff_second_sc
        trace.append(f"PSI: raw_best={raw_best_process}={raw_best_score} raw_second={raw_second_process}={raw_second_score} raw_diff={raw_diff}")
        trace.append(f"PSI: effective_primary={primary}={primary_score} effective_second={eff_second or 'none'}={eff_second_sc} effective_diff={eff_diff} forced_primary=True")
    elif len(sorted_by_score) >= 2 and primary != sorted_by_score[0]:
        final_score_diff = primary_score - second_score
        trace.append(f"PSI: final score_diff={final_score_diff} (after tie-break, primary changed from {sorted_by_score[0]} to {primary})")

    tradeoffs = [
        "Tooling lead time vs unit cost: IM/Sheet metal need tooling; CNC/AM suit low volume.",
        "Tolerance and finish: Define critical interfaces; plan post-machining or inspection where needed.",
        "Risk drivers: Warpage (IM/AM), supports (AM), setups (CNC/Sheet metal) affect feasibility.",
        "Volume sensitivity: IM and sheet metal favor production runs; CNC/AM suit proto and small batch.",
        "Documentation: 2D drawing and scale confirmation improve tolerance and process selection.",
    ]

    # Normalize secondary: remove duplicates and primary
    secondary_normalized = _normalize_primary_secondary(primary, secondary)
    
    rec = {
        "primary": primary,
        "secondary": secondary_normalized,
        "not_recommended": not_recommended,
        "reasons": reasons,
        "reasons_primary": reasons_primary,
        "reasons_secondary": reasons_secondary_list,
        "tradeoffs": tradeoffs,
        "scores": scores,
        "score_breakdown": score_breakdown,
        "process_gates": gates,
        "eligible_processes": eligible_processes,
        "user_selected": user_process_raw,  # Store original (including AUTO) for reporting
    }
    if sheet_primary_prevented and forced_reason is not None:
        rec["forced_primary"] = True
        rec["raw_best"] = raw_best_process or "SHEET_METAL"
        rec["forced_reason"] = forced_reason
    if cad_lite_result is not None:
        rec["cad_lite"] = cad_lite_result
        rec["sheet_metal_likelihood"] = {"level": likelihood, "source": likelihood_source}
    if extrusion_lite_result is not None:
        rec["extrusion_lite"] = extrusion_lite_result
    if extrusion_likelihood_result is not None:
        rec["extrusion_likelihood"] = extrusion_likelihood_result
    if turning_lite_result is not None:
        rec["turning_lite"] = turning_lite_result
    if turning_likelihood_result is not None:
        rec["turning_likelihood"] = turning_likelihood_result
    if cad_status != "ok":
        rec["am_likelihood_level"] = am_likelihood_level
        rec["am_likelihood_source"] = am_likelihood_source

    # Post-process: ensure not_recommended never includes primary or secondary
    # Apply strict threshold: only clearly worse options (score <= primary - 3 OR score < 0)
    excluded_for_less = {rec["primary"]} | set(rec.get("secondary") or [])
    less_suitable = rec.get("not_recommended", [])
    less_suitable = [
        p for p in less_suitable
        if p not in excluded_for_less
        and (scores.get(p, 0) <= scores.get(rec["primary"], 0) - 3 or scores.get(p, 0) < 0)
    ]
    rec["not_recommended"] = less_suitable

    trace.append(f"Process selection computed: primary={primary} user_selected={user_process if user_process else 'AUTO (geometry-driven)'}")
    trace.append(f"process_selection: cad_uploaded={'y' if cad_uploaded(state) else 'n'} evidence_available={'y' if cad_evidence_available(state) else 'n'}")
    if keyword_matches:
        kw_str = "/".join(keyword_matches)
        trace.append(f"Process selection: user_text keywords influenced scoring ({kw_str})")
    if user_process and primary != user_process:
        trace.append(f"Process selection mismatch: user_selected={user_process} but primary={primary}")
    
    # Add AM tech recommendation if primary is AM
    if primary == "AM":
        am_tech, am_src = _resolve_am_tech(state)
        trace.append(f"PSI: am_tech={am_tech} (source={am_src})")

    # Debug logging (opt-in via CNCR_DEBUG_PSI=1)
    if CONFIG.debug_psi:
        import sys
        print("=== CNCR_DEBUG_PSI: Process Selection Debug ===", file=sys.stderr)
        print(f"eligible_processes: {sorted(eligible_processes)}", file=sys.stderr)
        if cad_lite_result:
            bbox = cad_lite_result.get("bbox_dims")
            print(f"cad_lite: status={cad_lite_result.get('status')} bbox_dims={bbox} "
                  f"t_est={cad_lite_result.get('t_est')} av_ratio={cad_lite_result.get('av_ratio')} "
                  f"t_over_min_dim={cad_lite_result.get('t_over_min_dim')}", file=sys.stderr)
        if turning_lite_result:
            print(f"turning_lite: status={turning_lite_result.get('status')} level={turning_lite_result.get('level')} "
                  f"ratio_ab={turning_lite_result.get('ratio_ab')} ratio_cb={turning_lite_result.get('ratio_cb')} "
                  f"axis={turning_lite_result.get('turning_axis')}", file=sys.stderr)
        print(f"sheet_metal_likelihood: {likelihood} (source={likelihood_source})", file=sys.stderr)
        if extrusion_likelihood_result:
            ext_lh = extrusion_likelihood_result
            print(f"extrusion_likelihood: level={ext_lh.get('level')} coeff_var={ext_lh.get('coeff_var')} "
                  f"axis={ext_lh.get('axis')}", file=sys.stderr)
        print("Final scores:", file=sys.stderr)
        for proc in sorted(CANDIDATES):
            score = scores.get(proc, 0)
            if proc in eligible_processes or score != 0:
                marker = " <-- PRIMARY" if proc == primary else (" <-- SECONDARY" if proc in secondary else "")
                print(f"  {proc}: {score}{marker}", file=sys.stderr)
        print("=" * 50, file=sys.stderr)

    out: dict = {
        "process_recommendation": rec,
        "trace": trace,
        "findings": findings,
    }
    # CAD evidence propagation: when bins path (no numeric part_metrics_evidence), add cad_lite evidence so rules/explain see it
    if not state.get("part_metrics_evidence"):
        cad_ev = build_cad_lite_evidence_from_rec(rec)
        if cad_ev:
            out["part_metrics_evidence"] = cad_ev
    return out
