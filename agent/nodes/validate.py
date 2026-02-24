from __future__ import annotations

from agent.state import GraphState


def validate_node(state: GraphState) -> dict:
    # Do not overwrite part_summary: Streamlit builds it (with cad_or_manual); validate only
    if state.get("_summary_source") == "ui_final":
        if "inputs" not in state or "part_summary" not in state:
            raise ValueError("Missing required fields: inputs and/or part_summary")
        return {"trace": ["Inputs validated"]}

    existing = state.get("part_summary")
    if existing is not None:
        if "inputs" not in state:
            raise ValueError("Missing required field: inputs")
        return {"trace": ["Inputs validated"]}

    if "inputs" not in state or "part_summary" not in state:
        raise ValueError("Missing required fields: inputs and/or part_summary")

    return {"trace": ["Inputs validated"]}