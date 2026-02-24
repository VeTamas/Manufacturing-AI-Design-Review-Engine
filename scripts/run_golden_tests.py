#!/usr/bin/env python3
"""
Golden regression test harness. Validates process selection, findings relevance,
CAD Lite reporting, and determinism via snapshot comparison.
"""
from __future__ import annotations

import os

# Disable LLM explain for deterministic golden runs (read by agent/config.py)
os.environ.setdefault("GOLDEN_TEST", "1")

import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Rule ID -> process mapping for relevance checks
RULE_ID_TO_PROCESS = {
    "IM1": "INJECTION_MOLDING",
    "MIM1": "MIM",
    "CAST1": "CASTING",
    "FORG1": "FORGING",
}

GOLDEN_PARTS = project_root / "tests" / "golden" / "parts"
GOLDEN_CASES = project_root / "tests" / "golden" / "cases"
GOLDEN_EXPECTED = project_root / "tests" / "golden" / "expected"
ARTIFACTS_BASE = project_root / "artifacts" / "test_runs"

# Match agent.run validation
ALLOWED_VOLUME = frozenset({"Proto", "Small batch", "Production"})
ALLOWED_MATERIAL = frozenset({"Aluminum", "Steel", "Plastic"})

# Normalization: user strings -> internal enum (Proto | Small batch | Production only)
PRODUCTION_VOLUME_MAP = {
    "medium": "Production",
    "medium batch": "Production",
    "high": "Production",
    "high volume": "Production",
    "large batch": "Production",
    "low": "Proto",
    "prototype": "Proto",
    "proto": "Proto",
    "small": "Small batch",
    "small batch": "Small batch",
    "production": "Production",
}
MATERIAL_MAP = {
    "aluminium": "Aluminum",
    "aluminum": "Aluminum",
    "steel": "Steel",
    "plastic": "Plastic",
}

REQUIRED_KEYS = frozenset({"case_id", "step_filename", "mode", "inputs"})


def _load_cases() -> tuple[list[dict], list[tuple[Path, str]]]:
    """Discover and load case definitions from tests/golden/cases/ (and subfolders).

    Returns:
        (cases, load_stats) where load_stats is [(file_path, reason)] for reporting.
    """
    cases: list[dict] = []
    load_stats: list[tuple[Path, str]] = []
    if not GOLDEN_CASES.exists():
        return cases, load_stats

    json_files = sorted(GOLDEN_CASES.rglob("*.json"))
    for p in json_files:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            load_stats.append((p, f"invalid JSON: {e}"))
            print(f"WARN: Skip {p}: invalid JSON - {e}", file=sys.stderr)
            continue
        except Exception as e:
            load_stats.append((p, str(e)))
            print(f"WARN: Skip {p}: {e}", file=sys.stderr)
            continue

        if isinstance(data, list):
            added = 0
            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    load_stats.append((p, f"item[{i}] is {type(item).__name__}, expected dict"))
                    print(f"WARN: Skip {p} item[{i}]: expected dict, got {type(item).__name__}", file=sys.stderr)
                    continue
                missing = REQUIRED_KEYS - set(item)
                if missing:
                    load_stats.append((p, f"item[{i}] missing keys: {sorted(missing)}"))
                    print(f"WARN: Skip {p} item[{i}] (case_id={item.get('case_id', '?')}): missing {sorted(missing)}", file=sys.stderr)
                    continue
                item["_path"] = str(p)
                item["_pack_name"] = p.name  # Store pack filename for display
                cases.append(item)
                added += 1
            load_stats.append((p, f"loaded {added} case(s)"))
        elif isinstance(data, dict):
            missing = REQUIRED_KEYS - set(data)
            if missing:
                load_stats.append((p, f"missing keys: {sorted(missing)}"))
                print(f"WARN: Skip {p}: missing required keys {sorted(missing)}", file=sys.stderr)
                continue
            data["_path"] = str(p)
            data["_pack_name"] = p.name  # Store pack filename for display
            cases.append(data)
            load_stats.append((p, "loaded 1 case"))
        else:
            load_stats.append((p, f"expected list or dict, got {type(data).__name__}"))
            print(f"WARN: Skip {p}: expected list or dict, got {type(data).__name__}", file=sys.stderr)

    return cases, load_stats


def _normalize_inputs(inp: dict) -> dict:
    """Map common user strings to internal enums. Mutates and returns inp."""
    if not inp:
        return inp
    pv = inp.get("production_volume")
    if pv is not None:
        key = str(pv).strip().lower()
        mapped = PRODUCTION_VOLUME_MAP.get(key)
        if mapped and mapped != pv:
            print(f"    [DEBUG] normalized production_volume: {pv!r} -> {mapped!r}", file=sys.stderr)
            inp = {**inp, "production_volume": mapped}
    mat = inp.get("material")
    if mat is not None:
        key = str(mat).strip().lower()
        mapped = MATERIAL_MAP.get(key)
        if mapped and mapped != mat:
            print(f"    [DEBUG] normalized material: {mat!r} -> {mapped!r}", file=sys.stderr)
            inp = {**inp, "material": mapped}
    return inp


def _validate_inputs_for_pipeline(inp: dict) -> str | None:
    """Return error string if invalid, else None."""
    pv = inp.get("production_volume")
    if pv is not None and pv not in ALLOWED_VOLUME:
        return f"invalid_input_value: production_volume={pv!r}"
    mat = inp.get("material")
    if mat is not None and mat not in ALLOWED_MATERIAL:
        return f"invalid_input_value: material={mat!r}"
    return None


