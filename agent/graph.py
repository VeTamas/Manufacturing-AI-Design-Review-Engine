from __future__ import annotations

from agent.config import CONFIG
from agent.nodes.decision import decision_node, _route_decision
from agent.nodes.explain import explain_node
from agent.nodes.process_selection import process_selection_node
from agent.nodes.rag import rag_node
from agent.nodes.refine import refine_node, should_run_refine
from agent.nodes.report import report_node
from agent.nodes.rules import rules_node
from agent.nodes.self_review import self_review_node
from agent.nodes.validate import validate_node
from agent.state import GraphState
from langgraph.graph import START, END, StateGraph


def _should_run_rag(state: GraphState) -> str:
    """Conditional edge: run RAG if enabled or HIGH severity findings exist."""
    findings = state.get("findings", [])
    rag_enabled = state.get("rag_enabled", False)
    has_high = any(f.severity == "HIGH" for f in findings)
    return "rag" if (rag_enabled or has_high) else "report"


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("validate", validate_node)
    g.add_node("process_selection", process_selection_node)
    g.add_node("rules", rules_node)
    g.add_node("explain", explain_node)
    g.add_node("decision", decision_node)
    g.add_node("rag", rag_node)
    g.add_node("refine", refine_node)
    g.add_node("self_review", self_review_node)
    g.add_node("report", report_node)

    g.add_edge(START, "validate")
    g.add_edge("validate", "process_selection")
    g.add_edge("process_selection", "rules")
    
    # Sanity check: ensure process_selection node was added
    # Note: LangGraph doesn't expose nodes directly pre-compile, but edges verify node existence
    # If process_selection wasn't added, add_edge would raise an error

    if CONFIG.enable_llm_explain:
        g.add_edge("rules", "explain")
        g.add_edge("explain", "decision")
        g.add_conditional_edges(
            "decision",
            _route_decision,
            {
                "rag": "rag",
                "reassess": "explain",
                "accept": "self_review",
            },
        )
        def _after_rag(state: GraphState) -> str:
            return "refine" if should_run_refine(state) else "explain"

        g.add_conditional_edges("rag", _after_rag, {"refine": "refine", "explain": "explain"})
        g.add_edge("refine", "explain")
        g.add_edge("self_review", "report")
    else:
        g.add_edge("rules", "report")

    g.add_edge("report", END)
    return g.compile()