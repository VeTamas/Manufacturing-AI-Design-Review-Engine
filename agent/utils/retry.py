"""Retry helper for graph nodes: structured logging and optional error emission."""
from __future__ import annotations

import time
from collections.abc import Callable
from logging import Logger
from typing import TypeVar

T = TypeVar("T")


def run_with_retries(
    node: str,
    fn: Callable[[], T],
    max_attempts: int,
    logger: Logger,
    backoff_seconds: float = 1.0,
) -> tuple[T, int]:
    """
    Run fn up to max_attempts times. Log each failure with exc_info and extra.
    On exhaustion log critical and re-raise.

    Returns:
        (result, attempts_used)
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(), attempt
        except Exception as e:
            last_exc = e
            logger.error(
                "Node %s attempt %s/%s failed: %s",
                node,
                attempt,
                max_attempts,
                str(e),
                exc_info=True,
                extra={"node": node, "attempt": attempt, "max_attempts": max_attempts},
            )
            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)

    logger.critical(
        "Node %s exhausted retries (%s attempts)",
        node,
        max_attempts,
        exc_info=True,
        extra={"node": node, "max_attempts": max_attempts},
    )
    raise last_exc  # type: ignore[misc]