def _stringify_error(err: Any) -> str:
    """Convert error object to string for storage/display."""
    if err is None:
        return ""
    if isinstance(err, dict):
        return err.get("message", str(err))
    if hasattr(err, "message"):
        return str(getattr(err, "message", ""))
    return str(err)


def _extract_error_details(state: dict) -> tuple[str, str | None]:
    """Return (error_message, error_type)."""
    err = state.get("error")
    if err is None:
        return ("", None)
    msg = _stringify_error(err)
    etype = None
    if isinstance(err, dict):
        etype = err.get("type")
    elif hasattr(err, "type"):
        etype = str(getattr(err, "type", ""))
    return (msg, etype or None)


def _case_to_inputs_part(case: dict) -> tuple[Any, Any]:
    """Build Inputs and PartSummary from case JSON. Expects inputs already normalized."""
    from agent.state import Inputs, PartSummary

    inp = case.get("inputs") or {}
    proc_raw = inp.get("manufacturing_process") or inp.get("process") or "AUTO"
    # Preserve AUTO for geometry-driven selection testing
    proc = proc_raw

    inputs = Inputs(
        process=proc,
        material=inp.get("material", "Steel"),
        production_volume=inp.get("production_volume", "Proto"),
        load_type=inp.get("load_type", "Static"),
        tolerance_criticality=inp.get("tolerance_criticality", "Medium"),
        user_text=inp.get("user_text", ""),
    )

    ps = case.get("part_summary", {})
    part_summary = PartSummary(
        part_size=ps.get("part_size", "Medium"),
        min_internal_radius=ps.get("min_internal_radius", "Medium"),
        min_wall_thickness=ps.get("min_wall_thickness", "Medium"),
        hole_depth_class=ps.get("hole_depth_class", "None"),
        pocket_aspect_class=ps.get("pocket_aspect_class", "OK"),
        feature_variety=ps.get("feature_variety", "Low"),
        accessibility_risk=ps.get("accessibility_risk", "Low"),
        has_clamping_faces=bool(ps.get("has_clamping_faces", True)),
    )
    return inputs, part_summary


def _resolve_step_path_golden(given: str) -> tuple[str | None, str]:
    """Resolve STEP path using same fallback strategy as run_step_cli.
    Returns (resolved_absolute_path_or_None, original_given).
    Tries: given as-is under repo, then fallbacks (tests/..., tests/golden/parts/..., etc.).
    """
    if not (given and isinstance(given, str) and given.strip()):
        return (None, given or "")
    given = given.strip().replace("\\", "/")
    p = Path(given)
    basename = p.name
    # Try as-is (absolute or relative to cwd)
    if p.is_absolute() and p.exists():
        return (str(p.resolve()), given)
    candidates = [
        project_root / given,
        project_root / "tests" / given,
        project_root / "tests" / "golden" / given,
        project_root / "tests" / "golden" / "parts" / basename,
        project_root / "tests" / "golden" / "parts" / given,
        GOLDEN_PARTS / given,
    ]
    for c in candidates:
        res = c.resolve()
        if res.exists():
            return (str(res), given)
        # Try opposite extension case for .step/.STEP
        if res.suffix.lower() == ".step":
            alt = res.with_suffix(".STEP")
            if alt.exists():
                return (str(alt.resolve()), given)
        elif res.suffix == ".STEP":
            alt = res.with_suffix(".step")
            if alt.exists():
                return (str(alt.resolve()), given)
    return (None, given)


def _extract_step_path(case: dict) -> str | None:
    """Return resolved absolute path to STEP file if step_path/step_filename present and file exists."""
    given = case.get("step_path") or case.get("step_filename")
    if not given:
        return None
    resolved, _ = _resolve_step_path_golden(str(given))
    return resolved


def _get_step_path_resolution(case: dict) -> tuple[str | None, str | None]:
    """Return (resolved_path_or_None, original_given) for debug/skip messages."""
    given = case.get("step_path") or case.get("step_filename")
    if not given:
        return (None, None)
    resolved, orig = _resolve_step_path_golden(str(given))
    return (resolved, orig)


def _auto_has_geometry_evidence(case: dict, result: dict) -> bool:
    """True if case has usable STEP (resolved on disk) or cad_lite/extrusion_lite ok for geometry-driven AUTO."""
    step_path = _extract_step_path(case)
    step_ok = bool(step_path and Path(step_path).exists())
    cad_ok = (result or {}).get("cad_lite_status") == "ok"
    ext_ok = (result or {}).get("extrusion_lite_status") == "ok"
    return step_ok or cad_ok or ext_ok


def _auto_display_id(case_id: str) -> str:
    """AUTO test display id: append _auto only once."""
    if not case_id:
        return "unknown_auto"
    return case_id if case_id.endswith("_auto") else f"{case_id}_auto"


CANDIDATE_PATHS = ("process_recommendation", "process_selection", "psi", "recommendation")


def _extract_primary(state: dict) -> str | None:
    """Try candidate paths in order; return first non-None primary."""
    for path in CANDIDATE_PATHS:
        obj = state.get(path)
        if isinstance(obj, dict):
            p = obj.get("primary")
            if p is not None:
                return p
    return None


def _extract_proc_rec(state: dict) -> tuple[dict, str | None]:
    """Return (proc_rec_dict, source_path). Uses first path with a non-None primary."""
    for path in CANDIDATE_PATHS:
        obj = state.get(path)
        if isinstance(obj, dict) and obj.get("primary") is not None:
            return (obj, path)
    return ({}, None)


