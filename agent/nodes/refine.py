"""Refine node: bounded LLM pass after RAG to expand Top priorities and Action checklist."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from agent.config import CONFIG
from agent.geometry.evidence_for_llm import build_geometry_evidence_block
from agent.llm import ChatOpenAINoTemperature
from agent.llm.ollama_client import OllamaClient
from agent.state import GraphState
from agent.utils.retry import run_with_retries

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _read_text(path: Path) -> str:
    from agent.utils.filetrace import traced_read_text
    return traced_read_text(path, encoding="utf-8")


def _parse_refine_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if m:
        raw = m.group(1).strip()
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


def refine_node(state: GraphState) -> dict:
    """Run one bounded LLM pass to refine Top priorities (max 6) and Action checklist (max 10).

    Uses retrieved RAG sources; adds decision_rationale when process was a close call.
    Does not invent geometry facts; keeps deterministic findings unchanged.
    """
    findings = state.get("findings", [])
    sources = state.get("sources", [])
    proc_rec = state.get("process_recommendation") or {}
    forced_primary = bool(proc_rec.get("forced_primary"))
    primary = proc_rec.get("primary") or "CNC"
    secondary = proc_rec.get("secondary") or []

    trace_delta = ["refine: entered"]
    llm_mode = (os.getenv("LLM_MODE") or getattr(CONFIG, "llm_mode", "remote")).strip().lower()
    if llm_mode not in ("local", "hybrid", "remote"):
        llm_mode = "remote"

    # Build context from findings and sources (snippets only; no invented geometry)
    findings_text = "\n".join(
        f"- [{f.severity}] {f.title}: {f.recommendation}" for f in findings[:20]
    )
    sources_text = ""
    if sources:
        for i, s in enumerate(sources[:15], 1):
            content = (s.get("content") or s.get("text") or "").strip()
            src_name = s.get("source") or s.get("filename") or "snippet"
            if content:
                sources_text += f"\n[{i}] {src_name}: {content[:400]}\n"
    if not sources_text:
        sources_text = "(No RAG snippets available.)"

    geometry_block = build_geometry_evidence_block(state)
    scores = proc_rec.get("scores") or {}
    second_process = next(
        (p for p in sorted(scores, key=lambda x: scores.get(x, 0), reverse=True) if p != primary),
        None,
    ) if primary else None
    score_diff = (scores.get(primary, 0) - scores.get(second_process, 0)) if (primary and second_process) else 0

    close_call_note = ""
    if forced_primary and secondary:
        close_call_note = (
            f" Process selection was a close call: primary={primary}, secondary={secondary}, score_diff={score_diff}. "
            "decision_rationale MUST be a single string with three parts separated by semicolons: "
            "(1) Why primary was chosen, citing numeric metrics (e.g. flatness, score_diff); "
            "(2) Why secondary was rejected; "
            "(3) What metric change would flip the decision. Base ONLY on the geometry/metrics above; do not invent."
        )

    system = (
        "You are a manufacturing review assistant. Output ONLY valid JSON with these exact keys: "
        '"top_priorities" (array of strings, max 5), "action_checklist" (array of strings, max 10), '
        '"decision_rationale" (string or null). '
        "top_priorities MUST be structured: include at least one geometry risk (mention flatness/thinness/t_over_min_dim or extrusion/turning likelihood), "
        "one manufacturability risk, and one process decision risk where relevant. Use the provided geometry metrics; do not invent. "
        "decision_rationale when present: three parts (why primary numeric, why secondary rejected, what metric would flip). "
        "No markdown, no code fences."
    )
    user = (
        geometry_block
        + "\n\nFindings:\n"
        + (findings_text or "None.")
        + "\n\nRAG snippets:\n"
        + sources_text
        + "\n\n"
        + (close_call_note or "Produce top_priorities (max 5, structured: geometry/manufacturability/process risk) and action_checklist from the above.")
    )

    def _invoke_local() -> str:
        client = OllamaClient(
            base_url=CONFIG.ollama_base_url,
            model=CONFIG.ollama_model,
            timeout_seconds=CONFIG.llm_timeout_seconds,
        )
        return client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            options={"temperature": 0.2, "num_ctx": 2048, "num_predict": 600},
        ).strip()

    def _invoke_remote() -> str:
        llm = ChatOpenAINoTemperature(model=CONFIG.model_name, temperature=0.0)
        resp = llm.invoke(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        return resp.content.strip() if hasattr(resp, "content") else str(resp)

    refined_priorities: list[str] = []
    refined_action_checklist: list[str] = []
    decision_rationale: str | None = None

    try:
        if llm_mode == "local":
            trace_delta.append("refine: attempting local Ollama call")
            raw, _ = run_with_retries(
                "refine",
                _invoke_local,
                CONFIG.retry_max_attempts if CONFIG.enable_retry else 1,
                logger,
                backoff_seconds=CONFIG.retry_backoff_seconds,
            )
            parsed = _parse_refine_json(raw)
        elif llm_mode == "hybrid":
            try:
                trace_delta.append("refine: attempting local Ollama call")
                raw, _ = run_with_retries(
                    "refine (local)",
                    _invoke_local,
                    CONFIG.retry_max_attempts if CONFIG.enable_retry else 1,
                    logger,
                    backoff_seconds=CONFIG.retry_backoff_seconds,
                )
                parsed = _parse_refine_json(raw)
            except Exception as e:
                logger.warning(f"Refine local failed ({e}); using remote")
                raw = _invoke_remote()
                parsed = _parse_refine_json(raw)
        else:
            raw = _invoke_remote()
            parsed = _parse_refine_json(raw)

        if parsed:
            refined_priorities = parsed.get("top_priorities") or []
            if not isinstance(refined_priorities, list):
                refined_priorities = []
            refined_priorities = [str(x).strip() for x in refined_priorities if str(x).strip()][:5]
            refined_action_checklist = parsed.get("action_checklist") or []
            if not isinstance(refined_action_checklist, list):
                refined_action_checklist = []
            refined_action_checklist = [
                str(x).strip() for x in refined_action_checklist if str(x).strip()
            ][:10]
            dr = parsed.get("decision_rationale")
            decision_rationale = str(dr).strip() if dr else None
            trace_delta.append(
                f"refine: produced priorities={len(refined_priorities)} actions={len(refined_action_checklist)}"
            )
        else:
            trace_delta.append("refine: LLM output could not be parsed; skipping refined sections")
    except Exception as e:
        logger.warning("Refine node failed: %s", e, exc_info=True)
        trace_delta.append(f"refine: failed ({e}); skipping refined sections")

    return {
        "trace": trace_delta,
        "refined_priorities": refined_priorities,
        "refined_action_checklist": refined_action_checklist,
        "decision_rationale": decision_rationale,
    }


def should_run_refine(state: GraphState) -> bool:
    """True if refine should run: RAG was used (sources) or close call or any HIGH finding."""
    sources = state.get("sources") or []
    proc_rec = state.get("process_recommendation") or {}
    has_sources = len(sources) > 0
    close_call = bool(proc_rec.get("forced_primary"))
    findings = state.get("findings") or []
    has_high = any(getattr(f, "severity", "") == "HIGH" for f in findings)
    return has_sources or close_call or has_high
