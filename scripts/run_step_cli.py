#!/usr/bin/env python3
"""
Minimal end-user CLI to run the agent pipeline on a single STEP file (bins-first).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

REPORTS_DIR = project_root / "artifacts" / "reports"
ARTIFACTS_DIR = project_root / "artifacts"

# Candidate (module, attrs) for entrypoint discovery
DISCOVERY_CANDIDATES = [
    ("agent.run", ["run_agent", "run", "run_graph"]),
    ("agent.graph", ["run", "run_graph", "build_graph"]),
    ("agent.pipeline", ["run", "run_pipeline"]),
    ("agent.app", ["run", "run_app"]),
    ("agent.main", ["main", "run"]),
    ("agent.nodes.run", ["run"]),
]


def _ensure_dirs() -> None:
    """Ensure artifacts directories exist."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _make_part_summary(overrides: dict | None = None) -> object:
    """Build default PartSummary for bins mode."""
    from agent.state import PartSummary

    o = overrides or {}
    return PartSummary(
        part_size=o.get("part_size", "Medium"),
        min_internal_radius=o.get("min_internal_radius", "Medium"),
        min_wall_thickness=o.get("min_wall_thickness", "Medium"),
        hole_depth_class=o.get("hole_depth_class", "None"),
        pocket_aspect_class=o.get("pocket_aspect_class", "OK"),
        feature_variety=o.get("feature_variety", "Low"),
        accessibility_risk=o.get("accessibility_risk", "Low"),
        has_clamping_faces=bool(o.get("has_clamping_faces", True)),
    )


def _make_inputs(
    process: str = "AUTO",
    material: str = "Steel",
    production_volume: str = "Small batch",
    load_type: str = "Static",
    tolerance_criticality: str = "Medium",
    user_text: str = "",
) -> object:
    """Build Inputs from CLI params."""
    from agent.state import Inputs

    return Inputs(
        process=process,
        material=material,
        production_volume=production_volume,
        load_type=load_type,
        tolerance_criticality=tolerance_criticality,
        user_text=user_text or "",
    )


def _run_via_run_agent(state: dict) -> dict:
    """Adapter: call agent.run.run_agent with state dict."""
    from agent.run import run_agent
    from agent.state import Inputs, PartSummary

    inp = state.get("inputs")
    part = state.get("part_summary")
    if not isinstance(inp, Inputs):
        inp = _make_inputs(
            process=(inp or {}).get("process", "AUTO"),
            material=(inp or {}).get("material", "Steel"),
            production_volume=(inp or {}).get("production_volume", "Small batch"),
            load_type=(inp or {}).get("load_type", "Static"),
            tolerance_criticality=(inp or {}).get("tolerance_criticality", "Medium"),
            user_text=(inp or {}).get("user_text", state.get("user_text", "") or ""),
        )
    if not isinstance(part, PartSummary):
        part = _make_part_summary(part if isinstance(part, dict) else None)
    return run_agent(
        inputs=inp,
        part_summary=part,
        rag_enabled=bool(state.get("rag_enabled", False)),
        part_summary_mode=state.get("part_summary_mode", "bins"),
        step_path=state.get("step_path"),
        user_text=state.get("user_text", "") or state.get("description", ""),
    )


def discover_runner() -> tuple[callable, str]:
    """
    Discover a callable that runs the pipeline. Returns (runner_fn, source).
    runner_fn(state: dict) -> dict with keys including report/process_recommendation/trace.
    """
    import importlib

    attempted = []
    for mod_name, attrs in DISCOVERY_CANDIDATES:
        try:
            mod = importlib.import_module(mod_name)
            for attr in attrs:
                if hasattr(mod, attr):
                    fn = getattr(mod, attr)
                    if callable(fn):
                        attempted.append(f"{mod_name}.{attr}")
                        if mod_name == "agent.run" and attr == "run_agent":
                            return (_run_via_run_agent, f"{mod_name}.{attr}")
                        if mod_name == "agent.graph" and attr == "build_graph":
                            def _run_via_graph(s: dict):
                                g = fn()
                                return g.invoke(s)
                            return (_run_via_graph, f"{mod_name}.{attr}")
        except ImportError:
            attempted.append(f"{mod_name} (import failed)")
        except Exception:
            attempted.append(mod_name)

    sys.stderr.write(
        "No pipeline entrypoint found. Tried: " + ", ".join(attempted) + "\n"
        "Hint: Search for 'GraphState' and 'run_agent' in the repo.\n"
    )
    sys.exit(1)