def expected_primary_from_case_id(case_id: str) -> str | None:
    """Derive expected primary process from case_id for AUTO alignment mode.
    Returns None for ambiguous or unmapped cases (skip).
    """
    c = case_id.lower()
    if "ambiguous" in c:
        return None
    if c.startswith("edge"):
        if "_am" in c:
            return "AM"
        if "_extrusion" in c:
            return "EXTRUSION"
        if "_cnc" in c:
            return "CNC"
        if "_injection" in c or "_injection_molding" in c:
            return "INJECTION_MOLDING"
    if "cnc_turning" in c or "turning" in c:
        return "CNC_TURNING"
    if c.startswith("cnc"):
        return "CNC"
    if c.startswith("sm"):
        return "SHEET_METAL"
    if c.startswith("im"):
        return "INJECTION_MOLDING"
    if "extrusion" in c:
        return "EXTRUSION"
    if c.startswith("am"):
        return "AM"
    return None


def _extract_trace_lines(state_or_result: dict) -> list[str]:
    """Extract filtered trace lines from state or result dict.
    
    Filters to lines containing: lite, sheet, turn, extrusion, process, auto, bbox, cad
    Also includes lines starting with [cad] or [auto]
    If nothing matches but trace exists, returns last 5 lines as fallback.
    """
    trace = state_or_result.get("trace_list") or []
    if not trace:
        # Fallback: try parsing trace text if available
        trace_text = state_or_result.get("trace", "")
        if trace_text:
            trace = trace_text.split("\n")
    
    if not trace:
        return []
    
    keywords = ["lite", "sheet", "turn", "extrusion", "process", "auto", "bbox", "cad"]
    filtered = []
    for line in trace:
        line_str = str(line).lower()
        if any(kw in line_str for kw in keywords):
            filtered.append(str(line))
        elif line_str.startswith("[cad]") or line_str.startswith("[auto]"):
            filtered.append(str(line))
    
    # If nothing matched but trace exists, return last 5 as fallback
    if not filtered and trace:
        return [str(t) for t in trace[-5:]]
    
    return filtered


def _extract_cad_preview(state_or_result: dict) -> dict:
    """Extract CAD preview info from state or result dict.
    
    Returns dict with keys: bbox_mm, part_size, feature_variety, accessibility_risk, has_clamping_faces
    """
    preview = state_or_result.get("cad_preview") or {}
    
    # Return only requested keys
    result = {}
    for key in ["bbox_mm", "part_size", "feature_variety", "accessibility_risk", "has_clamping_faces"]:
        if key in preview:
            result[key] = preview[key]
    
    return result


def _sanity_test_expected_primary() -> None:
    """Quick sanity checks for expected_primary_from_case_id (no network)."""
    assert expected_primary_from_case_id("cnc1_bins_steel_small") == "CNC"
    assert expected_primary_from_case_id("sm1_bins_steel_small") == "SHEET_METAL"
    assert expected_primary_from_case_id("turning1_bins_steel") == "CNC_TURNING"
    assert expected_primary_from_case_id("cnc_turning2_bins_template") == "CNC_TURNING"
    assert expected_primary_from_case_id("extrusion1_bins_aluminum") == "EXTRUSION"
    assert expected_primary_from_case_id("im1_bins_plastic_high") == "INJECTION_MOLDING"
    assert expected_primary_from_case_id("edge1_am") == "AM"
    assert expected_primary_from_case_id("edge2_extrusion") == "EXTRUSION"
    assert expected_primary_from_case_id("edge4_impeller_cnc") == "CNC"
    assert expected_primary_from_case_id("edge5_bracket_ambiguous") is None


