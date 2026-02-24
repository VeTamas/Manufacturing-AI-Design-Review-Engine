"""RAG node: FAISS retrieval from process-specific KB indices.

Portfolio: FAISS index files (data/outputs/kb_index/) are not committed. Rebuild with
scripts/build_kb_index.py; works with minimal sample KB in knowledge_base/.
"""
from __future__ import annotations

from pathlib import Path

from agent.state import GraphState
from agent.tools.kb_tool import retrieve
from agent.nodes.process_selection import _resolve_am_tech
from agent.process_registry import resolve_retrieval_index

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_BASE = PROJECT_ROOT / "data" / "outputs" / "kb_index"


def _index_exists(name: str) -> bool:
    """Check if FAISS index exists for given process/index name."""
    idx_dir = INDEX_BASE / (name or "cnc").lower()
    return (idx_dir / "index.faiss").is_file() and (idx_dir / "metadata.json").is_file()


def _normalize_am_terms(text: str) -> str:
    """Normalize AM-related terms for better RAG recall."""
    t = (text or "").lower()
    repl = {
        "polyamide": "nylon",
        "polyamide 12": "pa12 nylon",
        "pa 12": "pa12",
        "photopolymer": "resin",
        "stereolithography": "sla",
        "selective laser sintering": "sls",
        "multi jet fusion": "mjf hp",
        "hp multi jet fusion": "mjf hp",
        "laser powder bed fusion": "lpbf",
        "direct metal laser sintering": "dmls lpbf",
        "selective laser melting": "slm lpbf",
    }
    for k, v in repl.items():
        t = t.replace(k, v)
    return t

IM_KEYWORDS = (
    "draft", "eject", "ejection", "texture", "textured",
    "gate", "gating", "weld line", "weldline", "knit line",
    "vent", "venting", "sink", "warpage", "warp", "shrink",
    "rib", "boss", "snap", "latch", "living hinge",
    "insert", "overmold", "over-mold", "metal insert",
    "undercut", "side action", "lifter"
)

CASTING_KEYWORDS = (
    "die cast", "diecasting", "hpdc", "lpdc",
    "investment", "lost wax", "ceramic shell",
    "urethane", "vacuum casting", "silicone mold", "soft tooling",
    "porosity", "shrink", "warpage", "misrun", "cold shut",
    "gating", "gate", "runner", "sprue", "vent", "overflow",
    "parting line", "draft", "ejection", "ejector", "slide", "lifter", "core",
    "weld repair", "heat treat", "radiography", "x-ray"
)

FORGING_KEYWORDS = (
    "forging", "forged", "flash", "die", "hammer", "press",
    "closed die", "impression die", "parting line", "draft",
    "grain flow", "lap", "laps", "fold", "cold shut", "underfill", "die fill", "flow",
    "rib", "boss", "thin section", "sharp corner", "radius", "fillet",
    "heat treat", "quench", "distortion",
    "open die", "ring rolling",
    "trim", "coining", "die machining",
)
CORE_FORG_TOPICS = (
    "draft", "parting line", "flash", "grain flow", "lap", "laps", "fold",
    "cold shut", "underfill", "die fill",
)
EXTRUSION_KEYWORDS = (
    "extrusion", "profile", "rail", "channel", "anodize", "6063",
    "constant cross section", "long prismatic", "hollow profile", "extruded",
    "die swell", "calibration", "uniform wall",
)
MIM_KEYWORDS = (
    "mim", "metal injection molding", "metal injection moulding",
    "powder", "feedstock", "binder", "debinding", "sinter", "sintering",
    "shrinkage", "distortion", "warpage", "17-4", "17-4ph", "316l", "stainless",
    "small metal part", "complex", "near-net", "tolerances", "design guidelines",
)
THERMOFORMING_KEYWORDS = (
    "thermoforming", "thermoform", "vacuum forming", "vacuum form", "pressure forming",
    "plug assist", "draft", "radii", "wall thinning", "webbing", "vent holes", "vacuum holes",
    "trimming", "tolerances", "deep draw", "sheet forming", "matched mold", "twin-sheet",
)
COMPRESSION_MOLDING_KEYWORDS = (
    "compression molding", "compression moulding", "thermoset", "thermosetting",
    "smc", "bmc", "bulk molding compound", "sheet molding compound",
    "cure shrinkage", "flash", "parting line", "charge placement", "fiber orientation",
    "voids", "venting", "tolerances", "trimming", "cure", "curing", "press",
)
AM_GEOM_KW = {
    "internal channel", "internal channels", "conformal cooling", "lattice", "topology", "gyroid",
    "impossible to machine", "cannot machine", "not machinable", "enclosed cavity",
    "monolithic", "part consolidation", "lightweight lattice",
    "ct scan", "powder removal"
}


