"""Scoring modules for process selection.

Portfolio demo scoring lives in portfolio_scoring; production scoring
remains in agent.nodes.process_selection (used when PORTFOLIO_MODE=0).
"""
from __future__ import annotations

from agent.scoring.portfolio_scoring import compute_portfolio_recommendation

__all__ = ["compute_portfolio_recommendation"]