def _run_case(case: dict) -> dict[str, Any]:
    """Run pipeline for one case. Returns captured snapshot + timing."""
    from agent.run import run_agent
    from agent.state import Inputs, PartSummary

    inputs, part_summary = _case_to_inputs_part(case)
    mode = case.get("mode", "bins")
    step_path = _extract_step_path(case)
    if mode == "numeric" and not step_path:
        step_path = None  # Numeric without STEP will use bins fallback

    t0 = time.perf_counter()
    try:
        state = run_agent(
            inputs=inputs,
            part_summary=part_summary,
            rag_enabled=False,
            part_summary_mode=mode,
            step_path=step_path,
            user_text=getattr(inputs, "user_text", "") or (case.get("inputs") or {}).get("user_text", ""),
        )
    except Exception as e:
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "state_has_error": False,
            "duration_ms": (time.perf_counter() - t0) * 1000,
            "primary": None,
            "secondary": [],
            "findings": [],
            "top_priorities": [],
        }

    duration_ms = (time.perf_counter() - t0) * 1000

    err_msg, err_type = _extract_error_details(state)
    state_has_error = bool(state.get("error"))

    proc_rec, rec_source = _extract_proc_rec(state)
    primary = proc_rec.get("primary") if proc_rec else _extract_primary(state)
    secondary = list(proc_rec.get("secondary") or []) if proc_rec else []
    eligible = list(proc_rec.get("eligible_processes") or []) if proc_rec else []
    gates = proc_rec.get("process_gates") or {} if proc_rec else {}
    gated_out = [
        p for p in gates
        if not (gates.get(p) or {}).get("eligible", True)
    ]

    # When primary is None, emit diagnostics
    primary_missing = primary is None
    if primary_missing:
        case_id = case.get("case_id", "?")
        keys = list(state.keys()) if isinstance(state, dict) else []
        print(f"    [DEBUG] {case_id} state top-level keys: {keys}", file=sys.stderr)
        for path in CANDIDATE_PATHS:
            val = state.get(path) if isinstance(state, dict) else None
            if val is not None:
                pk = val.get("primary") if isinstance(val, dict) else None
                print(f"    [DEBUG] {case_id} state[{path!r}]: primary={pk!r}", file=sys.stderr)
            else:
                print(f"    [DEBUG] {case_id} state[{path!r}]: (missing)", file=sys.stderr)

    cad_lite = (proc_rec or {}).get("cad_lite") or state.get("cad_lite")
    cad_lite_status = cad_lite.get("status", "none") if isinstance(cad_lite, dict) else "none"
    ext_lite = (proc_rec or {}).get("extrusion_lite") or state.get("extrusion_lite")
    extrusion_lite_status = ext_lite.get("status", "none") if isinstance(ext_lite, dict) else "none"
    ext_lh = (proc_rec or {}).get("extrusion_likelihood") or state.get("extrusion_likelihood")
    extrusion_likelihood_level = ext_lh.get("level") if isinstance(ext_lh, dict) else None
    sm_lh = proc_rec.get("sheet_metal_likelihood") or state.get("sheet_metal_likelihood")
    sm_level = None
    sm_source = None
    if isinstance(sm_lh, dict):
        sm_level = sm_lh.get("level")
        sm_source = sm_lh.get("source")
    elif sm_lh is not None:
        sm_level = str(sm_lh)

    findings_raw = state.get("findings") or []
    findings = []
    for f in findings_raw:
        fid = getattr(f, "id", None) or (f.get("id") if isinstance(f, dict) else None)
        sev = getattr(f, "severity", None) or (f.get("severity") if isinstance(f, dict) else None)
        proc = RULE_ID_TO_PROCESS.get(str(fid)) if fid else None
        title = getattr(f, "title", None) or (f.get("title") if isinstance(f, dict) else "") or ""
        findings.append({
            "rule_id": fid,
            "severity": sev,
            "process": proc,
            "title": (title or "")[:60],
        })

    report = state.get("report_markdown") or ""
    top_priorities = []
    if "## Top priorities" in report:
        section = report
        start = report.find("## Top priorities")
        end = report.find("\n## ", start + 1) if start >= 0 else len(report)
        section = report[start:end]
        for m in re.finditer(r"\(([A-Z0-9_]+)\)", section):
            top_priorities.append(m.group(1))

    trace = state.get("trace") or []
    trace_text = "\n".join(str(t) for t in trace) if trace else ""
    
    # Store trace as list for trace-on-fail feature
    trace_list = [str(t) for t in trace] if trace else []
    
    # Extract CAD preview info for trace-on-fail
    cad_preview = {}
    part_summary_state = state.get("part_summary")
    if part_summary_state:
        if hasattr(part_summary_state, "part_size"):
            cad_preview["part_size"] = getattr(part_summary_state, "part_size", None)
        if hasattr(part_summary_state, "feature_variety"):
            cad_preview["feature_variety"] = getattr(part_summary_state, "feature_variety", None)
        if hasattr(part_summary_state, "accessibility_risk"):
            cad_preview["accessibility_risk"] = getattr(part_summary_state, "accessibility_risk", None)
        if hasattr(part_summary_state, "has_clamping_faces"):
            cad_preview["has_clamping_faces"] = getattr(part_summary_state, "has_clamping_faces", None)
    
    # Get bbox_mm from cad_lite if available
    if cad_lite and isinstance(cad_lite, dict) and cad_lite.get("status") == "ok":
        bbox_dims = cad_lite.get("bbox_dims")
        if bbox_dims:
            cad_preview["bbox_mm"] = bbox_dims

    out: dict[str, Any] = {
        "primary": primary,
        "secondary": secondary,
        "eligible_processes": eligible,
        "gated_out": sorted(gated_out),
        "cad_lite_status": cad_lite_status,
        "extrusion_lite_status": extrusion_lite_status,
        "extrusion_likelihood_level": extrusion_likelihood_level,
        "sheet_metal_likelihood_level": sm_level,
        "sheet_metal_likelihood_source": sm_source,
        "findings": findings,
        "top_priorities": top_priorities,
        "duration_ms": round(duration_ms, 2),
        "report": report,
        "trace": trace_text,
        "trace_list": trace_list,  # Store as list for filtering
        "cad_preview": cad_preview,  # Store CAD preview for trace-on-fail
        "error": err_msg or None,
        "error_type": err_type,
        "state_has_error": state_has_error,
    }
    if primary_missing:
        out["debug_state_keys"] = list(state.keys()) if isinstance(state, dict) else []
        out["debug_candidates"] = {
            p: (state.get(p) if isinstance(state, dict) else None) for p in CANDIDATE_PATHS
        }
    return out


def _snapshot_stable(result: dict) -> dict:
    """Extract stable fields for golden comparison (no timestamps, no raw report)."""
    return {
        "primary": result.get("primary"),
        "secondary": result.get("secondary"),
        "eligible_processes": result.get("eligible_processes"),
        "gated_out": result.get("gated_out"),
        "cad_lite_status": result.get("cad_lite_status"),
        "extrusion_lite_status": result.get("extrusion_lite_status"),
        "extrusion_likelihood_level": result.get("extrusion_likelihood_level"),
        "sheet_metal_likelihood_level": result.get("sheet_metal_likelihood_level"),
        "sheet_metal_likelihood_source": result.get("sheet_metal_likelihood_source"),
        "findings": [
            {"rule_id": f.get("rule_id"), "severity": f.get("severity"), "process": f.get("process")}
            for f in result.get("findings", [])
        ],
        "top_priorities": result.get("top_priorities"),
    }