def _build_im_query(state: GraphState) -> tuple[str, list[str]]:
    """Build IM-focused retrieval query. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()

    # Extract inputs
    material = getattr(inp, "material", "") or ""
    volume = getattr(inp, "production_volume", "") or ""
    tolerance = getattr(inp, "tolerance_criticality", "") or ""

    # Extract geometry bins
    size = getattr(part, "part_size", "") or "" if part else ""
    wall = getattr(part, "min_wall_thickness", "") or "" if part else ""
    radius = getattr(part, "min_internal_radius", "") or "" if part else ""
    pockets = getattr(part, "pocket_aspect_class", "") or "" if part else ""
    holes = getattr(part, "hole_depth_class", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""
    variety = getattr(part, "feature_variety", "") or "" if part else ""

    # Extract confidence inputs
    has_2d = False
    scale_ok = True
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
            scale_ok = conf_inputs.get("step_scale_confirmed", True)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))

    # Extract matching keywords from user_text (dedupe, max 8)
    matched_topics = []
    for kw in IM_KEYWORDS:
        if kw in user_text and kw not in matched_topics:
            matched_topics.append(kw)
            if len(matched_topics) >= 8:
                break

    # Build findings summary (max 6)
    findings_parts = []
    for f in findings[:6]:
        sev = f.severity
        title = f.title[:60]  # Truncate long titles
        findings_parts.append(f"[{sev}] {title}")

    # Check for process selection mismatch
    proc_rec = state.get("process_recommendation")
    mismatch_info = None
    if proc_rec and isinstance(proc_rec, dict) and inp:
        user_proc = getattr(inp, "process", None) or ""
        rec_primary = proc_rec.get("primary")
        rec_scores = proc_rec.get("scores", {})
        if rec_primary and rec_primary != user_proc:
            primary_score = rec_scores.get(rec_primary, 0)
            user_score = rec_scores.get(user_proc, 0)
            score_diff = primary_score - user_score
            if score_diff >= 2:
                mismatch_info = (user_proc, rec_primary, score_diff)
                if "process selection mismatch" not in matched_topics:
                    matched_topics.append("process selection mismatch")

    # Build query sections
    parts = ["INJECTION MOLDING DFM guidance."]
    parts.append(f"Context: material={material}, volume={volume}, tolerance={tolerance}")
    parts.append(f"Geometry bins: size={size}, wall={wall}, radius={radius}, pockets={pockets}, holes={holes}, access={access}, variety={variety}")
    parts.append(f"Confidence: has_2d_drawing={has_2d}, step_scale_confirmed={scale_ok}")
    if mismatch_info:
        user_proc, rec_primary, score_diff = mismatch_info
        parts.append(f"Process selection: user_selected={user_proc}, recommended_primary={rec_primary}, score_diff={score_diff}")
    if matched_topics:
        parts.append(f"Topics: {', '.join(matched_topics)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    # Truncate if needed (keep under ~1200 chars)
    if len(query) > 1200:
        query = query[:1197] + "..."

    return query, matched_topics[:6]  # Return topics list for trace (max 6)


def _build_casting_query(state: GraphState) -> tuple[str, list[str]]:
    """Build CASTING-focused retrieval query. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()
    casting_hint = state.get("casting_subprocess_hint") or "unknown"

    # Extract inputs
    material = getattr(inp, "material", "") or ""
    volume = getattr(inp, "production_volume", "") or ""
    tolerance = getattr(inp, "tolerance_criticality", "") or ""
    load = getattr(inp, "load_type", "") or ""

    # Extract geometry bins
    size = getattr(part, "part_size", "") or "" if part else ""
    wall = getattr(part, "min_wall_thickness", "") or "" if part else ""
    radius = getattr(part, "min_internal_radius", "") or "" if part else ""
    pockets = getattr(part, "pocket_aspect_class", "") or "" if part else ""
    holes = getattr(part, "hole_depth_class", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""
    variety = getattr(part, "feature_variety", "") or "" if part else ""
    clamping = getattr(part, "has_clamping_faces", False) if part else False

    # Extract confidence inputs
    has_2d = False
    scale_ok = True
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
            scale_ok = conf_inputs.get("step_scale_confirmed", True)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))

    # Extract matching keywords from user_text (dedupe, max 8)
    matched_topics = []
    for kw in CASTING_KEYWORDS:
        if kw in user_text and kw not in matched_topics:
            matched_topics.append(kw)
            if len(matched_topics) >= 8:
                break

    # Build findings summary (max 6)
    findings_parts = []
    for f in findings[:6]:
        sev = f.severity
        title = f.title[:60]  # Truncate long titles
        findings_parts.append(f"[{sev}] {title}")

    # Build query sections
    parts = ["CASTING DFM guidance."]
    parts.append(f"Subprocess: {casting_hint}.")
    parts.append(f"Context: material={material}, volume={volume}, tolerance={tolerance}, load={load}")
    parts.append(f"Geometry bins: size={size}, wall={wall}, radius={radius}, pockets={pockets}, holes={holes}, access={access}, variety={variety}, clamping={clamping}")
    parts.append(f"Confidence: has_2d_drawing={has_2d}, step_scale_confirmed={scale_ok}")
    if matched_topics:
        parts.append(f"Topics: {', '.join(matched_topics)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    # Truncate if needed (keep under ~1200 chars)
    if len(query) > 1200:
        query = query[:1197] + "..."

    return query, matched_topics[:6]  # Return topics list for trace (max 6)


def _build_forging_query(state: GraphState) -> tuple[str, list[str]]:
    """Build FORGING-focused retrieval query. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()
    forging_hint = state.get("forging_subprocess_hint") or "unknown"

    # Extract inputs
    material = getattr(inp, "material", "") or ""
    volume = getattr(inp, "production_volume", "") or ""
    tolerance = getattr(inp, "tolerance_criticality", "") or ""
    load = getattr(inp, "load_type", "") or ""

    # Extract geometry bins
    size = getattr(part, "part_size", "") or "" if part else ""
    wall = getattr(part, "min_wall_thickness", "") or "" if part else ""
    radius = getattr(part, "min_internal_radius", "") or "" if part else ""
    pockets = getattr(part, "pocket_aspect_class", "") or "" if part else ""
    holes = getattr(part, "hole_depth_class", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""
    variety = getattr(part, "feature_variety", "") or "" if part else ""
    clamping = getattr(part, "has_clamping_faces", False) if part else False

    # Extract confidence inputs
    has_2d = False
    scale_ok = True
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
            scale_ok = conf_inputs.get("step_scale_confirmed", True)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))

    # Extract matching keywords: prioritize core, then rest (dedupe, max 8)
    matched = [k for k in FORGING_KEYWORDS if k in user_text]
    core = [k for k in CORE_FORG_TOPICS if k in user_text]
    rest = [k for k in matched if k not in core]
    topics = (core + rest)[:8]

    # Build findings summary (max 6)
    findings_parts = []
    for f in findings[:6]:
        sev = f.severity
        title = f.title[:60]
        findings_parts.append(f"[{sev}] {title}")

    # Build query sections: front-load subprocess + focus topics
    focus_str = ", ".join(topics[:4]) if topics else ""
    parts = [f"FORGING DFM guidance. Subprocess={forging_hint}. Focus={focus_str}."]
    parts.append(f"Context: material={material}, volume={volume}, tolerance={tolerance}, load={load}")
    parts.append(f"Geometry bins: size={size}, wall={wall}, radius={radius}, pockets={pockets}, holes={holes}, access={access}, variety={variety}, clamping={clamping}")
    parts.append(f"Confidence: has_2d_drawing={has_2d}, step_scale_confirmed={scale_ok}")
    if topics:
        parts.append(f"Topics: {', '.join(topics)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    if len(query) > 1200:
        query = query[:1197] + "..."

    return query, topics[:6]


def _build_extrusion_query(state: GraphState) -> tuple[str, list[str]]:
    """Build EXTRUSION-focused retrieval query. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()

    material = getattr(inp, "material", "") or ""
    volume = getattr(inp, "production_volume", "") or ""
    tolerance = getattr(inp, "tolerance_criticality", "") or ""
    load = getattr(inp, "load_type", "") or ""

    size = getattr(part, "part_size", "") or "" if part else ""
    wall = getattr(part, "min_wall_thickness", "") or "" if part else ""
    radius = getattr(part, "min_internal_radius", "") or "" if part else ""
    pockets = getattr(part, "pocket_aspect_class", "") or "" if part else ""
    holes = getattr(part, "hole_depth_class", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""
    variety = getattr(part, "feature_variety", "") or "" if part else ""
    clamping = getattr(part, "has_clamping_faces", False) if part else False

    has_2d = False
    scale_ok = True
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
            scale_ok = conf_inputs.get("step_scale_confirmed", True)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))

    matched = [k for k in EXTRUSION_KEYWORDS if k in user_text][:8]
    findings_parts = [f"[{f.severity}] {f.title[:60]}" for f in findings[:6]]

    parts = ["EXTRUSION DFM guidance. Constant cross-section profiles."]
    parts.append(f"Context: material={material}, volume={volume}, tolerance={tolerance}, load={load}")
    parts.append(f"Geometry bins: size={size}, wall={wall}, radius={radius}, pockets={pockets}, holes={holes}, access={access}, variety={variety}, clamping={clamping}")
    parts.append(f"Confidence: has_2d_drawing={has_2d}, step_scale_confirmed={scale_ok}")
    if matched:
        parts.append(f"Topics: {', '.join(matched)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    if len(query) > 1200:
        query = query[:1197] + "..."
    return query, matched[:6]


def _build_mim_query(state: GraphState) -> tuple[str, list[str]]:
    """Build MIM-focused retrieval query. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()

    material = getattr(inp, "material", "") or ""
    volume = getattr(inp, "production_volume", "") or ""
    tolerance = getattr(inp, "tolerance_criticality", "") or ""
    load = getattr(inp, "load_type", "") or ""

    size = getattr(part, "part_size", "") or "" if part else ""
    wall = getattr(part, "min_wall_thickness", "") or "" if part else ""
    radius = getattr(part, "min_internal_radius", "") or "" if part else ""
    pockets = getattr(part, "pocket_aspect_class", "") or "" if part else ""
    holes = getattr(part, "hole_depth_class", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""
    variety = getattr(part, "feature_variety", "") or "" if part else ""
    clamping = getattr(part, "has_clamping_faces", False) if part else False

    has_2d = False
    scale_ok = True
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
            scale_ok = conf_inputs.get("step_scale_confirmed", True)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))

    matched = [k for k in MIM_KEYWORDS if k in user_text][:8]
    findings_parts = [f"[{f.severity}] {f.title[:60]}" for f in findings[:6]]

    parts = ["MIM DFM guidance. Metal injection molding. Debinding. Sintering. Shrinkage. Tolerances. Design guidelines."]
    parts.append(f"Context: material={material}, volume={volume}, tolerance={tolerance}, load={load}")
    parts.append(f"Geometry bins: size={size}, wall={wall}, radius={radius}, pockets={pockets}, holes={holes}, access={access}, variety={variety}, clamping={clamping}")
    parts.append(f"Confidence: has_2d_drawing={has_2d}, step_scale_confirmed={scale_ok}")
    if matched:
        parts.append(f"Topics: {', '.join(matched)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    if len(query) > 1200:
        query = query[:1197] + "..."
    return query, matched[:6]


def _build_thermoforming_query(state: GraphState) -> tuple[str, list[str]]:
    """Build THERMOFORMING-focused retrieval query. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()

    material = getattr(inp, "material", "") or ""
    volume = getattr(inp, "production_volume", "") or ""
    tolerance = getattr(inp, "tolerance_criticality", "") or ""
    load = getattr(inp, "load_type", "") or ""

    size = getattr(part, "part_size", "") or "" if part else ""
    wall = getattr(part, "min_wall_thickness", "") or "" if part else ""
    radius = getattr(part, "min_internal_radius", "") or "" if part else ""
    pockets = getattr(part, "pocket_aspect_class", "") or "" if part else ""
    holes = getattr(part, "hole_depth_class", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""
    variety = getattr(part, "feature_variety", "") or "" if part else ""
    clamping = getattr(part, "has_clamping_faces", False) if part else False

    has_2d = False
    scale_ok = True
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
            scale_ok = conf_inputs.get("step_scale_confirmed", True)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))

    matched = [k for k in THERMOFORMING_KEYWORDS if k in user_text][:8]
    findings_parts = [f"[{f.severity}] {f.title[:60]}" for f in findings[:6]]

    parts = ["THERMOFORMING DFM guidance. Vacuum forming. Pressure forming. Sheet forming. Plug assist. Draft. Radii. Wall thinning. Webbing. Vent holes. Trimming. Tolerances."]
    parts.append(f"Context: material={material}, volume={volume}, tolerance={tolerance}, load={load}")
    parts.append(f"Geometry bins: size={size}, wall={wall}, radius={radius}, pockets={pockets}, holes={holes}, access={access}, variety={variety}, clamping={clamping}")
    parts.append(f"Confidence: has_2d_drawing={has_2d}, step_scale_confirmed={scale_ok}")
    if matched:
        parts.append(f"Topics: {', '.join(matched)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    if len(query) > 1200:
        query = query[:1197] + "..."
    return query, matched[:6]


def _build_compression_molding_query(state: GraphState) -> tuple[str, list[str]]:
    """Build COMPRESSION_MOLDING-focused retrieval query. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()

    material = getattr(inp, "material", "") or ""
    volume = getattr(inp, "production_volume", "") or ""
    tolerance = getattr(inp, "tolerance_criticality", "") or ""
    load = getattr(inp, "load_type", "") or ""

    size = getattr(part, "part_size", "") or "" if part else ""
    wall = getattr(part, "min_wall_thickness", "") or "" if part else ""
    radius = getattr(part, "min_internal_radius", "") or "" if part else ""
    pockets = getattr(part, "pocket_aspect_class", "") or "" if part else ""
    holes = getattr(part, "hole_depth_class", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""
    variety = getattr(part, "feature_variety", "") or "" if part else ""
    clamping = getattr(part, "has_clamping_faces", False) if part else False

    has_2d = False
    scale_ok = True
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
            scale_ok = conf_inputs.get("step_scale_confirmed", True)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))

    matched = [k for k in COMPRESSION_MOLDING_KEYWORDS if k in user_text][:8]
    findings_parts = [f"[{f.severity}] {f.title[:60]}" for f in findings[:6]]

    parts = ["COMPRESSION MOLDING DFM guidance. Thermoset. Composite. SMC. BMC. Cure shrinkage. Flash. Parting line. Charge placement. Fiber orientation. Voids. Venting. Tolerances. Trimming."]
    parts.append(f"Context: material={material}, volume={volume}, tolerance={tolerance}, load={load}")
    parts.append(f"Geometry bins: size={size}, wall={wall}, radius={radius}, pockets={pockets}, holes={holes}, access={access}, variety={variety}, clamping={clamping}")
    parts.append(f"Confidence: has_2d_drawing={has_2d}, step_scale_confirmed={scale_ok}")
    if matched:
        parts.append(f"Topics: {', '.join(matched)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    if len(query) > 1200:
        query = query[:1197] + "..."
    return query, matched[:6]


def _build_am_query(state: GraphState, am_tech: str) -> tuple[str, list[str]]:
    """Build AM-focused retrieval query for specific technology. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    raw_text = ((state.get("description") or state.get("user_text")) or "").lower()
    user_text = _normalize_am_terms(raw_text)

    material = getattr(inp, "material", "") or ""
    volume = getattr(inp, "production_volume", "") or ""
    tolerance = getattr(inp, "tolerance_criticality", "") or ""
    load = getattr(inp, "load_type", "") or ""

    size = getattr(part, "part_size", "") or "" if part else ""
    wall = getattr(part, "min_wall_thickness", "") or "" if part else ""
    radius = getattr(part, "min_internal_radius", "") or "" if part else ""
    pockets = getattr(part, "pocket_aspect_class", "") or "" if part else ""
    holes = getattr(part, "hole_depth_class", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""
    variety = getattr(part, "feature_variety", "") or "" if part else ""
    clamping = getattr(part, "has_clamping_faces", False) if part else False

    has_2d = False
    scale_ok = True
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
            scale_ok = conf_inputs.get("step_scale_confirmed", True)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf_inputs, "step_scale_confirmed", True))

    # Tech-specific keywords
    tech_keywords = []
    if am_tech == "FDM":
        tech_keywords = ["fdm", "fused deposition", "filament", "layer adhesion", "overhang", "support", "warping"]
    elif am_tech == "METAL_LPBF":
        tech_keywords = ["lpbf", "dmls", "powder bed", "metal am", "residual stress", "heat treat", "hip", "powder removal"]
    elif am_tech == "THERMOPLASTIC_HIGH_TEMP":
        tech_keywords = ["peek", "pei", "ultem", "high temp", "high temperature", "chamber temperature", "warping", "shrinkage"]
    elif am_tech == "SLA":
        tech_keywords = ["sla", "stereolithography", "resin", "photopolymer", "uv cure", "support", "post-cure", "drain hole", "IPA wash"]
    elif am_tech == "SLS":
        tech_keywords = ["sls", "selective laser sintering", "nylon", "pa12", "pa11", "powder removal", "drain hole", "warpage"]
    elif am_tech == "MJF":
        tech_keywords = ["mjf", "multi jet fusion", "hp mjf", "fusing agent", "powder removal", "nylon", "drain hole"]
    
    matched = [kw for kw in tech_keywords if kw in user_text][:8]
    findings_parts = [f"[{f.severity}] {f.title[:60]}" for f in findings[:6]]

    parts = [f"AM DFM guidance. Technology: {am_tech}."]
    parts.append(f"Context: material={material}, volume={volume}, tolerance={tolerance}, load={load}")
    parts.append(f"Geometry bins: size={size}, wall={wall}, radius={radius}, pockets={pockets}, holes={holes}, access={access}, variety={variety}, clamping={clamping}")
    parts.append(f"Confidence: has_2d_drawing={has_2d}, step_scale_confirmed={scale_ok}")
    if matched:
        parts.append(f"Topics: {', '.join(matched)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    if len(query) > 1200:
        query = query[:1197] + "..."
    return query, matched[:6]


def _build_hybrid_cnc_query(state: GraphState, primary_process: str) -> tuple[str, list[str]]:
    """Build CNC-focused query for hybrid manufacturing secondary operations. Returns (query_string, topics_list)."""
    inp = state.get("inputs")
    part = state.get("part_summary")
    conf_inputs = state.get("confidence_inputs")
    findings = state.get("findings", [])
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()

    tolerance = getattr(inp, "tolerance_criticality", "") or ""
    size = getattr(part, "part_size", "") or "" if part else ""
    access = getattr(part, "accessibility_risk", "") or "" if part else ""

    has_2d = False
    if conf_inputs is not None:
        if isinstance(conf_inputs, dict):
            has_2d = conf_inputs.get("has_2d_drawing", False)
        else:
            has_2d = bool(getattr(conf_inputs, "has_2d_drawing", False))

    # Build query focused on secondary operations
    cnc_keywords = ["secondary operations", "finish machining", "datums", "tolerances", "drilling", "tapping", "milling", "fixturing"]
    if primary_process == "THERMOFORMING":
        cnc_keywords.extend(["cnc trimming", "trim flange", "fixture", "trimming"])
    elif primary_process == "EXTRUSION":
        cnc_keywords.extend(["cut-to-length", "drilling", "tapping", "milling"])
    
    matched = [kw for kw in cnc_keywords if kw in user_text][:6]
    findings_parts = [f"[{f.severity}] {f.title[:60]}" for f in findings[:6] if any(kw in f.title.lower() for kw in ["machin", "datum", "tolerance", "drill", "tap", "mill", "trim"])]

    parts = [f"CNC secondary operations. Finish machining. Datums. Tolerances. Drilling. Tapping. Milling. Fixturing."]
    if primary_process == "THERMOFORMING":
        parts.append("CNC trimming. Trim flange. Fixture design.")
    elif primary_process == "EXTRUSION":
        parts.append("Cut-to-length. Drilling. Tapping. Milling operations.")
    parts.append(f"Context: tolerance={tolerance}, size={size}, access={access}, has_2d_drawing={has_2d}")
    if matched:
        parts.append(f"Topics: {', '.join(matched)}")
    if findings_parts:
        parts.append(f"Findings: {'; '.join(findings_parts)}")

    query = " ".join(parts)
    if len(query) > 1200:
        query = query[:1197] + "..."
    return query, matched[:6]


def rag_node(state: GraphState) -> dict:
    """RAG node: retrieve knowledge base chunks for findings (triggered by decision node)."""
    inp = state.get("inputs")
    process = getattr(inp, "process", None) if inp else None
    process = process or "CNC"
    top_k = 5
    trace_delta = [f"Entered rag_node (process={process}, top_k={top_k})"]
    if process == "INJECTION_MOLDING":
        query, topics = _build_im_query(state)
        if topics:
            trace_delta.append(f"RAG query built: injection_molding (topics: {', '.join(topics)})")
        else:
            trace_delta.append("RAG query built: injection_molding")
    elif process == "CASTING":
        query, topics = _build_casting_query(state)
        if topics:
            trace_delta.append(f"RAG query built: casting (topics: {', '.join(topics[:6])})")
        else:
            trace_delta.append("RAG query built: casting")
    elif process == "FORGING":
        query, topics = _build_forging_query(state)
        if topics:
            trace_delta.append(f"RAG query built: forging (topics: {', '.join(topics[:6])})")
        else:
            trace_delta.append("RAG query built: forging")
    elif process == "EXTRUSION":
        query, topics = _build_extrusion_query(state)
        if topics:
            trace_delta.append(f"RAG query built: extrusion (topics: {', '.join(topics[:6])})")
        else:
            trace_delta.append("RAG query built: extrusion")
    elif process == "MIM":
        query, topics = _build_mim_query(state)
        if topics:
            trace_delta.append(f"RAG query built: mim (topics: {', '.join(topics[:6])})")
        else:
            trace_delta.append("RAG query built: mim")
    elif process == "THERMOFORMING":
        query, topics = _build_thermoforming_query(state)
        if topics:
            trace_delta.append(f"RAG query built: thermoforming (topics: {', '.join(topics[:6])})")
        else:
            trace_delta.append("RAG query built: thermoforming")
    elif process == "COMPRESSION_MOLDING":
        query, topics = _build_compression_molding_query(state)
        if topics:
            trace_delta.append(f"RAG query built: compression_molding (topics: {', '.join(topics[:6])})")
        else:
            trace_delta.append("RAG query built: compression_molding")
    elif process == "AM":
        user_am_tech = getattr(inp, "am_tech", None) if inp else None
        am_tech, _ = _resolve_am_tech(state, user_am_tech)
        query, topics = _build_am_query(state, am_tech)
        if topics:
            trace_delta.append(f"RAG query built: am_{am_tech.lower()} (topics: {', '.join(topics[:6])})")
        else:
            trace_delta.append(f"RAG query built: am_{am_tech.lower()}")
        # Store am_tech in state for retrieval section
        state["_am_tech_resolved"] = am_tech
    else:
        findings = state.get("findings", [])
        if not findings:
            trace_delta.append("RAG completed: retrieved 0 snippets (no findings)")
            usage_rag = {"retrieved_k": top_k, "sources_count": 0, "cache_hit": False}
            return {"trace": trace_delta, "sources": [], "usage_by_node": {"rag": usage_rag}}
        query_parts = [f"{f.title}: {f.recommendation}" for f in findings]
        query = " ".join(query_parts)
    
    # Effective process for RAG: when no specific process selected (AUTO), use recommended primary (no "auto" index)
    proc_rec = state.get("process_recommendation") or {}
    primary = proc_rec.get("primary")
    if process == "AUTO":
        effective_process_for_rag = primary if primary else "CNC"
        trace_delta.append(f"RAG: no specific process (AUTO) → effective_process_for_rag={effective_process_for_rag}")
    else:
        effective_process_for_rag = process

    # Initialize main_retrieve_process from effective process (never use "auto" index)
    main_retrieve_process = effective_process_for_rag
    offer_retrieve_process = None

    # Canonical variables for actual FAISS indices used (normalized trace keys)
    main_index_used = None
    offer_index_used = None
    hybrid_primary_index_used = None
    hybrid_secondary_index_used = None

    # Map process to retrieval index using centralized registry (effective process, not AUTO)
    am_tech_resolved = None
    if effective_process_for_rag == "AM":
        _am, _ = _resolve_am_tech(state, getattr(inp, "am_tech", None) if inp else None)
        am_tech_resolved = state.get("_am_tech_resolved") or _am
        main_retrieve_process = resolve_retrieval_index(effective_process_for_rag, am_tech_resolved, state)
        trace_delta.append(f"RAG: AM tech resolved to {am_tech_resolved}, using index {main_retrieve_process}")
    else:
        main_retrieve_process = resolve_retrieval_index(effective_process_for_rag, None, None)

    # Set canonical main_index_used after resolution (always actual index name, never "auto")
    main_index_used = main_retrieve_process
    scores = proc_rec.get("scores") or {}
    user_text = ((state.get("description") or state.get("user_text")) or "").lower()
    # PATCH 4: Trace normalized AM terms for RAG recall boost
    trace_delta.append(f"RAG: rag_user_text_normalized={_normalize_am_terms(user_text)[:120]}")
    
    # Process offer detection
    extrusion_offer = primary == "EXTRUSION" and primary != process
    mim_offer = primary == "MIM" and primary != process
    thermo_offer = primary == "THERMOFORMING" and primary != process
    comp_offer = primary == "COMPRESSION_MOLDING" and primary != process
    casting_offer = primary == "CASTING" and primary != process
    forging_offer = primary == "FORGING" and primary != process
    
    # AM offer: trigger if primary is AM OR if strong AM-only geometry signals present
    am_geom_hits = len([kw for kw in AM_GEOM_KW if kw in user_text])
    am_offer = (
        (primary == "AM" and primary != process)
        or (am_geom_hits >= 2 and process != "AM")
    )
    
    # Resolve AM tech-specific index early if AM offer is detected (for trace consistency)
    if am_offer:
        am_tech_offer, _ = _resolve_am_tech(state, getattr(inp, "am_tech", None) if inp else None)
        offer_index_used = resolve_retrieval_index("AM", am_tech_offer, state)
    
    # Hybrid offer detection: primary is hybrid-suitable AND (keywords OR structured signals)
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
    
    score_diff = scores.get(primary, 0) - scores.get(process, 0) if primary and process else 0
    hybrid_offer = (
        primary in hybrid_suitable_processes
        and primary != process
        and (has_hybrid_keyword_signal or hybrid_structured_signal)
        and score_diff >= 4  # Strong mismatch threshold
    )
    
    # Determine trigger type for trace
    hybrid_trigger = "keyword" if has_hybrid_keyword_signal else "structured" if hybrid_structured_signal else "none"
    
    # Legacy offer_idx for backward compatibility (uses canonical offer_index_used when available)
    offer_idx = "EXTRUSION" if extrusion_offer else "MIM" if mim_offer else "THERMOFORMING" if thermo_offer else "COMPRESSION_MOLDING" if comp_offer else (offer_index_used if am_offer and offer_index_used else ("AM" if am_offer else "none"))
    hybrid_trigger_str = f", hybrid_trigger={hybrid_trigger}" if hybrid_offer else ""
    # Normalized trace keys (canonical variables)
    trace_delta.append(f"PSI debug: primary={primary}, user_selected={process}, extrusion_offer={'yes' if extrusion_offer else 'no'}, mim_offer={'yes' if mim_offer else 'no'}, thermo_offer={'yes' if thermo_offer else 'no'}, comp_offer={'yes' if comp_offer else 'no'}, am_offer={'yes' if am_offer else 'no'}, hybrid_offer={'yes' if hybrid_offer else 'no'}{hybrid_trigger_str}, main_index_used={main_index_used}, offer_index_used={offer_index_used or 'none'}, hybrid_primary_index_used={hybrid_primary_index_used or 'none'}, hybrid_secondary_index_used={hybrid_secondary_index_used or 'none'}")
    # Backward compatibility aliases
    trace_delta.append(f"RAG: main_retrieve_index={main_index_used}, offer_retrieve_index={offer_index_used or offer_idx}")

    # Extract subprocess hints for main retrieval (user-selected process)
    subprocess_hint = (
        state.get("forging_subprocess_hint") if process == "FORGING"
        else (state.get("casting_subprocess_hint") if process == "CASTING" else None)
    )

    # PATCH 3: Index sanity check + fallback chain (am→cnc for am_*; cnc→am for others)
    retrieve_index_final = main_retrieve_process
    fallback_chain: list[str] = []
    if not _index_exists(retrieve_index_final):
        missing_name = retrieve_index_final
        if retrieve_index_final.startswith("am_"):
            for cand in ["am", "cnc"]:
                if _index_exists(cand):
                    retrieve_index_final = cand
                    fallback_chain.append(cand)
                    break
        else:
            for cand in ["cnc", "am"]:
                if _index_exists(cand):
                    retrieve_index_final = cand
                    fallback_chain.append(cand)
                    break
        trace_delta.append(f"RAG: rag_index_missing={missing_name}")
        trace_delta.append(f"RAG: rag_index_fallback={retrieve_index_final}")
        trace_delta.append(f"RAG: rag_index_fallback_chain={fallback_chain}")
        main_index_used = retrieve_index_final  # Log actual index used

    # Main retrieval: always from user-selected process index (or fallback)
    idx_name = retrieve_index_final.lower()
    trace_delta.append(f"RAG: main_index_used={main_index_used}")
    if subprocess_hint:
        trace_delta.append(f"RAG: retrieving from local {idx_name} index (hint={subprocess_hint})")
    else:
        trace_delta.append(f"RAG: retrieving from local {idx_name} index")

    try:
        sources = retrieve(query, process=retrieve_index_final, top_k=top_k, subprocess_hint=subprocess_hint)

        # Close call: forced primary and SHEET_METAL in secondary → add 2 snippets from sheet_metal KB
        proc_rec_rag = state.get("process_recommendation") or {}
        if proc_rec_rag.get("forced_primary") and "SHEET_METAL" in (proc_rec_rag.get("secondary") or []):
            sheet_idx = resolve_retrieval_index("SHEET_METAL", None, None)
            if _index_exists(sheet_idx):
                try:
                    sm_sources = retrieve(query, process=sheet_idx, top_k=2, subprocess_hint=None)
                    seen = {s.get("source") or s.get("path") or "" for s in sources}
                    for src in sm_sources:
                        key = src.get("source") or src.get("path") or ""
                        if key and key not in seen:
                            seen.add(key)
                            sources.append(dict(src))
                    if sm_sources:
                        trace_delta.append("RAG: close call → added 2 snippets from sheet_metal index")
                except (FileNotFoundError, Exception):
                    pass

        # Second retrieval for offer evidence only (when user did not select recommended process)
        offer_sources: list[dict] = []
        if extrusion_offer:
            offer_index_used = resolve_retrieval_index("EXTRUSION", None, None)
            trace_delta.append(f"RAG: offer_retrieve_index={offer_index_used} (extrusion offer evidence)")
            try:
                ext_query, _ = _build_extrusion_query(state)
                offer_sources = retrieve(ext_query, process="EXTRUSION", top_k=4, subprocess_hint=None)
            except (FileNotFoundError, Exception):
                pass
            sources = list(sources) + list(offer_sources)
        elif mim_offer:
            offer_index_used = resolve_retrieval_index("MIM", None, None)
            trace_delta.append(f"RAG: offer_retrieve_index={offer_index_used} (mim offer evidence)")
            try:
                mim_query, _ = _build_mim_query(state)
                offer_sources_raw = retrieve(mim_query, process="MIM", top_k=4, subprocess_hint=None)
                # Tag MIM offer evidence sources with explicit metadata
                for src in offer_sources_raw:
                    tagged_src = dict(src)
                    tagged_src["process"] = "MIM"
                    tagged_src["role"] = "offer_evidence"
                    offer_sources.append(tagged_src)
            except (FileNotFoundError, Exception):
                pass
            sources = list(sources) + list(offer_sources)
            trace_delta.append("RAG: offer_evidence_tagged=true")
        elif thermo_offer:
            offer_index_used = resolve_retrieval_index("THERMOFORMING", None, None)
            trace_delta.append(f"RAG: offer_retrieve_index={offer_index_used} (thermoforming offer evidence)")
            try:
                thermo_query, _ = _build_thermoforming_query(state)
                offer_sources_raw = retrieve(thermo_query, process="THERMOFORMING", top_k=4, subprocess_hint=None)
                # Tag THERMOFORMING offer evidence sources with explicit metadata
                for src in offer_sources_raw:
                    tagged_src = dict(src)
                    tagged_src["process"] = "THERMOFORMING"
                    tagged_src["role"] = "offer_evidence"
                    offer_sources.append(tagged_src)
            except (FileNotFoundError, Exception):
                pass
            sources = list(sources) + list(offer_sources)
            trace_delta.append("RAG: offer_evidence_tagged=true")
        elif comp_offer:
            offer_index_used = resolve_retrieval_index("COMPRESSION_MOLDING", None, None)
            trace_delta.append(f"RAG: offer_retrieve_index={offer_index_used} (compression_molding offer evidence)")
            try:
                comp_query, _ = _build_compression_molding_query(state)
                offer_sources_raw = retrieve(comp_query, process="COMPRESSION_MOLDING", top_k=4, subprocess_hint=None)
                # Tag COMPRESSION_MOLDING offer evidence sources with explicit metadata
                for src in offer_sources_raw:
                    tagged_src = dict(src)
                    tagged_src["process"] = "COMPRESSION_MOLDING"
                    tagged_src["role"] = "offer_evidence"
                    offer_sources.append(tagged_src)
            except (FileNotFoundError, Exception):
                pass
            sources = list(sources) + list(offer_sources)
            trace_delta.append("RAG: offer_evidence_tagged=true")
        elif am_offer:
            am_retrieve_process = offer_index_used or resolve_retrieval_index("AM", None, state)
            if not offer_index_used:
                offer_index_used = am_retrieve_process
            am_tech_offer, _ = _resolve_am_tech(state, getattr(inp, "am_tech", None) if inp else None)
            am_offer_reason = f"am_geom_hits={am_geom_hits}" if am_geom_hits >= 2 and primary != "AM" else "primary=AM"
            trace_delta.append(f"RAG: am_offer=yes (reason={am_offer_reason}), offer_retrieve_index={offer_index_used} (am offer evidence, tech={am_tech_offer})")
            # PATCH 3: Index fallback chain for offer evidence
            am_offer_idx = am_retrieve_process
            if not _index_exists(am_offer_idx):
                missing_offer = am_offer_idx
                offer_fallback_chain: list[str] = []
                for cand in ["am", "cnc"]:
                    if _index_exists(cand):
                        am_offer_idx = cand
                        offer_fallback_chain.append(cand)
                        break
                trace_delta.append(f"RAG: rag_index_missing={missing_offer}")
                trace_delta.append(f"RAG: rag_index_fallback={am_offer_idx}")
                trace_delta.append(f"RAG: rag_index_fallback_chain={offer_fallback_chain}")
            try:
                am_query, _ = _build_am_query(state, am_tech_offer)
                offer_sources_raw = retrieve(am_query, process=am_offer_idx, top_k=4, subprocess_hint=None)
                # Tag AM offer evidence sources with explicit metadata
                for src in offer_sources_raw:
                    tagged_src = dict(src)
                    tagged_src["process"] = "AM"
                    tagged_src["am_tech"] = am_tech_offer
                    tagged_src["role"] = "offer_evidence"
                    offer_sources.append(tagged_src)
            except (FileNotFoundError, Exception):
                pass
            sources = list(sources) + list(offer_sources)
            trace_delta.append("RAG: offer_evidence_tagged=true")

        # Hybrid offer: dual evidence retrieval (primary process + CNC)
        hybrid_primary_sources: list[dict] = []
        hybrid_cnc_sources: list[dict] = []
        if hybrid_offer:
            # Map primary process to actual FAISS index name using centralized registry
            hybrid_primary_index_used = resolve_retrieval_index(primary, None, None) if primary else "none"
            hybrid_secondary_index_used = resolve_retrieval_index("CNC", None, None)
            
            trace_delta.append(f"RAG: hybrid_offer=yes, hybrid_trigger={hybrid_trigger}, hybrid_primary_index={hybrid_primary_index_used}, hybrid_secondary_index={hybrid_secondary_index_used}")
            # Retrieve from primary process index (if not already retrieved)
            primary_already_retrieved = (
                (extrusion_offer and primary == "EXTRUSION") or
                (mim_offer and primary == "MIM") or
                (thermo_offer and primary == "THERMOFORMING") or
                (comp_offer and primary == "COMPRESSION_MOLDING") or
                (casting_offer and primary == "CASTING") or
                (forging_offer and primary == "FORGING")
            )
            if not primary_already_retrieved:
                try:
                    if primary == "CASTING":
                        primary_query, _ = _build_casting_query(state)
                        hybrid_primary_raw = retrieve(primary_query, process="CASTING", top_k=4, subprocess_hint=None)
                    elif primary == "FORGING":
                        primary_query, _ = _build_forging_query(state)
                        hybrid_primary_raw = retrieve(primary_query, process="FORGING", top_k=4, subprocess_hint=None)
                    elif primary == "EXTRUSION":
                        primary_query, _ = _build_extrusion_query(state)
                        hybrid_primary_raw = retrieve(primary_query, process="EXTRUSION", top_k=4, subprocess_hint=None)
                    elif primary == "MIM":
                        primary_query, _ = _build_mim_query(state)
                        hybrid_primary_raw = retrieve(primary_query, process="MIM", top_k=4, subprocess_hint=None)
                    elif primary == "THERMOFORMING":
                        primary_query, _ = _build_thermoforming_query(state)
                        hybrid_primary_raw = retrieve(primary_query, process="THERMOFORMING", top_k=4, subprocess_hint=None)
                    elif primary == "COMPRESSION_MOLDING":
                        primary_query, _ = _build_compression_molding_query(state)
                        hybrid_primary_raw = retrieve(primary_query, process="COMPRESSION_MOLDING", top_k=4, subprocess_hint=None)
                    else:
                        hybrid_primary_raw = []
                    # Tag primary sources
                    for src in hybrid_primary_raw:
                        tagged_src = dict(src)
                        tagged_src["process"] = primary
                        tagged_src["role"] = "offer_evidence"
                        tagged_src["offer_type"] = "hybrid_primary"
                        hybrid_primary_sources.append(tagged_src)
                except (FileNotFoundError, Exception):
                    pass
            else:
                # Re-tag existing primary offer sources with hybrid_primary
                # Find sources that match the primary process
                for src in sources:
                    if src.get("process") == primary and src.get("role") == "offer_evidence":
                        tagged_src = dict(src)
                        tagged_src["offer_type"] = "hybrid_primary"
                        hybrid_primary_sources.append(tagged_src)
            
            # Retrieve from CNC index for secondary finishing evidence
            try:
                cnc_query, _ = _build_hybrid_cnc_query(state, primary)
                hybrid_cnc_raw = retrieve(cnc_query, process="CNC", top_k=4, subprocess_hint=None)
                # Tag CNC sources
                for src in hybrid_cnc_raw:
                    tagged_src = dict(src)
                    tagged_src["process"] = "CNC"
                    tagged_src["role"] = "offer_evidence"
                    tagged_src["offer_type"] = "hybrid_secondary"
                    hybrid_cnc_sources.append(tagged_src)
            except (FileNotFoundError, Exception):
                pass
            
            sources = list(sources) + list(hybrid_primary_sources) + list(hybrid_cnc_sources)
            trace_delta.append(f"RAG: hybrid_primary_snippets={len(hybrid_primary_sources)}, hybrid_secondary_snippets={len(hybrid_cnc_sources)}")
        
        # Count sources by role for breakdown trace
        main_sources_count = len([s for s in sources if s.get("role") != "offer_evidence" and s.get("offer_type") is None])
        offer_sources_count = len([s for s in sources if s.get("role") == "offer_evidence" and s.get("offer_type") != "hybrid_primary" and s.get("offer_type") != "hybrid_secondary"])
        hybrid_primary_count = len([s for s in sources if s.get("offer_type") == "hybrid_primary"])
        hybrid_secondary_count = len([s for s in sources if s.get("offer_type") == "hybrid_secondary"])
        trace_delta.append(f"RAG: sources_breakdown main={main_sources_count} offer={offer_sources_count} hybrid_primary={hybrid_primary_count} hybrid_secondary={hybrid_secondary_count}")

        # Normalized trace summary using canonical variables
        offer_idx_str = f", offer_index_used={offer_index_used}" if offer_index_used else ""
        if hybrid_offer:
            offer_idx_str += f", hybrid_primary_index_used={hybrid_primary_index_used}, hybrid_secondary_index_used={hybrid_secondary_index_used}"
        trace_delta.append(f"RAG completed: retrieved {len(sources)} snippets (main_index_used={main_index_used}{offer_idx_str})")
        usage_rag = {"retrieved_k": top_k, "sources_count": len(sources), "cache_hit": False}
        return {"trace": trace_delta, "sources": sources, "usage_by_node": {"rag": usage_rag}}
    except FileNotFoundError:
        idx_lower = main_retrieve_process.lower()
        trace_delta.append(
            f"RAG index not found for process={main_retrieve_process} (expected: data/outputs/kb_index/{idx_lower}/)"
        )
        trace_delta.append("RAG completed: retrieved 0 snippets (index unavailable)")
        usage_rag = {"retrieved_k": top_k, "sources_count": 0, "cache_hit": False}
        return {"trace": trace_delta, "sources": [], "usage_by_node": {"rag": usage_rag}}
    except Exception as e:
        trace_delta.append(f"RAG retrieval failed: {str(e)}")
        trace_delta.append("RAG completed: retrieved 0 snippets (error)")
        usage_rag = {"retrieved_k": top_k, "sources_count": 0, "cache_hit": False}
        return {"trace": trace_delta, "sources": [], "usage_by_node": {"rag": usage_rag}}
