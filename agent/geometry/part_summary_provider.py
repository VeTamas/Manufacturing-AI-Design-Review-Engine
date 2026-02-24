"""Part summary provider: bins-only or bins + numeric (process-gated)."""
from __future__ import annotations

import logging
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from agent.config import CONFIG
from agent.state import GraphState, PartSummary

logger = logging.getLogger(__name__)

# Required keys for valid numeric metrics (report/cache gating)
REQUIRED_NUMERIC_KEYS = frozenset({"bounding_box_mm", "volume_mm3", "surface_area_mm2"})


def _numeric_metrics_valid(metrics: dict[str, Any] | None) -> bool:
    """Return True only if metrics is non-empty and has required keys."""
    if not metrics or not isinstance(metrics, dict):
        return False
    return REQUIRED_NUMERIC_KEYS <= metrics.keys()


def get_numeric_analyzer(process: str) -> Any | None:
    """Return analyzer for process or None if not supported."""
    from agent.geometry.analyzers import cnc_numeric_v1
    if cnc_numeric_v1.supports(process):
        return cnc_numeric_v1
    return None


def build_bins_summary(state: GraphState) -> PartSummary:
    """Return bins PartSummary from state (existing logic)."""
    return state["part_summary"]


def merge_bins_with_numeric(
    bins: PartSummary,
    metrics: dict[str, Any],
    process: str,
) -> PartSummary:
    """Phase 1: numeric is additive; bins unchanged. Return bins as-is."""
    return bins


def build_part_summary(
    state: GraphState,
) -> tuple[PartSummary, GraphState]:
    """
    Build part summary; if numeric mode and process has analyzer, run numeric analysis
    and store part_metrics. Returns (PartSummary, updated_state_dict).
    """
    bins = build_bins_summary(state)
    mode = state.get("part_summary_mode") or "bins"
    step_path_raw = state.get("step_path")

    if mode != "numeric":
        return bins, {}

    process = getattr(state.get("inputs"), "process", None) if state.get("inputs") else None
    if not process:
        return bins, {}

    analyzer = get_numeric_analyzer(process)
    if analyzer is None:
        return bins, {}

    if not step_path_raw:
        logger.debug("Numeric mode but no step_path; using bins only")
        return bins, {}

    step_path = Path(step_path_raw)
    if not step_path.exists():
        logger.warning("Step path does not exist: %s; using bins only", step_path)
        return bins, {}

    timeout_sec = getattr(CONFIG, "cnc_numeric_timeout_seconds", 3)
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(analyzer.analyze, step_path)
            metrics = future.result(timeout=timeout_sec)
    except FuturesTimeoutError:
        logger.warning(
            "Numeric analysis timed out (%ss); using bins only",
            timeout_sec,
            extra={"numeric_cnc_timeout": True},
        )
        return bins, {
            "part_metrics": None,
            "part_metrics_provider": "numeric_cnc_v1_timeout",
            "part_metrics_evidence": None,
        }
    except Exception as e:
        logger.warning(
            "Numeric analysis failed (%s: %s); using bins only",
            type(e).__name__,
            e,
            extra={"numeric_cnc_error": str(e)},
        )
        return bins, {
            "part_metrics": None,
            "part_metrics_provider": "numeric_cnc_v1_failed",
            "part_metrics_evidence": None,
        }

    if not _numeric_metrics_valid(metrics):
        logger.warning("Numeric analysis returned invalid metrics; using bins only")
        return bins, {
            "part_metrics": None,
            "part_metrics_provider": "numeric_cnc_v1_failed",
            "part_metrics_evidence": None,
        }

    provider = getattr(analyzer, "NAME", "numeric_cnc_v1")
    merged = merge_bins_with_numeric(bins, metrics, process)

    # CNC-only numeric adapter: refine bins and attach evidence when provider is numeric_cnc_v1
    evidence: dict[str, Any] | None = None
    if process in ("CNC", "CNC_TURNING") and provider == "numeric_cnc_v1":
        from agent.geometry.cnc_numeric_adapter import apply_numeric_to_bins
        merged, evidence = apply_numeric_to_bins(merged, metrics)

    # CNC v2: extract hole/pocket features and merge into evidence
    part_features: dict[str, Any] | None = None
    trace_msgs: list[str] = []
    if process in ("CNC", "CNC_TURNING"):
        try:
            from agent.geometry.analyzers.cnc_numeric_v2_features import (
                extract_cnc_features_from_step,
            )
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(extract_cnc_features_from_step, step_path)
                part_features = future.result(timeout=timeout_sec)
            hc = part_features.get("hole_count", 0) if part_features else 0
            pc = part_features.get("pocket_count", 0) if part_features else 0
            hpc = part_features.get("hole_proxy_count", 0) if part_features else 0
            ppc = part_features.get("pocket_proxy_count", 0) if part_features else 0
            if hc == 0 and pc == 0 and (hpc > 0 or ppc > 0):
                trace_msgs.append(f"numeric_v2: fallback_used hole_proxy_count={hpc} pocket_proxy_count={ppc}")
            else:
                trace_msgs.append(f"numeric_v2: analytic_used hole_count={hc} pocket_count={pc}")
            if part_features:
                evidence = evidence or {}
                for k in (
                    "hole_count", "hole_diameters_mm", "hole_max_depth_mm", "hole_max_ld",
                    "pocket_count", "pocket_max_depth_mm", "pocket_max_aspect",
                ):
                    if k in part_features and part_features[k] is not None:
                        evidence[k] = part_features[k]
        except FuturesTimeoutError as e:
            part_features = None
            trace_msgs.append(f"numeric_v2: features_extraction_failed err={type(e).__name__}")
            logger.debug("CNC v2 feature extraction timed out: %s", e)
        except Exception as e:
            part_features = None
            trace_msgs.append(f"numeric_v2: features_extraction_failed err={type(e).__name__}")
            logger.debug("CNC v2 feature extraction skipped: %s", e)

    delta: dict[str, Any] = {
        "part_metrics": metrics,
        "part_metrics_provider": provider,
        "part_summary": merged,
        "part_metrics_evidence": evidence,
        "part_features": part_features,
    }
    if trace_msgs:
        delta["trace"] = trace_msgs
    return merged, delta