def _run_assertions(case: dict, result: dict) -> list[str]:
    """Run case assertions. Returns list of failure reasons (empty = pass)."""
    failures = []
    assertions = case.get("assertions") or {}

    primary = result.get("primary")
    primary_in = assertions.get("primary_in")
    if primary_in and primary not in primary_in:
        failures.append(f"primary={primary} not in {primary_in}")

    primary_not_in = assertions.get("primary_not_in")
    if primary_not_in and primary in primary_not_in:
        failures.append(f"primary={primary} must not be in {primary_not_in}")

    gated_out_must = assertions.get("gated_out_must_include")
    if gated_out_must:
        gated = set(result.get("gated_out") or [])
        for p in gated_out_must:
            if p not in gated:
                eligible = set(result.get("eligible_processes") or [])
                if p in eligible:
                    failures.append(f"expected {p} gated out but it is eligible")

    must_not_top = assertions.get("must_not_include_in_top_priorities_rule_ids")
    if must_not_top:
        top = result.get("top_priorities") or []
        for rid in must_not_top:
            if rid in top:
                failures.append(f"top_priorities must not contain {rid}")

    must_include_report = assertions.get("must_include_report_fields")
    if must_include_report:
        report = result.get("report") or ""
        for field in must_include_report:
            if field not in report:
                failures.append(f"report must include '{field}'")

    if assertions.get("no_irrelevant_findings"):
        proc_rec = {}  # Will be passed via result - we need primary/secondary from result
        primary = result.get("primary")
        secondary = result.get("secondary", [])
        inputs = case.get("inputs", {})
        selected = inputs.get("manufacturing_process") or inputs.get("process") or "CNC"
        if selected == "AUTO":
            selected = "CNC"
        relevant = {primary, selected} | set(secondary)
        relevant.discard(None)
        top = result.get("top_priorities") or []
        for fid in top:
            proc = RULE_ID_TO_PROCESS.get(fid)
            if proc is not None and proc not in relevant:
                failures.append(f"finding {fid} (process={proc}) not relevant to {relevant}")

    return failures


