from __future__ import annotations

from agent.nodes.process_selection import _resolve_am_tech
from agent.state import GraphState


def resolve_retrieval_index(process: str, am_tech: str | None = None, state: GraphState | None = None) -> str:
    """
    Resolve process identifier to actual FAISS index name used for retrieval.
    
    Args:
        process: Process identifier (e.g., "CNC", "AM", "MIM")
        am_tech: AM technology if process == "AM" (e.g., "FDM", "METAL_LPBF", "AUTO")
        state: Optional GraphState for auto-resolving AM tech when am_tech == "AUTO"
    
    Returns:
        FAISS index name (lowercase, e.g., "cnc", "am_fdm", "mim")
    """
    process_upper = process.upper()

    # AUTO is not a real index; callers should use recommended primary. Fallback to cnc if ever passed.
    if process_upper == "AUTO":
        return "cnc"

    # Non-AM processes: direct mapping to lowercase
    process_to_index = {
        "CNC": "cnc",
        "CNC_TURNING": "cnc",  # Shares CNC index
        "SHEET_METAL": "sheet_metal",
        "INJECTION_MOLDING": "injection_molding",
        "CASTING": "casting",
        "FORGING": "forging",
        "EXTRUSION": "extrusion",
        "MIM": "mim",
        "THERMOFORMING": "thermoforming",
        "COMPRESSION_MOLDING": "compression_molding",
    }
    
    if process_upper in process_to_index:
        return process_to_index[process_upper]
    
    # AM process: requires tech resolution (FIX 4: safe extraction)
    if process_upper == "AM":
        if am_tech is None or am_tech == "AUTO":
            if state is not None:
                try:
                    inp = state.get("inputs")
                    am_tech_in = getattr(inp, "am_tech", "AUTO") if inp else "AUTO"
                    am_tech, _ = _resolve_am_tech(state, am_tech_in)
                except (AttributeError, TypeError, KeyError):
                    am_tech = "FDM"
            else:
                am_tech = "FDM"
        
        am_tech_upper = am_tech.upper()
        am_tech_to_index = {
            "FDM": "am_fdm",
            "METAL_LPBF": "am_metal_lpbf",
            "THERMOPLASTIC_HIGH_TEMP": "am_thermoplastic_high_temp",
            "SLA": "am_sla",
            "SLS": "am_sls",
            "MJF": "am_mjf",
        }
        return am_tech_to_index.get(am_tech_upper, "am")  # Fallback to generic AM index
    
    # Fallback: lowercase the process name
    return process.lower()


def pretty_process_name(process: str, am_tech: str | None = None) -> str:
    """
    Get user-facing display name for a process.
    
    Args:
        process: Process identifier (e.g., "AM", "CNC", "MIM")
        am_tech: AM technology if process == "AM" (e.g., "METAL_LPBF", "FDM")
    
    Returns:
        User-friendly name (e.g., "Metal LPBF (SLM/DMLS)", "FDM", "CNC")
    """
    process_upper = process.upper()
    
    # AM processes: tech-specific names
    if process_upper == "AM" and am_tech:
        am_tech_upper = am_tech.upper()
        am_tech_display = {
            "METAL_LPBF": "Metal LPBF (SLM/DMLS)",
            "FDM": "FDM",
            "THERMOPLASTIC_HIGH_TEMP": "High-temp thermoplastic (PEEK/PEI)",
            "SLA": "SLA (Resin)",
            "SLS": "SLS (Powder polymer)",
            "MJF": "MJF (HP Multi Jet Fusion)",
        }
        return am_tech_display.get(am_tech_upper, "AM")
    
    # Non-AM processes: title-case or existing labels
    process_labels = {
        "CNC": "CNC",
        "CNC_TURNING": "CNC Turning",
        "SHEET_METAL": "Sheet Metal",
        "INJECTION_MOLDING": "Injection Molding",
        "CASTING": "Casting",
        "FORGING": "Forging",
        "EXTRUSION": "Extrusion",
        "MIM": "MIM",
        "THERMOFORMING": "Thermoforming",
        "COMPRESSION_MOLDING": "Compression Molding",
    }
    return process_labels.get(process_upper, process.replace("_", " ").title())


def is_am_process(process: str) -> bool:
    """Check if process is AM (Additive Manufacturing)."""
    return process.upper() == "AM"


def get_kb_folder_path(process_index: str) -> str:
    """
    Get knowledge_base folder path for a process index name.
    Used by build_kb_index.py to map index names to KB folders.
    
    Args:
        process_index: FAISS index name (e.g., "am_fdm", "mim", "cnc")
    
    Returns:
        Relative path from knowledge_base root (e.g., "am/fdm", "mim", "cnc")
    """
    # AM tech-specific indices map to subfolders under am/
    if process_index == "am_fdm":
        return "am/fdm"
    elif process_index == "am_metal_lpbf":
        return "am/metal_lpbf"
    elif process_index == "am_thermoplastic_high_temp":
        return "am/thermoplastic_high_temp"
    elif process_index == "am_sla":
        return "am/sla"
    elif process_index == "am_sls":
        return "am/sls"
    elif process_index == "am_mjf":
        return "am/mjf"
    else:
        # All other processes map directly
        return process_index


# Sanity check function (can be called in tests or as assert)
def _sanity_check() -> None:
    """Verify mapping outputs are correct."""
    assert resolve_retrieval_index("CNC") == "cnc"
    assert resolve_retrieval_index("MIM") == "mim"
    assert resolve_retrieval_index("AM", "METAL_LPBF") == "am_metal_lpbf"
    assert resolve_retrieval_index("AM", "FDM") == "am_fdm"
    assert resolve_retrieval_index("AM", "THERMOPLASTIC_HIGH_TEMP") == "am_thermoplastic_high_temp"
    assert resolve_retrieval_index("AM", "SLA") == "am_sla"
    assert resolve_retrieval_index("AM", "SLS") == "am_sls"
    assert resolve_retrieval_index("AM", "MJF") == "am_mjf"
    assert resolve_retrieval_index("THERMOFORMING") == "thermoforming"
    
    assert pretty_process_name("AM", "METAL_LPBF") == "Metal LPBF (SLM/DMLS)"
    assert pretty_process_name("AM", "FDM") == "FDM"
    assert pretty_process_name("AM", "SLA") == "SLA (Resin)"
    assert pretty_process_name("AM", "SLS") == "SLS (Powder polymer)"
    assert pretty_process_name("AM", "MJF") == "MJF (HP Multi Jet Fusion)"
    assert pretty_process_name("MIM") == "MIM"
    assert pretty_process_name("CNC") == "CNC"
    
    assert get_kb_folder_path("am_fdm") == "am/fdm"
    assert get_kb_folder_path("am_sla") == "am/sla"
    assert get_kb_folder_path("am_sls") == "am/sls"
    assert get_kb_folder_path("am_mjf") == "am/mjf"
    assert get_kb_folder_path("mim") == "mim"
    assert get_kb_folder_path("cnc") == "cnc"


if __name__ == "__main__":
    # Run sanity check if module is executed directly
    _sanity_check()
    print("✓ Process registry sanity checks passed")
