from __future__ import annotations

import hashlib
import json
import logging
import os
import re

from diskcache import Cache
from pathlib import Path

from agent.config import CONFIG, resolve_llm_settings
from agent.explain.fallback import build_fallback_report
from agent.geometry.cad_presence import cad_uploaded
from agent.geometry.evidence_for_llm import build_geometry_evidence_block
from agent.llm import ChatOpenAINoTemperature
from agent.llm.ollama_client import OllamaClient
from agent.state import Error, GraphState
from agent.utils.retry import run_with_retries
from langchain_community.callbacks import get_openai_callback

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_CACHE: Cache | None = None


def _get_cache() -> Cache:
    global _CACHE
    if _CACHE is None:
        os.makedirs(CONFIG.cache_dir, exist_ok=True)
        _CACHE = Cache(CONFIG.cache_dir)
    return _CACHE


def _cache_key(model_name: str, system_tmpl: str, user_prompt: str) -> str:
    payload = {
        "model": model_name,
        "system": system_tmpl,
        "user": user_prompt,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _explain_cache_signature(state: GraphState) -> str:
    """Build a stable cache signature for explain that includes CAD/numeric state.
    
    Ensures cache key changes when STEP, part_summary_mode, part_metrics_provider,
    or part_metrics_evidence changes (CNC-only). Avoids stale "Part geometry not provided".
    """
    sig: dict = {}
    inputs = state.get("inputs")
    if inputs:
        sig["process"] = getattr(inputs, "process", None)
        sig["material"] = getattr(inputs, "material", None)
        sig["production_volume"] = getattr(inputs, "production_volume", None)
        sig["load_type"] = getattr(inputs, "load_type", None)
        sig["tolerance_criticality"] = getattr(inputs, "tolerance_criticality", None)

    part = state.get("part_summary")
    if part:
        sig["part_summary"] = {
            "part_size": getattr(part, "part_size", None),
            "min_internal_radius": getattr(part, "min_internal_radius", None),
            "min_wall_thickness": getattr(part, "min_wall_thickness", None),
            "hole_depth_class": getattr(part, "hole_depth_class", None),
            "pocket_aspect_class": getattr(part, "pocket_aspect_class", None),
            "feature_variety": getattr(part, "feature_variety", None),
            "accessibility_risk": getattr(part, "accessibility_risk", None),
            "has_clamping_faces": getattr(part, "has_clamping_faces", None),
        }

    findings = state.get("findings", []) or []
    findings_sig: list[dict] = []
    for f in findings:
        fe: dict = {
            "id": getattr(f, "id", None),
            "title": getattr(f, "title", None),
            "severity": getattr(f, "severity", None),
            "recommendation": getattr(f, "recommendation", None),
        }
        ev = getattr(f, "evidence", None)
        if isinstance(ev, dict) and ev:
            fe["evidence"] = sorted((k, repr(v)) for k, v in ev.items())
        prop = getattr(f, "proposal", None)
        if prop and isinstance(prop, str):
            fe["proposal"] = prop[:200]
        steps = getattr(f, "proposal_steps", None)
        if steps and isinstance(steps, list):
            fe["proposal_steps"] = [str(s)[:100] for s in steps[:5]]
        findings_sig.append(fe)
    sig["findings"] = findings_sig

    sig["rag_enabled"] = state.get("rag_enabled", False)
    sources = state.get("sources", []) or []
    sig["sources"] = sorted(s.get("source", "?") for s in sources[:20])

    # CNC numeric: cache must invalidate when STEP / provider / evidence changes
    sig["part_summary_mode"] = state.get("part_summary_mode") or "bins"
    step_path = state.get("step_path")
    sig["step_path_basename"] = (
        os.path.basename(step_path) if step_path and isinstance(step_path, str) else None
    )
    sig["part_metrics_provider"] = state.get("part_metrics_provider")
    ev = state.get("part_metrics_evidence") or {}
    if isinstance(ev, dict) and ev:
        sig["part_metrics_evidence"] = sorted((k, repr(v)) for k, v in ev.items())
    else:
        sig["part_metrics_evidence"] = []

    # Phase 4: part_features summary
    pf = state.get("part_features") or {}
    if isinstance(pf, dict) and pf:
        sig["part_features"] = {
            k: pf.get(k) for k in ("hole_count", "hole_max_ld", "pocket_count", "pocket_max_aspect")
            if k in pf and pf[k] is not None
        }
    else:
        sig["part_features"] = {}

    raw = json.dumps(sig, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_text(path: Path) -> str:
    from agent.utils.filetrace import traced_read_text
    return traced_read_text(path, encoding="utf-8")


def _contains_invented_tolerances(text: str) -> bool:
    """Check if text contains invented numeric tolerances that should not appear.
    
    Flags common invented tolerance patterns:
    - "±" anywhere
    - Numeric ranges like "0.05–0.20 mm" or "0.1-0.2 mm"
    - Numeric tolerance values near tolerance-related keywords
    
    Args:
        text: Text to check
        
    Returns:
        True if invented tolerance patterns detected
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Check for ± symbol
    if "±" in text or "\u00b1" in text:
        return True
    
    # Check for numeric range patterns: "0.05–0.20 mm", "0.1-0.2 mm", etc.
    range_pattern = re.compile(r"\b\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*mm\b", re.IGNORECASE)
    if range_pattern.search(text):
        return True
    
    # Phase 4: "~" or "about" near tolerance keywords (invented approx); do not block for non-tolerance dims
    tol_kw = ["tolerance", "±", "microns", "micron"]
    for kw in tol_kw:
        idx = text_lower.find(kw)
        if idx >= 0:
            start, end = max(0, idx - 60), min(len(text), idx + len(kw) + 60)
            chunk = text_lower[start:end]
            if "~" in chunk or " about " in chunk:
                return True
    # Check for numeric tolerance values near tolerance-related keywords
    # Pattern: number + "mm" near words like "tolerance", "±", "range", "tighten", "loosen", "specify"
    tolerance_keywords = ["tolerance", "±", "range", "tighten", "loosen", "specify", "microns", "micron"]
    tolerance_value_pattern = re.compile(r"\b\d+(?:\.\d+)?\s*mm\b", re.IGNORECASE)
    
    # Check if tolerance keywords appear near numeric mm values
    for keyword in tolerance_keywords:
        if keyword in text_lower:
            # Find all numeric mm values
            matches = tolerance_value_pattern.finditer(text)
            for match in matches:
                # Check context around the match (±50 chars)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text_lower[start:end]
                # If keyword appears in context, likely invented tolerance
                if keyword in context:
                    return True
    
    return False


def _is_placeholder_line(s: str) -> bool:
    """Check if a line is a placeholder token.
    
    Args:
        s: Line text to check
        
    Returns:
        True if line appears to be a placeholder
    """
    s_lower = s.lower().strip()
    
    # Check for angle-bracket placeholders
    if "<" in s and ">" in s:
        return True
    
    # Check for common placeholder keywords (case-insensitive)
    placeholder_keywords = ["todo", "tbd", "placeholder"]
    if any(kw in s_lower for kw in placeholder_keywords):
        return True
    
    # Check for common misspelling "assumpction" or pattern "assumption 1/2/3/4" without real content
    if "assumpction" in s_lower:
        return True
    
    # Check for pattern like "assumption 1", "assumption 2" etc. without meaningful content
    # This matches lines that are just "assumption N" or "<assumption N>" with minimal other text
    assumption_pattern = re.search(r"assumption\s*[0-9]", s_lower)
    if assumption_pattern:
        # If the line is mostly just "assumption N" with minimal other content, it's a placeholder
        stripped = re.sub(r"[^a-z0-9]", "", s_lower)
        if len(stripped) < 20:  # Very short after removing punctuation
            return True
    
    # Check if becomes empty after stripping bullets/punctuation/whitespace
    stripped = re.sub(r"[-•\s\.\,\!\?]", "", s_lower)
    if len(stripped) < 3:  # Too short to be meaningful
        return True
    
    return False


def _parse_actions_assumptions(resp: str) -> tuple[list[str], list[str]]:
    """Parse actions and assumptions from LLM response.
    
    Tolerant to:
    - "-" or "•" bullets
    - Trailing punctuation
    - Extra whitespace
    
    Filters out placeholder lines from assumptions.
    """
    lines = [ln.strip() for ln in resp.splitlines() if ln.strip()]
    actions: list[str] = []
    assumptions: list[str] = []
    section: str | None = None
    for ln in lines:
        upper = ln.upper().strip()
        if upper.startswith("ACTION CHECKLIST"):
            section = "actions"
            continue
        if upper.startswith("ASSUMPTIONS"):
            section = "assumptions"
            continue
        if ln.startswith(("-", "•")):
            # Strip bullet marker and normalize whitespace
            item = ln.lstrip("-• ").strip()
            # Remove trailing punctuation if excessive (keep one period)
            if item.endswith("...") or (item.count(".") > 1 and not item.endswith(".")):
                item = item.rstrip(".").rstrip() + "."
            if item:
                if section == "actions":
                    actions.append(item)
                elif section == "assumptions":
                    # Filter out placeholder lines
                    if not _is_placeholder_line(item):
                        assumptions.append(item)
    if not actions:
        actions = ["Review findings and apply recommended DFM improvements."]
    return actions[:6], assumptions[:6]


def _output_contains_evidence_keys(resp: str, state: GraphState) -> bool:
    """Phase 4: CNC numeric mode with hole_*/pocket_* evidence requires >= 2 keys in output."""
    inputs = state.get("inputs")
    process = getattr(inputs, "process", None) if inputs else None
    mode = state.get("part_summary_mode") or "bins"
    evidence = state.get("part_metrics_evidence") or {}
    if process not in ("CNC", "CNC_TURNING") or mode != "numeric":
        return True
    hole_pocket_keys = {"hole_count", "hole_max_ld", "hole_max_depth_mm", "hole_diameters_mm", "pocket_count", "pocket_max_aspect", "pocket_max_depth_mm"}
    present = [k for k in hole_pocket_keys if k in evidence and evidence[k] is not None]
    if len(present) < 1:
        return True
    resp_lower = resp.lower()
    found = sum(1 for k in present if k in resp_lower or k.replace("_", " ") in resp_lower)
    return found >= 2


def _is_valid_content(resp: str) -> bool:
    """Check if response contains required sections with minimum content.
    
    Robust validation:
    - Must contain both "ACTION CHECKLIST" and "ASSUMPTIONS" headers (case-insensitive, whitespace-tolerant)
    - Must have at least 4 bullets under ACTION CHECKLIST (preferably 6)
    - Must have at least 2 bullets under ASSUMPTIONS (preferably 4)
    - Must NOT contain markdown code fences (```)
    - Must NOT contain invented numeric tolerances
    - Count bullets only within each section
    """
    # Reject markdown fences
    if "```" in resp:
        return False
    
    # Reject invented tolerances
    if _contains_invented_tolerances(resp):
        return False
    
    # Normalize whitespace for header detection
    resp_normalized = " ".join(resp.split())
    resp_upper = resp_normalized.upper()
    
    # Check headers (case-insensitive, whitespace-tolerant)
    has_action_header = "ACTION CHECKLIST" in resp_upper
    has_assumptions_header = "ASSUMPTIONS" in resp_upper
    
    if not (has_action_header and has_assumptions_header):
        return False
    
    # Count bullets in each section (only within section boundaries)
    lines = [ln.strip() for ln in resp.splitlines() if ln.strip()]
    in_actions = False
    in_assumptions = False
    action_count = 0
    assumption_count = 0
    
    for ln in lines:
        upper = ln.upper().strip()
        # Check for section headers (tolerant to extra whitespace/colons)
        if "ACTION CHECKLIST" in upper and not in_assumptions:
            in_actions = True
            in_assumptions = False
            continue
        if "ASSUMPTIONS" in upper and in_actions:
            in_actions = False
            in_assumptions = True
            continue
        
        # Count bullets only within the correct section
        if in_actions and not in_assumptions and ln.startswith(("-", "•")):
            action_count += 1
        elif in_assumptions and not in_actions and ln.startswith(("-", "•")):
            assumption_count += 1
    
    # Require minimum bullets: 4 actions, 2 assumptions
    return action_count >= 4 and assumption_count >= 2


def _normalize_for_dedup(text: str) -> str:
    """Normalize text for duplicate detection.
    
    Args:
        text: Action or assumption text
        
    Returns:
        Normalized string (lowercase, no punctuation, first ~6 words)
    """
    # Lowercase, strip punctuation, get first ~6 words
    normalized = re.sub(r'[^\w\s]', '', text.lower())
    words = normalized.split()[:6]
    return " ".join(words)


def _normalize_checklist_item(action: str) -> str:
    """Normalize checklist item to complete imperative sentence.
    
    Args:
        action: Raw action text
        
    Returns:
        Normalized action: starts with single imperative verb, ends with period.
        Severity tags ([HIGH], [MEDIUM], [LOW], "Verify LOW]", etc.) are stripped.
    """
    if not action:
        return action
    
    # Strip severity tags and artifacts (avoid checklist contamination)
    action = re.sub(r"^\[?(HIGH|MEDIUM|LOW)\]?\s*", "", action, flags=re.IGNORECASE)
    action = re.sub(r"Verify\s+(?:LOW|MEDIUM|HIGH)\]?\s*", "Verify ", action, flags=re.IGNORECASE)
    action = re.sub(r"\]\s*", " ", action).strip()
    # Strip leading bullets/checkbox markers and whitespace
    action = action.lstrip("-•[] ").strip()
    
    # Common imperative verbs (for double-verb removal and verb detection)
    imperative_verbs = frozenset([
        "address", "add", "apply", "confirm", "consider", "define", "ensure",
        "implement", "review", "run", "verify", "check", "balance", "reduce",
        "improve", "optimize", "modify", "adjust", "evaluate", "assess",
        "establish", "document", "inspect", "test", "specify",
        "identify", "validate", "keep", "select",
    ])
    # Leading verbs that often duplicate the second verb (drop first when both are imperatives)
    drop_when_second_verb = frozenset(["verify", "review", "confirm"])

    # Fix double-verb patterns: "Verify Validate", "Confirm Identify", "Confirm Keep", etc.
    words = action.split()
    if len(words) >= 2:
        first_word = words[0].lower()
        second_word = words[1].lower()
        if first_word in drop_when_second_verb and second_word in imperative_verbs:
            action = " ".join(words[1:])
    
    # Check if starts with verb-like word
    first_word = action.split()[0].lower() if action.split() else ""
    starts_with_verb = first_word in imperative_verbs
    
    # If doesn't start with verb, add appropriate prefix
    if not starts_with_verb:
        # Detect common patterns and add appropriate verb
        action_lower = action.lower()
        if "tolerance" in action_lower or "dimension" in action_lower:
            action = "Confirm " + action
        elif "finding" in action_lower:
            action = "Review " + action
        elif "volume" in action_lower or "process" in action_lower:
            action = "Confirm " + action
        elif "tool" in action_lower or "accessibility" in action_lower:
            action = "Verify " + action
        elif "inspection" in action_lower or "plan" in action_lower:
            action = "Define " + action
        else:
            # Default: use "Address" for generic cases
            action = "Address " + action
    
    # Ensure ends with period
    action = action.rstrip(".!?") + "."
    
    # Capitalize first letter
    if action:
        action = action[0].upper() + action[1:]
    
    return action


def _deduplicate_actions(actions: list[str]) -> list[str]:
    """Remove near-duplicate actions using simple normalization.
    
    Args:
        actions: List of action strings
        
    Returns:
        Deduplicated list (first occurrence kept)
    """
    seen = set()
    deduped = []
    for action in actions:
        norm = _normalize_for_dedup(action)
        if norm not in seen:
            seen.add(norm)
            deduped.append(action)
    return deduped


def _normalize_checklist_items(actions: list[str]) -> list[str]:
    """Normalize all checklist items to complete imperative sentences.
    
    Args:
        actions: List of action strings
        
    Returns:
        Normalized actions list (each is complete imperative sentence)
    """
    if not actions:
        return actions
    
    # Normalize each item
    normalized = [_normalize_checklist_item(a) for a in actions]
    
    return normalized


def _fill_checklist_to_six(actions: list[str], findings: list) -> tuple[list[str], bool]:
    """Fill checklist to exactly 6 items from findings if needed.
    
    Args:
        actions: Current actions list
        findings: List of Finding objects
        
    Returns:
        Tuple of (filled actions list, fill_occurred bool)
    """
    fill_occurred = False
    
    if len(actions) >= 6:
        return actions[:6], fill_occurred
    
    # Fill from findings (HIGH then MED)
    high_med_findings = [f for f in findings if getattr(f, "severity", "") in ("HIGH", "MEDIUM")]
    
    existing_norms = {_normalize_for_dedup(a) for a in actions}
    
    # Add from findings
    for f in high_med_findings:
        if len(actions) >= 6:
            break
        fid = getattr(f, "id", "")
        rec = getattr(f, "recommendation", "")
        if rec:
            # Convert to actionable sentence
            rec_clean = rec.split(".")[0].strip()
            if rec_clean:
                if fid:
                    new_action = f"Address {fid}: {rec_clean}."
                else:
                    new_action = rec_clean + "."
                new_action = _normalize_checklist_item(new_action)
                norm = _normalize_for_dedup(new_action)
                if norm not in existing_norms:
                    actions.append(new_action)
                    existing_norms.add(norm)
                    fill_occurred = True
    
    # Add safe generic items if still fewer than 6
    generic_items = [
        "Run a CAM tool-reach/accessibility check for all flagged features.",
        "Define an inspection plan for the critical dimensions (medium tolerance criticality).",
        "Verify material and process assumptions match design intent.",
        "Confirm manufacturing volumes align with process selection.",
    ]
    
    for generic in generic_items:
        if len(actions) >= 6:
            break
        norm = _normalize_for_dedup(generic)
        if norm not in existing_norms:
            actions.append(generic)
            existing_norms.add(norm)
            fill_occurred = True
    
    return actions[:6], fill_occurred


def _normalize_assumption_formatting(assumption: str) -> str:
    """Normalize assumption formatting: ALL CAPS to sentence case, preserve acronyms, ensure period.
    
    Args:
        assumption: Raw assumption text
        
    Returns:
        Normalized assumption (sentence case, period at end)
    """
    if not assumption:
        return assumption
    
    # Preserve common acronyms (CNC, MIM, AM, CAD, DFM, etc.)
    acronyms = {"CNC", "MIM", "AM", "CAD", "DFM", "CAM", "EDM", "SLA", "SLS", "MJF", "LPBF", "FDM", "2D", "3D"}
    
    # Check if entire assumption is ALL CAPS (excluding acronyms and punctuation)
    words = assumption.split()
    is_all_caps = all(
        word.upper() == word or word.upper() in acronyms or not word.isalpha()
        for word in words
    ) and any(word.isalpha() and word.upper() == word and word.upper() not in acronyms for word in words)
    
    if is_all_caps:
        # Convert to sentence case, preserving acronyms
        normalized_words = []
        for word in words:
            if word.upper() in acronyms or not word.isalpha():
                normalized_words.append(word)
            elif normalized_words:  # Not first word
                normalized_words.append(word.lower())
            else:  # First word
                normalized_words.append(word.capitalize())
        assumption = " ".join(normalized_words)
    
    # Ensure period at end
    assumption = assumption.rstrip(".!?") + "."
    
    return assumption


def build_deterministic_assumptions(state: GraphState) -> list[str]:
    """Build a deterministic assumptions list from known state flags (no placeholders).

    Uses: CAD uploaded, drawing provided, scale confirmed, tolerance criticality,
    volume, material. Pass to explain/refine prompts so LLM does not invent placeholders.
    """
    assumptions: list[str] = []
    cad = cad_uploaded(state)
    conf = state.get("confidence_inputs")
    has_2d = False
    scale_ok = True
    if conf is not None:
        if isinstance(conf, dict):
            has_2d = bool(conf.get("has_2d_drawing", False))
            scale_ok = bool(conf.get("step_scale_confirmed", True))
        else:
            has_2d = bool(getattr(conf, "has_2d_drawing", False))
            scale_ok = bool(getattr(conf, "step_scale_confirmed", True))
    inp = state.get("inputs")
    tol = getattr(inp, "tolerance_criticality", "Medium") if inp else "Medium"
    volume = getattr(inp, "production_volume", "") if inp else ""
    material = getattr(inp, "material", "") if inp else ""

    if cad:
        assumptions.append("CAD (STEP) was uploaded; geometry-derived metrics are from the analyzed file.")
    else:
        assumptions.append("No CAD file was uploaded; part summary is from bins or user inputs only.")
    if has_2d:
        assumptions.append("A 2D drawing was provided; critical dimensions and tolerances may be referenced there.")
    else:
        assumptions.append("No 2D drawing was provided; tolerance and dimension assumptions are from summary inputs.")
    if scale_ok:
        assumptions.append("STEP scale has been confirmed; dimensions and volumes are in the stated units.")
    else:
        assumptions.append("STEP scale was not confirmed; dimensions and volumes should be verified.")
    assumptions.append(f"Tolerance criticality is {tol}; stack-up and inspection assumptions follow from this.")
    if volume:
        assumptions.append(f"Production volume is {volume}; cost and process selection assumptions reflect this.")
    if material:
        assumptions.append(f"Material is {material}; process and tooling assumptions use this as the resolution source.")
    # Fallback if we have fewer than 4
    fallbacks = [
        "Shop tooling and machine constraints were not specified.",
        "Manufacturing constraints assumed to follow standard industry practice.",
    ]
    for f in fallbacks:
        if len(assumptions) >= 4:
            break
        assumptions.append(f)
    return [_normalize_assumption_formatting(a) for a in assumptions[:4]]


def _soft_fill_assumptions(assumptions: list[str], state: GraphState | None = None) -> list[str]:
    """Soft-fill assumptions to exactly 4 items; use deterministic defaults from state when provided."""

    defaults = (
        build_deterministic_assumptions(state) if state is not None else [
            "Shop tooling and machine constraints were not specified.",
            "No detailed CAD geometry or 2D drawing was provided.",
            "Tolerance stack-up assumptions are based on summary inputs.",
            "Manufacturing constraints assumed to follow standard industry practice.",
        ]
    )

    # Filter out any remaining placeholders before normalizing
    filtered = [a for a in assumptions if not _is_placeholder_line(a)]

    # Normalize existing assumptions
    result = [_normalize_assumption_formatting(a) for a in filtered]

    # Append defaults until 4 total
    default_idx = 0
    while len(result) < 4 and default_idx < len(defaults):
        result.append(defaults[default_idx])
        default_idx += 1

    return result[:4]


def _derive_actions_from_findings(findings: list) -> list[str]:
    """Derive actions from findings when parsing yields empty/insufficient actions.
    
    Args:
        findings: List of Finding objects
        
    Returns:
        List of action strings (max 6)
    """
    actions: list[str] = []
    
    # Generate actions from HIGH/MED findings first
    high_med_findings = [f for f in findings if getattr(f, "severity", "") in ("HIGH", "MEDIUM")]
    for f in high_med_findings[:6]:
        fid = getattr(f, "id", "")
        rec = getattr(f, "recommendation", "")
        if rec:
            # Shorten to one actionable sentence
            rec_clean = rec.split(".")[0].strip()
            if rec_clean:
                if fid:
                    actions.append(f"Address {fid}: {rec_clean}.")
                else:
                    actions.append(rec_clean + ".")
    
    # Add generic actions if fewer than 6
    generic_actions = [
        "Confirm manufacturing volumes align with process selection.",
        "Confirm tolerances and critical dimensions meet functional requirements.",
        "Verify CAM tool reach and accessibility for all features.",
    ]
    
    while len(actions) < 6 and generic_actions:
        actions.append(generic_actions.pop(0))
    
    return actions[:6]


def _generate_deterministic_fallback(findings: list, inputs, state: GraphState | None = None) -> tuple[list[str], list[str]]:
    """Generate deterministic actions and assumptions; assumptions from state flags when state provided."""
    actions = _derive_actions_from_findings(findings)
    if state is not None:
        assumptions = build_deterministic_assumptions(state)
    else:
        assumptions = [
            "Inputs reflect current design intent and requirements.",
            "Numeric tolerances not fully specified in provided inputs.",
            "Shop/tooling constraints and capabilities unknown.",
        ]
        volume = getattr(inputs, "production_volume", "")
        if volume == "Proto":
            assumptions.append("Prototype volume implies low batch size and higher per-unit cost tolerance.")
        else:
            assumptions.append("Production volume assumptions may affect process selection and cost.")
        assumptions = assumptions[:4]
    return actions[:6], assumptions


def explain_node(state: GraphState) -> dict:
    findings = state.get("findings", [])
    if not findings and not state.get("rag_enabled"):
        return {
            "trace": ["explain: skipping LLM explanation (no findings & RAG disabled)"],
            "actions": ["No major issues detected based on provided summary."],
            "assumptions": [],
        }

    # Single source of truth: CNCR_OFFLINE disables cloud only; local Ollama remains allowed.
    settings = resolve_llm_settings()
    llm_mode = settings.llm_mode
    explain_trace: list[str] = [
        f"explain: effective_llm_mode={llm_mode} offline={1 if settings.offline else 0} cloud_enabled={1 if settings.cloud_enabled else 0} local_enabled={1 if settings.local_enabled else 0}",
        f"explain: provider=ollama base_url={settings.ollama_base_url} model={settings.ollama_model} timeout={settings.timeout_seconds}",
    ]
    for r in settings.reason_trace:
        explain_trace.append(f"explain: {r}")

    def _fallback_no_llm() -> dict:
        state_dict = dict(state) if isinstance(state, dict) else {k: getattr(state, k, None) for k in dir(state) if not k.startswith("_")}
        report_markdown = build_fallback_report(state_dict)
        existing_trace = state.get("trace", [])
        if not isinstance(existing_trace, list):
            existing_trace = []
        return {
            "report_markdown": report_markdown,
            "trace": existing_trace + explain_trace + ["explain: offline fallback (no LLM)"],
            "actions": [],
            "assumptions": [],
        }

    # Only skip LLM when mode is off, or remote without cloud/key, or hybrid with neither local nor cloud.
    if llm_mode == "off":
        return _fallback_no_llm()
    if llm_mode == "remote" and (not settings.cloud_enabled or not os.getenv("OPENAI_API_KEY")):
        explain_trace.append("explain: remote requested but cloud disabled or no OPENAI_API_KEY → fallback")
        return _fallback_no_llm()
    if llm_mode == "hybrid" and not settings.local_enabled and not settings.cloud_enabled:
        explain_trace.append("explain: hybrid but neither local nor cloud available → fallback")
        return _fallback_no_llm()

    system_tmpl = _read_text(_PROMPTS_DIR / "explain_system.txt")
    user_tmpl = _read_text(_PROMPTS_DIR / "explain_user.txt")
    def _fmt_finding(f):
        buf = f"- [{f.severity}] {f.title}: {f.recommendation}"
        prop = getattr(f, "proposal", None)
        if prop and isinstance(prop, str) and prop.strip():
            buf += f"\n  Proposal: {prop.strip()}"
        steps = getattr(f, "proposal_steps", None)
        if steps and isinstance(steps, list) and steps:
            buf += "\n  Proposal steps:"
            for s in steps[:5]:
                if s and isinstance(s, str) and s.strip():
                    buf += f"\n    - {s.strip()}"
        return buf

    findings_bullets = "\n".join(_fmt_finding(f) for f in findings)
    inputs = state["inputs"]
    process = getattr(inputs, "process", None)
    part_summary_mode = state.get("part_summary_mode") or "bins"
    evidence = state.get("part_metrics_evidence") or {}
    part_metrics = state.get("part_metrics") or {}
    part_features = state.get("part_features") or {}
    evidence_lines: list[str] = []
    if process in ("CNC", "CNC_TURNING") and part_summary_mode == "numeric" and (evidence or part_metrics):
        if isinstance(part_metrics, dict):
            bb = part_metrics.get("bounding_box_mm")
            if isinstance(bb, (list, tuple)) and len(bb) >= 3:
                evidence_lines.append(f"  - bounding_box_mm: {float(bb[0]):.2f}x{float(bb[1]):.2f}x{float(bb[2]):.2f}")
            v = part_metrics.get("volume_mm3")
            if v is not None:
                evidence_lines.append(f"  - volume_mm3: {round(float(v), 2)}")
            v = part_metrics.get("tool_access_proxy")
            if v is not None:
                evidence_lines.append(f"  - tool_access_proxy: {round(float(v), 2)}")
        if isinstance(evidence, dict) and evidence:
            hole_keys = ["hole_count", "hole_max_ld", "hole_max_depth_mm", "hole_diameters_mm"]
            hole_vals = [f"{k}={evidence[k]}" for k in hole_keys if k in evidence]
            if hole_vals:
                evidence_lines.append("  - holes: " + ", ".join(hole_vals))
            pocket_keys = ["pocket_count", "pocket_max_aspect", "pocket_max_depth_mm"]
            pocket_vals = [f"{k}={evidence[k]}" for k in pocket_keys if k in evidence]
            if pocket_vals:
                evidence_lines.append("  - pockets: " + ", ".join(pocket_vals))
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "(none)"
    geometry_evidence_block = build_geometry_evidence_block(state)
    user_prompt = user_tmpl.format(
        material=inputs.material,
        production_volume=inputs.production_volume,
        load_type=inputs.load_type,
        tolerance_criticality=inputs.tolerance_criticality,
        evidence_block=evidence_block,
        geometry_evidence_block=geometry_evidence_block,
        findings_bullets=findings_bullets,
    )
    sources_exist = bool(state.get("sources"))

    # Determine effective model name for cache key based on mode (use resolved settings)
    if llm_mode in ("local", "hybrid"):
        effective_model = settings.ollama_model
    else:
        effective_model = CONFIG.model_name

    # Incorporate CAD/numeric signature so cache invalidates when STEP or evidence changes
    signature_hash = _explain_cache_signature(state)
    base_payload = {
        "model": effective_model,
        "system": system_tmpl,
        "user": user_prompt,
        "explain_signature": signature_hash,
    }
    cache_key = hashlib.sha256(
        json.dumps(base_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    mode_str = state.get("part_summary_mode") or "bins"
    part_provider = state.get("part_metrics_provider") or "none"

    cached_data = None
    if CONFIG.enable_cache:
        cache = _get_cache()
        cached_data = cache.get(cache_key, default=None)
        # Re-validate cached content; treat invalid as cache miss
        if cached_data is not None:
            resp = cached_data.get("resp", "")
            if not _is_valid_content(resp) or not _output_contains_evidence_keys(resp, state):
                cache.delete(cache_key)
                cached_data = None

    if cached_data is not None:
        resp = cached_data.get("resp", "")
        usage = (cached_data.get("usage") or {}).copy()
        usage.pop("cache_hit", None)
        usage.pop("attempts", None)
        usage["cache_hit"] = True
        usage["attempts"] = 0
        trace_msg = (
            "Explanation regenerated after RAG (cache allowed)"
            if sources_exist
            else "Explanation loaded from cache"
        )
        trace_debug = f"explain: cache_hit=True key={cache_key[:8]} mode={mode_str} provider={part_provider}"
        actions, assumptions = _parse_actions_assumptions(resp)
        return {
            "trace": explain_trace + [trace_msg, trace_debug],
            "usage": usage,
            "usage_by_node": {"explain": usage},
            "actions": actions,
            "assumptions": assumptions,
        }

    max_attempts = CONFIG.retry_max_attempts if CONFIG.enable_retry else 1
    provider_used = None
    total_attempts = 0

    def _invoke_remote() -> tuple[str, dict]:
        """Invoke OpenAI."""
        llm = ChatOpenAINoTemperature(model=CONFIG.model_name)
        with get_openai_callback() as cb:
            content = llm.invoke(
                [
                    {"role": "system", "content": system_tmpl},
                    {"role": "user", "content": user_prompt},
                ]
            ).content.strip()
            usage = {
                "provider": "openai",
                "model": CONFIG.model_name,
                "prompt_tokens": getattr(cb, "prompt_tokens", None),
                "completion_tokens": getattr(cb, "completion_tokens", None),
                "total_tokens": getattr(cb, "total_tokens", None),
                "total_cost_usd": getattr(cb, "total_cost", None),
            }
            return content, usage

    def _invoke_local() -> tuple[str, dict]:
        """Invoke Ollama (uses resolved settings)."""
        client = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.timeout_seconds,
        )
        messages = [
            {"role": "system", "content": system_tmpl},
            {"role": "user", "content": user_prompt},
        ]
        # num_ctx=4096 to prevent context truncation; num_predict=550 for repair compatibility
        content = client.chat(messages, options={"num_predict": 550, "num_ctx": 4096})
        usage = {
            "provider": "ollama",
            "model": settings.ollama_model,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "total_cost_usd": None,
        }
        return content, usage

    def _repair_local_output(invalid_output: str, inputs, findings_bullets: str) -> tuple[str, dict]:
        """Repair invalid local output by asking LLM to reformat it.
        
        Args:
            invalid_output: The invalid LLM output to repair
            inputs: Inputs object
            findings_bullets: Formatted findings bullets string
            
        Returns:
            Tuple of (repaired content, usage dict)
        """
        repair_system = "Output EXACTLY two sections with uppercase headers ACTION CHECKLIST and ASSUMPTIONS. Use '-' bullets only. Exactly 6 action bullets and 4 assumption bullets. Do NOT output numeric tolerances, ranges, or ± values unless they appear verbatim in the inputs. No other text."
        
        repair_user = f"""Job context:
- Material: {inputs.material}
- Production volume: {inputs.production_volume}
- Load type: {inputs.load_type}
- Tolerance criticality: {inputs.tolerance_criticality}

Findings:
{findings_bullets}

Previous output (invalid format):
{invalid_output}

Rewrite the previous output into the exact required format."""
        
        client = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.timeout_seconds,
        )
        messages = [
            {"role": "system", "content": repair_system},
            {"role": "user", "content": repair_user},
        ]
        content = client.chat(messages, options={"num_predict": 550, "num_ctx": 4096})
        usage = {
            "provider": "ollama",
            "model": settings.ollama_model,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "total_cost_usd": None,
            "repair_pass": True,
        }
        return content, usage

    def _invoke_local_with_validation() -> tuple[str, dict]:
        """Invoke local and validate content. Raises ValueError if invalid."""
        content, usage = _invoke_local()
        if not _is_valid_content(content):
            logger.warning("explain: local output missing required sections or insufficient bullets — retrying")
            raise ValueError("Local model output invalid: missing required sections or insufficient content")
        return content, usage

    def _invoke() -> tuple[str, dict]:
        """Invoke based on mode: remote, local, or hybrid."""
        nonlocal provider_used
        
        if llm_mode == "remote":
            provider_used = "openai"
            return _invoke_remote()
        elif llm_mode == "local":
            provider_used = "ollama"
            # Local mode: invoke without validation here (validation happens after retries)
            return _invoke_local()
        elif llm_mode == "hybrid":
            # Hybrid: try local first; fallback to OpenAI only when cloud_enabled (not offline)
            try:
                provider_used = "ollama"
                (resp, usage), local_attempts = run_with_retries(
                    "explain (local)",
                    _invoke_local_with_validation,
                    max_attempts,
                    logger,
                    backoff_seconds=CONFIG.retry_backoff_seconds,
                )
                usage["attempts"] = local_attempts
                return resp, usage
            except Exception as e:
                if settings.cloud_enabled:
                    logger.warning(f"Local model failed after retries ({e}), falling back to OpenAI")
                    provider_used = "openai"
                    resp, usage = _invoke_remote()
                    usage["attempts"] = max_attempts + 1
                    return resp, usage
                # Offline: re-raise so caller can use deterministic fallback
                raise
        else:
            # Unknown mode, default to remote
            logger.warning(f"Unknown LLM_MODE={llm_mode}, defaulting to remote")
            provider_used = "openai"
            return _invoke_remote()

    if llm_mode == "local":
        explain_trace.append("explain: attempting local Ollama call...")
    try:
        if llm_mode == "hybrid":
            # Hybrid mode handles retries internally
            resp, usage = _invoke()
            total_attempts = usage.get("attempts", 1)
        else:
            # Remote/local modes use standard retry wrapper
            (resp, usage), attempts = run_with_retries(
                "explain",
                _invoke,
                max_attempts,
                logger,
                backoff_seconds=CONFIG.retry_backoff_seconds,
            )
            total_attempts = attempts
            # Ensure provider_used is set in usage
            if provider_used:
                usage["provider"] = provider_used
    except Exception as e:
        err_msg = str(e)
        # Local or hybrid (offline): log and use deterministic fallback instead of surfacing error
        if llm_mode == "local" or (llm_mode == "hybrid" and not settings.cloud_enabled):
            logger.warning(f"explain: local Ollama failed: {err_msg}")
            explain_trace.append(f"explain: local Ollama failed: {err_msg}")
            state_dict = dict(state) if isinstance(state, dict) else {k: getattr(state, k, None) for k in dir(state) if not k.startswith("_")}
            report_markdown = build_fallback_report(state_dict)
            existing_trace = state.get("trace", [])
            if not isinstance(existing_trace, list):
                existing_trace = []
            return {
                "report_markdown": report_markdown,
                "trace": existing_trace + explain_trace + ["explain: offline fallback (no LLM)"],
                "actions": [],
                "assumptions": [],
            }
        # Non-local (remote or hybrid with cloud): check for connection/DNS errors and use offline fallback
        msg = str(e).lower()
        if (
            "getaddrinfo failed" in msg
            or "connecterror" in msg
            or "connection error" in msg
            or "apiconnectionerror" in msg
            or "name or service not known" in msg
            or "failed to resolve" in msg
            or "network" in msg and "error" in msg
        ):
            state_dict = dict(state) if isinstance(state, dict) else {k: getattr(state, k, None) for k in dir(state) if not k.startswith("_")}
            report_markdown = build_fallback_report(state_dict)
            existing_trace = state.get("trace", [])
            if not isinstance(existing_trace, list):
                existing_trace = []
            return {
                "report_markdown": report_markdown,
                "trace": existing_trace + ["explain: connection error -> offline fallback"],
                "actions": [],
                "assumptions": [],
            }
        # Other errors: return error as before
        return {
            "error": Error(
                node="explain",
                type=type(e).__name__,
                message=str(e),
                retry_exhausted=True,
            ),
        }
    usage["cache_hit"] = False
    usage["attempts"] = total_attempts
    if provider_used:
        usage["provider"] = provider_used
    provider_str = usage.get("provider", "unknown")
    
    # Validate before caching (prevent caching invalid responses)
    is_valid = _is_valid_content(resp) and _output_contains_evidence_keys(resp, state)
    use_fallback = False
    repair_used = False
    deterministic_added = False
    placeholder_detected = False
    
    # LLM-first self-healing: try repair pass if invalid and local mode
    if not is_valid and llm_mode == "local":
        invalid_reason = "format" if "```" in resp or not _is_valid_content(resp.replace("```", "")) else "invented tolerances" if _contains_invented_tolerances(resp) else "format"
        logger.warning(f"explain: local output invalid ({invalid_reason}), running LLM repair pass")
        try:
            repaired_resp, repair_usage = _repair_local_output(resp, inputs, findings_bullets)
            if _is_valid_content(repaired_resp) and _output_contains_evidence_keys(repaired_resp, state):
                logger.info("explain: repair pass succeeded")
                resp = repaired_resp
                repair_used = True
                # Merge repair usage info (mark as repair)
                usage["repair_pass"] = True
                is_valid = True
            else:
                logger.warning("explain: repair failed; using deterministic fallback")
        except Exception as e:
            logger.warning(f"explain: repair pass failed ({e}); using deterministic fallback")
    
    if not is_valid:
        logger.warning("explain: using deterministic checklist completion after LLM output validation failure")
        use_fallback = True
        # Generate deterministic fallback from findings (last resort, never crash)
        try:
            actions, assumptions = _generate_deterministic_fallback(findings, inputs, state)
            # Normalize, deduplicate, and ensure exactly 6
            actions = _normalize_checklist_items(actions)
            actions = _deduplicate_actions(actions)
            actions, _ = _fill_checklist_to_six(actions, findings)
            assumptions = _soft_fill_assumptions(assumptions, state)
            # Create a formatted response string for caching (deterministic fallback should be cached)
            fallback_resp = "ACTION CHECKLIST\n" + "\n".join(f"- {a}" for a in actions) + "\n\nASSUMPTIONS\n" + "\n".join(f"- {a}" for a in assumptions)
            resp = fallback_resp
        except Exception as e:
            logger.error(f"explain: deterministic fallback failed ({e}); using minimal fallback")
            actions = ["Review findings and apply recommended DFM improvements."]
            # Normalize and fill to 6
            actions = _normalize_checklist_items(actions)
            actions, _ = _fill_checklist_to_six(actions, findings)
            assumptions = _soft_fill_assumptions(["Inputs reflect current design intent."], state)
            resp = "ACTION CHECKLIST\n" + "\n".join(f"- {a}" for a in actions) + "\n\nASSUMPTIONS\n" + "\n".join(f"- {a}" for a in assumptions)
    else:
        actions, assumptions = _parse_actions_assumptions(resp)
        
        # Check if raw response contains placeholder markers (detect contamination before filtering)
        resp_lower = resp.lower()
        placeholder_markers = ["<", "todo", "tbd", "placeholder", "assumpction"]
        placeholder_detected = any(marker in resp_lower for marker in placeholder_markers)
        
        # Deduplicate actions (preserve LLM priority - only remove duplicates)
        actions = _deduplicate_actions(actions)
        
        # Soft-fill assumptions to exactly 4 (preserve LLM-generated, append deterministic defaults from state)
        assumptions = _soft_fill_assumptions(assumptions, state)
        
        # Check if parsed actions are empty or too short when findings exist
        # Only fill missing slots, never replace valid LLM output
        llm_action_count = len(actions)
        deterministic_added = False
        
        if findings and (not actions or len(actions) < 2):
            logger.warning("explain: parsed actions empty; deriving actions from findings")
            logger.debug(f"explain: raw response preview (first 200 chars): {resp[:200]}")
            # Derive actions from findings (only fills missing slots)
            derived_actions = _derive_actions_from_findings(findings)
            if derived_actions:
                # Preserve any valid LLM actions, append derived ones
                actions = actions + derived_actions[len(actions):]
                actions = actions[:6]
                deterministic_added = True
            # Mark that we're not caching invalid/unstable content
            is_valid = False  # Prevent caching since parsing failed
        elif len(actions) < 6 and findings and llm_action_count < 4:
            # Only add deterministic if LLM provided fewer than 4 actions
            # Fill remaining slots (preserve LLM priority)
            derived_actions = _derive_actions_from_findings(findings)
            # Only append actions that don't duplicate existing ones
            existing_norms = {_normalize_for_dedup(a) for a in actions}
            for derived in derived_actions:
                if len(actions) >= 6:
                    break
                if _normalize_for_dedup(derived) not in existing_norms:
                    actions.append(derived)
                    existing_norms.add(_normalize_for_dedup(derived))
                    deterministic_added = True
        # Note: Final fill to 6 happens after normalization (see below)
    
    # Normalize checklist items (ensure complete imperative sentences)
    actions = _normalize_checklist_items(actions)
    
    # Deduplicate
    actions = _deduplicate_actions(actions)
    
    # Fill to exactly 6 items if needed
    fill_occurred = False
    if len(actions) < 6 and findings:
        actions, fill_occurred = _fill_checklist_to_six(actions, findings)
    
    # Truncate to 6 if more
    actions = actions[:6]
    
    # Ensure assumptions are properly formatted (use state-based defaults when filling)
    assumptions = _soft_fill_assumptions(assumptions[:4], state)
    
    # Optional: truncate very long actions at sentence boundary
    truncated_actions = []
    for action in actions:
        if len(action) > 160:
            # Find last sentence boundary before 160 chars
            truncated = action[:160]
            last_period = truncated.rfind(".")
            last_exclamation = truncated.rfind("!")
            last_question = truncated.rfind("?")
            last_boundary = max(last_period, last_exclamation, last_question)
            if last_boundary > 100:  # Only truncate if reasonable boundary found
                truncated_actions.append(action[:last_boundary + 1])
            else:
                truncated_actions.append(action)
        else:
            truncated_actions.append(action)
    actions = truncated_actions
    
    # Trace messages for polishing
    polish_trace = []
    if fill_occurred:
        polish_trace.append("explain: filled checklist from findings to reach 6 items")
    # Always add polish trace if we have actions/assumptions (normalization happened)
    if actions:
        polish_trace.append("explain: polished checklist grammar and formatting")
    
    trace_msgs = list(explain_trace)
    provider_used_str = usage.get("provider", "unknown")
    base_msg = (
        f"Explanation regenerated after RAG (via {provider_used_str})"
        if sources_exist
        else f"Generated explanation via {provider_used_str}"
    )
    trace_msgs.append(base_msg)
    trace_msgs.append(
        f"explain: cache_hit=False key={cache_key[:8]} mode={mode_str} provider={part_provider}"
    )
    
    if repair_used:
        trace_msgs.append("explain: repair pass succeeded")
    elif use_fallback:
        trace_msgs.append("explain: using deterministic checklist completion after LLM output validation failure")
    elif deterministic_added:
        trace_msgs.append("explain: checklist partially completed deterministically after LLM output")
    
    # Add placeholder detection trace if detected
    if placeholder_detected:
        trace_msgs.append("explain: detected placeholder assumptions; using deterministic defaults")
    
    # Add polishing trace messages
    trace_msgs.extend(polish_trace)
    
    # Use placeholder_detected (already computed from raw response) for caching decision
    # Only cache if content is valid AND produces usable actions (>= 2 actions) AND no placeholders
    should_cache = CONFIG.enable_cache and is_valid and len(actions) >= 2 and not placeholder_detected
    if not should_cache and CONFIG.enable_cache:
        if not is_valid:
            logger.debug("explain: not caching invalid/unstable content")
        elif placeholder_detected:
            logger.debug("explain: not caching placeholder-contaminated content")
    
    if should_cache:
        cache = _get_cache()
        usage_for_cache = {k: v for k, v in usage.items() if k not in ("cache_hit", "attempts")}
        cache.set(
            cache_key,
            {"resp": resp, "usage": usage_for_cache},
            expire=CONFIG.cache_ttl_seconds,
        )
    return {
        "trace": trace_msgs,
        "usage": usage,
        "usage_by_node": {"explain": usage},
        "actions": actions,
        "assumptions": assumptions,
    }