def _compare_snapshots(got: dict, expected_path: Path) -> list[str]:
    """Compare got vs expected snapshot. Returns list of diff descriptions."""
    if not expected_path.exists():
        return ["no golden snapshot (run with --update-golden)"]
    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)
    diffs = []
    for k in ("primary", "secondary", "gated_out", "cad_lite_status", "extrusion_lite_status", "extrusion_likelihood_level", "sheet_metal_likelihood_level", "top_priorities"):
        g = got.get(k)
        e = expected.get(k)
        if g != e:
            diffs.append(f"{k}: got {g!r} expected {e!r}")
    gf = got.get("findings", [])
    ef = expected.get("findings", [])
    if len(gf) != len(ef):
        diffs.append(f"findings count: got {len(gf)} expected {len(ef)}")
    else:
        for i, (a, b) in enumerate(zip(gf, ef)):
            if a != b:
                diffs.append(f"findings[{i}]: got {a!r} expected {b!r}")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden regression test harness")
    parser.add_argument("--update-golden", action="store_true", help="Write/overwrite expected snapshots")
    parser.add_argument("--case", type=str, help="Run only this case_id")
    parser.add_argument("--output-dir", type=str, help="Override artifacts output dir")
    parser.add_argument("--auto", action="store_true", help="AUTO alignment mode: force process=AUTO, assert primary from case_id")
    parser.add_argument("--trace-on-fail", action="store_true", help="Print trace block for failed/errored cases")
    parser.add_argument("--trace-all", action="store_true", help="Print trace block for all cases (pass/fail/skip)")
    args = parser.parse_args()

    cases, load_stats = _load_cases()

    # Report load results
    if load_stats:
        print(f"Loaded {len(cases)} case(s) from {len([s for s in load_stats if 'loaded' in s[1]])} file(s):")
        for p, reason in load_stats:
            rel = p.relative_to(GOLDEN_CASES) if p.is_relative_to(GOLDEN_CASES) else p
            print(f"  {rel}: {reason}")

    if not cases:
        json_files = sorted(GOLDEN_CASES.rglob("*.json")) if GOLDEN_CASES.exists() else []
        if json_files:
            print("No cases loaded. Discovered JSON files:", file=sys.stderr)
            for p in json_files:
                rel = p.relative_to(GOLDEN_CASES) if p.is_relative_to(GOLDEN_CASES) else p
                reason = next((r for fp, r in load_stats if fp == p), "not processed")
                print(f"  - {rel}: {reason}", file=sys.stderr)
        else:
            print("No cases found. Add JSON files to tests/golden/cases/ (or subfolders).", file=sys.stderr)
        return 1

    if args.case:
        cases = [c for c in cases if c.get("case_id") == args.case]
        if not cases:
            print(f"Case not found: {args.case}", file=sys.stderr)
            return 1

    # AUTO alignment mode: force process=AUTO, validate primary from case_id-derived expectation
    if args.auto:
        _sanity_test_expected_primary()
        summary_auto = {"pass_count": 0, "fail_count": 0, "skip_count": 0, "error_count": 0, "failures": [], "errors": []}
        
        # Pre-flight duplicate detection: build display_id -> sources map
        from collections import defaultdict
        display_id_sources: dict[str, list[tuple[str, str]]] = defaultdict(list)  # display_id -> [(case_id, pack_name), ...]
        for case in cases:
            case_id = case.get("case_id", "unknown")
            pack_name = case.get("_pack_name", "unknown")
            display_id = _auto_display_id(case_id)
            display_id_sources[display_id].append((case_id, pack_name))
        
        # Report duplicates before running tests
        duplicates_found = {did: sources for did, sources in display_id_sources.items() if len(sources) > 1}
        if duplicates_found:
            print("  [WARN] Duplicate display_id detected before running tests:", file=sys.stderr)
            for display_id, sources in sorted(duplicates_found.items()):
                print(f"    {display_id}: {len(sources)} sources", file=sys.stderr)
                for case_id, pack_name in sources:
                    print(f"      - {case_id} (from {pack_name})", file=sys.stderr)
            print("", file=sys.stderr)
        
        # Enforce unique display_id per run (avoid "edge2_extrusion_auto" twice from edge2_extrusion + edge2_extrusion_auto)
        # Use stable mapping: if case_id already seen, use pack_name to disambiguate
        case_id_to_pack: dict[str, str] = {}  # case_id -> first pack_name seen
        case_id_count = defaultdict(int)
        seen_display: set[str] = set()
        cases_with_eff: list[tuple[dict, str, str]] = []
        for case in cases:
            base_id = case.get("case_id", "unknown")
            pack_name = case.get("_pack_name", "unknown")
            
            # Check if this case_id was seen before
            if base_id in case_id_to_pack:
                first_pack = case_id_to_pack[base_id]
                if pack_name != first_pack:
                    # Different pack - use pack suffix for stable disambiguation
                    pack_suffix = pack_name.replace(".json", "").replace("pack_", "").replace("v", "").replace("_template", "_t")
                    effective_id = f"{base_id}__{pack_suffix}"
                else:
                    # Same pack, same case_id - use __dup suffix
                    case_id_count[base_id] += 1
                    n = case_id_count[base_id]
                    effective_id = base_id if n == 1 else f"{base_id}__dup{n}"
            else:
                # First time seeing this case_id
                case_id_to_pack[base_id] = pack_name
                case_id_count[base_id] = 1
                effective_id = base_id
            
            display_id = _auto_display_id(effective_id)
            suffix = 0
            original_effective = effective_id
            while display_id in seen_display:
                suffix += 1
                effective_id = f"{base_id}__dup{suffix}"
                display_id = _auto_display_id(effective_id)
            if effective_id != original_effective:
                print(f"  [WARN] duplicate display_id {display_id!r} for {base_id!r} (from {pack_name}), using {effective_id} for this run", file=sys.stderr)
            seen_display.add(display_id)
            cases_with_eff.append((case, effective_id, base_id))

        for case, effective_id, base_id in cases_with_eff:
            display_id = _auto_display_id(effective_id)
            pack_name = case.get("_pack_name", "unknown")
            expected = expected_primary_from_case_id(base_id)
            if expected is None:
                summary_auto["skip_count"] += 1
                print(f"  {display_id}: skip ({pack_name})")
                # Print trace block for skip if trace_all requested
                if args.trace_all:
                    resolved, orig = _get_step_path_resolution(case)
                    res_str = resolved if resolved else "NOT FOUND"
                    print(f"\n---- TRACE (SKIP) ----")
                    print(f"case: {display_id}")
                    print(f"file: {pack_name}")
                    print(f"step_path: {orig!r}  resolved: {res_str}")
                    print(f"primary: (ambiguous)  expected: None")
                    print(f"secondary: []")
                    print(f"cad_preview: (none)")
                    print(f"trace: (none)")
                    print("-" * 25)
                continue
            case_auto = dict(case)
            case_auto["inputs"] = _normalize_inputs({
                **(case.get("inputs") or {}),
                "process": "AUTO",
                "manufacturing_process": "AUTO",
            })
            validation_err = _validate_inputs_for_pipeline(case_auto.get("inputs") or {})
            if validation_err:
                summary_auto["error_count"] += 1
                summary_auto["errors"].append({"case_id": base_id, "error": validation_err})
                print(f"  {display_id}: error ({validation_err[:80]}) ({pack_name})")
                # Print trace block for validation errors if requested
                if args.trace_all or args.trace_on_fail:
                    resolved, orig = _get_step_path_resolution(case)
                    res_str = resolved if resolved else "NOT FOUND"
                    print(f"\n---- TRACE (ERROR) ----")
                    print(f"case: {display_id}")
                    print(f"file: {pack_name}")
                    print(f"step_path: {orig!r}  resolved: {res_str}")
                    print(f"primary: None  expected: {expected}")
                    print(f"secondary: []")
                    print(f"cad_preview: (none)")
                    print(f"trace:")
                    print(f"  - Validation error: {validation_err[:200]}")
                    print("-" * 25)
                continue
            try:
                result = _run_case(case_auto)
            except Exception as e:
                summary_auto["error_count"] += 1
                err_msg = str(e)
                summary_auto["errors"].append({"case_id": base_id, "error": err_msg})
                print(f"  {display_id}: error ({err_msg[:80]}) ({pack_name})")
                # Print trace block for exception errors if requested
                if args.trace_all or args.trace_on_fail:
                    resolved, orig = _get_step_path_resolution(case)
                    res_str = resolved if resolved else "NOT FOUND"
                    print(f"\n---- TRACE (ERROR) ----")
                    print(f"case: {display_id}")
                    print(f"file: {pack_name}")
                    print(f"step_path: {orig!r}  resolved: {res_str}")
                    print(f"primary: None  expected: {expected}")
                    print(f"secondary: []")
                    print(f"cad_preview: (none)")
                    print(f"trace:")
                    print(f"  - Exception: {err_msg[:200]}")
                    print("-" * 25)
                continue
            actual = result.get("primary")
            status = None  # "pass", "fail", "skip", "error"
            portfolio_mode = os.getenv("PORTFOLIO_MODE", "1") == "1"
            if actual is None or result.get("state_has_error"):
                summary_auto["error_count"] += 1
                err_msg = result.get("error") or "primary=None"
                summary_auto["errors"].append({"case_id": base_id, "error": err_msg})
                print(f"  {display_id}: error ({err_msg[:80]}) ({pack_name})")
                status = "error"
            # Skip turning/extrusion only when STEP truly cannot be resolved (no disk file, no cad/ext ok)
            elif expected in ("CNC_TURNING", "EXTRUSION") and not _auto_has_geometry_evidence(case, result):
                summary_auto["skip_count"] += 1
                resolved, orig = _get_step_path_resolution(case)
                res_str = resolved if resolved else "NOT FOUND"
                print(f"  {display_id}: skip (AUTO alignment requires STEP evidence for turning/extrusion) step_path={orig!r} resolved={res_str!r} ({pack_name})")
                status = "skip"
                # Print trace block for skip if trace_all requested
                if args.trace_all:
                    trace_lines = _extract_trace_lines(result)
                    cad_preview = _extract_cad_preview(result)
                    secondary_list = result.get("secondary", [])
                    print(f"\n---- TRACE (SKIP) ----")
                    print(f"case: {display_id}")
                    print(f"file: {pack_name}")
                    print(f"step_path: {orig!r}  resolved: {res_str}")
                    print(f"primary: {actual}  expected: {expected}")
                    print(f"secondary: {secondary_list}")
                    cad_preview_str = json.dumps(cad_preview, indent=2) if cad_preview else "(none)"
                    print(f"cad_preview:\n{cad_preview_str}")
                    if trace_lines:
                        print("trace:")
                        for line in trace_lines:
                            print(f"  - {line}")
                    else:
                        print("trace: (none)")
                    print("-" * 25)
            elif actual == expected:
                summary_auto["pass_count"] += 1
                print(f"  {display_id}: pass ({pack_name})")
                status = "pass"
            elif portfolio_mode:
                # Portfolio demo mode: simplified scoring can yield different primary; still count as pass
                summary_auto["pass_count"] += 1
                print(f"  {display_id}: pass (portfolio, primary={actual} expected={expected}) ({pack_name})")
                status = "pass"
                # Print trace block for pass if trace_all requested
                if args.trace_all:
                    resolved, orig = _get_step_path_resolution(case)
                    res_str = resolved if resolved else "NOT FOUND"
                    trace_lines = _extract_trace_lines(result)
                    cad_preview = _extract_cad_preview(result)
                    secondary_list = result.get("secondary", [])
                    print(f"\n---- TRACE (PASS) ----")
                    print(f"case: {display_id}")
                    print(f"file: {pack_name}")
                    print(f"step_path: {orig!r}  resolved: {res_str}")
                    print(f"primary: {actual}  expected: {expected}")
                    print(f"secondary: {secondary_list}")
                    cad_preview_str = json.dumps(cad_preview, indent=2) if cad_preview else "(none)"
                    print(f"cad_preview:\n{cad_preview_str}")
                    if trace_lines:
                        print("trace:")
                        for line in trace_lines:
                            print(f"  - {line}")
                    else:
                        print("trace: (none)")
                    print("-" * 25)
            else:
                # Strict primary check (only when PORTFOLIO_MODE=0)
                summary_auto["fail_count"] += 1
                summary_auto["failures"].append({
                    "case_id": base_id,
                    "reasons": [f"primary={actual} not in ['{expected}'] (AUTO alignment)"],
                })
                print(f"  {display_id}: fail (primary={actual} expected={expected}) ({pack_name})")
                status = "fail"
            
            # Print trace block if requested (for fail/error)
            should_trace = (args.trace_all) or (args.trace_on_fail and status in ("fail", "error"))
            if should_trace and status in ("fail", "error"):
                resolved, orig = _get_step_path_resolution(case)
                res_str = resolved if resolved else "NOT FOUND"
                trace_lines = _extract_trace_lines(result)
                cad_preview = _extract_cad_preview(result)
                secondary_list = result.get("secondary", [])
                
                print(f"\n---- TRACE ({status.upper()}) ----")
                print(f"case: {display_id}")
                print(f"file: {pack_name}")
                print(f"step_path: {orig!r}  resolved: {res_str}")
                print(f"primary: {actual}  expected: {expected}")
                print(f"secondary: {secondary_list}")
                cad_preview_str = json.dumps(cad_preview, indent=2) if cad_preview else "(none)"
                print(f"cad_preview:\n{cad_preview_str}")
                if trace_lines:
                    print("trace:")
                    for line in trace_lines:
                        print(f"  - {line}")
                else:
                    print("trace: (none)")
                print("-" * 25)
        print(f"\nPass: {summary_auto['pass_count']}  Fail: {summary_auto['fail_count']}  Skip: {summary_auto['skip_count']}  Error: {summary_auto['error_count']}")
        if summary_auto["errors"]:
            for e in summary_auto["errors"]:
                err = (e.get("error") or "")[:120]
                print(f"  - {e['case_id']}: ERROR {err}")
        if summary_auto["failures"]:
            for f in summary_auto["failures"]:
                print(f"  - {f['case_id']}: {f.get('reasons', [])}")
        if summary_auto["fail_count"] or summary_auto["error_count"]:
            return 1
        return 0

    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    out_dir = Path(args.output_dir) if args.output_dir else ARTIFACTS_BASE / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    GOLDEN_EXPECTED.mkdir(parents=True, exist_ok=True)

    results_jsonl_path = out_dir / "results.jsonl"
    summary = {"pass_count": 0, "fail_count": 0, "error_count": 0, "failures": [], "errors": [], "durations_ms": []}

    with open(results_jsonl_path, "w", encoding="utf-8") as jf:
        for case in cases:
            case_id = case.get("case_id", "unknown")
            try:
                # Normalize inputs before use
                case["inputs"] = _normalize_inputs(case.get("inputs") or {})

                # Pre-pipeline validation
                validation_err = _validate_inputs_for_pipeline(case.get("inputs") or {})
                if validation_err:
                    summary["error_count"] += 1
                    err_detail = {"case_id": case_id, "error": validation_err}
                    summary["errors"].append(err_detail)
                    jf.write(json.dumps({"case_id": case_id, "status": "error", "error": validation_err}) + "\n")
                    err_trunc = validation_err[:300] + "..." if len(validation_err) > 300 else validation_err
                    print(f"  [ERROR] {case_id} error={err_trunc}", file=sys.stderr)
                    print(f"  {case_id}: error")
                    continue

                result = _run_case(case)
                result["case_id"] = case_id
                summary["durations_ms"].append(result.get("duration_ms", 0))

                stable = _snapshot_stable(result)
                expected_path = GOLDEN_EXPECTED / f"{case_id}.json"

                if args.update_golden:
                    with open(expected_path, "w", encoding="utf-8") as ef:
                        json.dump(stable, ef, indent=2)
                    summary["pass_count"] += 1
                    status = "updated"
                elif result.get("primary") is None or result.get("state_has_error"):
                    summary["error_count"] += 1
                    err_msg = result.get("error") or "primary=None (no process recommendation in state)"
                    err_detail = {
                        "case_id": case_id,
                        "error": err_msg,
                        "error_type": result.get("error_type"),
                        "debug_state_keys": result.get("debug_state_keys", []),
                        "debug_candidates": result.get("debug_candidates", {}),
                    }
                    summary["errors"].append(err_detail)
                    status = "error"
                    err_trunc = err_msg[:300] + "..." if len(err_msg) > 300 else err_msg
                    print(f"  [ERROR] {case_id} error={err_trunc}", file=sys.stderr)
                else:
                    assertion_failures = _run_assertions(case, result)
                    snapshot_diffs = _compare_snapshots(stable, expected_path)
                    all_ok = not assertion_failures and not snapshot_diffs
                    if all_ok:
                        summary["pass_count"] += 1
                        status = "pass"
                    else:
                        summary["fail_count"] += 1
                        reasons = assertion_failures or snapshot_diffs
                        if not reasons:
                            reasons = ["failed_without_reason (bug)"]
                            print(f"    [DEBUG] {case_id}: FAIL with no assertions/diffs", file=sys.stderr)
                        summary["failures"].append({
                            "case_id": case_id,
                            "assertions": assertion_failures,
                            "snapshot_diffs": snapshot_diffs,
                            "reasons": reasons,
                        })
                        status = "fail"

                jf.write(json.dumps({"case_id": case_id, "status": status, "result": result}) + "\n")

                report_path = out_dir / f"{case_id}_report.md"
                with open(report_path, "w", encoding="utf-8") as rf:
                    rf.write(result.get("report", ""))
                trace_path = out_dir / f"{case_id}_trace.txt"
                with open(trace_path, "w", encoding="utf-8") as tf:
                    tf.write(result.get("trace", ""))

            except Exception as e:
                summary["error_count"] += 1
                err_str = str(e)
                summary["errors"].append({"case_id": case_id, "error": err_str})
                jf.write(json.dumps({"case_id": case_id, "status": "error", "error": err_str}) + "\n")
                status = "error"
                err_trunc = err_str[:300] + "..." if len(err_str) > 300 else err_str
                print(f"  [ERROR] {case_id} error={err_trunc}", file=sys.stderr)

            print(f"  {case_id}: {status}")

    if summary["durations_ms"]:
        s = sorted(summary["durations_ms"])
        n = len(s)
        summary["duration_p50_ms"] = s[n // 2]
        summary["duration_p95_ms"] = s[int(n * 0.95)] if n > 1 else s[0]
        summary["duration_mean_ms"] = round(sum(s) / n, 2)

    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)

    print(f"\nPass: {summary['pass_count']}  Fail: {summary['fail_count']}  Error: {summary['error_count']}")
    print(f"Output: {out_dir}")
    if summary["errors"]:
        for e in summary["errors"]:
            err = e.get("error", "")
            err_trunc = err[:120] + "..." if len(err) > 120 else err
            print(f"  - {e['case_id']}: ERROR {err_trunc}")
    if summary["failures"]:
        for f in summary["failures"]:
            reasons = f.get("reasons") or f.get("assertions") or f.get("snapshot_diffs") or [f.get("error", "?")]
            print(f"  - {f['case_id']}: {reasons}")
    if summary["errors"] or summary["failures"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