def discover_runner_safe() -> tuple[callable | None, str]:
    """Same as discover_runner but returns (None, error_msg) instead of exiting."""
    import importlib

    attempted = []
    for mod_name, attrs in DISCOVERY_CANDIDATES:
        try:
            mod = importlib.import_module(mod_name)
            for attr in attrs:
                if hasattr(mod, attr):
                    fn = getattr(mod, attr)
                    if callable(fn):
                        attempted.append(f"{mod_name}.{attr}")
                        if mod_name == "agent.run" and attr == "run_agent":
                            return (_run_via_run_agent, f"{mod_name}.{attr}")
                        if mod_name == "agent.graph" and attr == "build_graph":
                            def _run_via_graph(s: dict):
                                g = fn()
                                return g.invoke(s)
                            return (_run_via_graph, f"{mod_name}.{attr}")
        except ImportError:
            attempted.append(f"{mod_name} (import failed)")
        except Exception:
            attempted.append(mod_name)
    return (None, "Tried: " + ", ".join(attempted))


def run_pipeline(
    step_path: str | Path,
    process: str = "AUTO",
    material: str = "Steel",
    production_volume: str = "Small batch",
    load_type: str = "Static",
    tolerance_criticality: str = "Medium",
    user_text: str = "",
    rag_enabled: bool = False,
    numeric: bool = False,
) -> dict:
    """Run the agent pipeline on a STEP file. Returns state dict."""
    _ensure_dirs()
    step_path = Path(step_path)
    if not step_path.is_absolute():
        step_path = (project_root / step_path).resolve()

    runner, _ = discover_runner()
    inputs = _make_inputs(
        process=process,
        material=material,
        production_volume=production_volume,
        load_type=load_type,
        tolerance_criticality=tolerance_criticality,
        user_text=user_text or "",
    )
    part_summary = _make_part_summary()
    mode = "numeric" if numeric and process in ("CNC", "CNC_TURNING") else "bins"
    state = {
        "step_path": str(step_path),
        "inputs": inputs,
        "part_summary": part_summary,
        "user_text": user_text or "",
        "description": user_text or "",
        "rag_enabled": rag_enabled,
        "part_summary_mode": mode,
    }
    return runner(state)


def _extract_proc_rec(state: dict) -> dict:
    """Extract process recommendation from state."""
    for path in ("process_recommendation", "process_selection", "psi", "recommendation"):
        obj = state.get(path)
        if isinstance(obj, dict) and obj.get("primary") is not None:
            return obj
    return {}


def _extract_top_priorities(report: str) -> list[str]:
    """Extract rule IDs from Top priorities section."""
    out = []
    if "## Top priorities" in report:
        start = report.find("## Top priorities")
        end = report.find("\n## ", start + 1) if start >= 0 else len(report)
        section = report[start:end]
        for m in re.finditer(r"\(([A-Z0-9_]+)\)", section):
            out.append(m.group(1))
    return out


def _extract_findings(state: dict) -> list[dict]:
    """Extract findings as {rule_id, severity, title}."""
    findings_raw = state.get("findings") or []
    out = []
    for f in findings_raw:
        fid = getattr(f, "id", None) or (f.get("id") if isinstance(f, dict) else None)
        sev = getattr(f, "severity", None) or (f.get("severity") if isinstance(f, dict) else None)
        title = getattr(f, "title", None) or (f.get("title") if isinstance(f, dict) else "") or ""
        out.append({"rule_id": fid, "severity": sev, "title": (str(title) or "")[:60]})
    return out


def _state_to_json_safe(state: dict) -> dict:
    """Convert state to JSON-serializable dict."""
    pr = state.get("process_recommendation") or state.get("process_selection")
    pr_clean = {}
    if isinstance(pr, dict):
        for k, v in pr.items():
            if k == "score_breakdown":
                continue
            if isinstance(v, (dict, list, str, int, float, bool, type(None))):
                try:
                    json.dumps(v)
                    pr_clean[k] = v
                except (TypeError, ValueError):
                    pr_clean[k] = str(v)
            else:
                pr_clean[k] = str(v)
    return {
        "process_recommendation": pr_clean,
        "report_markdown": state.get("report_markdown", ""),
        "findings": _extract_findings(state),
        "error": state.get("error") if isinstance(state.get("error"), str) else str(state.get("error", "")),
        "error_type": state.get("error_type"),
        "trace": list(state.get("trace", [])) if isinstance(state.get("trace"), list) else [],
    }


def _resolve_step_path(given: str) -> tuple[Path, bool]:
    """Resolve STEP path. Returns (resolved_path, used_fallback).
    If given path exists, use it. Else try fallbacks 1-6.
    """
    p = Path(given)
    if p.is_absolute() and p.exists():
        return (p.resolve(), False)
    if not p.is_absolute():
        candidate = (project_root / given).resolve()
        if candidate.exists():
            return (candidate, False)
    basename = Path(given).name
    fallbacks = [
        project_root / "tests" / given,
        project_root / "tests" / "parts" / basename,
        project_root / "parts" / basename,
        project_root / "tests" / "golden" / given,
        project_root / "tests" / "golden" / "parts" / basename,
        project_root / "tests" / "golden" / "parts" / given,
    ]
    for fb in fallbacks:
        resolved = fb.resolve()
        if resolved.exists():
            return (resolved, True)
    not_found = (project_root / given).resolve() if not p.is_absolute() else p.resolve()
    return (not_found, False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run agent pipeline on a single STEP file (bins-first)")
    parser.add_argument("step_path", type=str, help="Path to STEP file")
    parser.add_argument("--process", "-p", default="AUTO", help="Manufacturing process (default: AUTO - geometry-driven selection)")
    parser.add_argument("--material", "-m", default="Steel", help="Material (default: Steel)")
    parser.add_argument("--volume", "-v", default="Small batch", dest="production_volume", help="Production volume")
    parser.add_argument("--load", "-l", default="Static", dest="load_type", help="Load type")
    parser.add_argument("--tolerance", "-t", default="Medium", dest="tolerance_criticality", help="Tolerance criticality")
    parser.add_argument("--rag", action="store_true", help="Enable RAG")
    parser.add_argument("--numeric", action="store_true", help="Attempt numeric mode (CNC only)")
    parser.add_argument("--text", type=str, default="", dest="user_text", help="User notes (optional)")
    args = parser.parse_args()

    given = args.step_path
    step_path, used_fallback = _resolve_step_path(given)
    if not step_path.exists():
        print(f"Error: STEP file not found: {given}", file=sys.stderr)
        return 1
    if used_fallback:
        print(f"Resolved STEP path via fallback: {given} -> {step_path}")

    _ensure_dirs()
    stem = step_path.stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        state = run_pipeline(
            step_path=str(step_path),
            process=args.process,
            material=args.material,
            production_volume=args.production_volume,
            load_type=args.load_type,
            tolerance_criticality=args.tolerance_criticality,
            user_text=args.user_text or "",
            rag_enabled=args.rag,
            numeric=args.numeric,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        state = {"error": str(e), "error_type": type(e).__name__}

    if state.get("error"):
        err = state.get("error")
        err_type = state.get("error_type", "")
        print(f"Pipeline error: {err}" + (f" ({err_type})" if err_type else ""))

    proc_rec = _extract_proc_rec(state)
    primary = proc_rec.get("primary")
    secondary = proc_rec.get("secondary") or []
    report = state.get("report_markdown") or ""
    top_priorities = _extract_top_priorities(report)
    findings = _extract_findings(state)

    print("--- Process recommendation ---")
    print(f"Primary:   {primary}")
    print(f"Secondary: {secondary}")
    print("--- Top priorities ---")
    print(" ".join(top_priorities) if top_priorities else "(none)")
    print("--- Findings ---")
    for f in findings:
        sev = f.get("severity") or "?"
        title = (f.get("title") or "")[:50]
        rid = f.get("rule_id") or "?"
        print(f"  [{sev}] {rid}: {title}")

    md_path = REPORTS_DIR / f"{stem}_{ts}.md"
    json_path = REPORTS_DIR / f"{stem}_{ts}.json"
    try:
        md_path.write_text(report, encoding="utf-8")
        json_path.write_text(json.dumps(_state_to_json_safe(state), indent=2), encoding="utf-8")
        print(f"\nReport: {md_path}")
        print(f"State:  {json_path}")
    except OSError as e:
        print(f"Warning: could not write artifacts: {e}", file=sys.stderr)

    return 0 if not state.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
