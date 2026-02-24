from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from agent.run import run_agent
from agent.state import ConfidenceInputs, Inputs, PartSummary
from app.ui.presets import PRESETS

st.set_page_config(page_title="CNC Review Agent", layout="wide")
st.title("Manufacturing AI Design Review Engine")
st.info(
    "**Portfolio Release:** simplified deterministic scoring (production heuristics removed)."
)

debug = st.sidebar.checkbox("Debug", value=False, key="debug")
if debug:
    st.sidebar.info("Debug mode is ON (non-blocking).")

# ---- CAD status: success, message, bins_preview (set by STEP upload) ----
if "cad_status" not in st.session_state:
    st.session_state["cad_status"] = {"success": False, "message": "", "bins_preview": None}
if "cad_bins_preview" not in st.session_state:
    st.session_state["cad_bins_preview"] = None
st.session_state.setdefault("use_cad_bins_user_set", False)
# Set use_cad_bins_ui default only once; do not overwrite on reruns
_cad_ok_init = st.session_state.get("cad_status", {}).get("success", False)
st.session_state.setdefault("use_cad_bins_ui", bool(_cad_ok_init))
st.session_state.setdefault("has_2d_drawing", False)
st.session_state.setdefault("step_scale_confirmed", True)
st.session_state.setdefault("turning_support_confirmed", False)
st.session_state.setdefault("user_text", "")
st.session_state.setdefault("part_summary_mode", "bins")
st.session_state.setdefault("step_path", None)

# ---- Defaults ----
DEFAULTS = {
    "process": "AUTO",
    "material": "Aluminum",
    "production_volume": "Proto",
    "load_type": "Static",
    "tolerance_criticality": "Medium",
    "part_size": "Small",
    "min_internal_radius": "Medium",
    "min_wall_thickness": "Medium",
    "hole_depth_class": "None",
    "pocket_aspect_class": "OK",
    "feature_variety": "Low",
    "accessibility_risk": "Low",
    "has_clamping_faces": True,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


def _idx(options: list[str], value: str, fallback: str) -> int:
    v = value if value in options else fallback
    return options.index(v)


with st.sidebar:
    st.header("Job inputs")

    process_values = ["AUTO", "CNC", "CNC_TURNING", "AM", "SHEET_METAL", "INJECTION_MOLDING", "CASTING", "FORGING", "EXTRUSION", "MIM", "THERMOFORMING", "COMPRESSION_MOLDING"]
    process_labels = ["AUTO (I'm not sure)", "CNC", "CNC Turning", "AM", "Sheet Metal", "Injection Molding", "Casting", "Forging", "Extrusion", "MIM", "Thermoforming", "Compression Molding"]
    process_idx = _idx(process_values, st.session_state.get("process", "AUTO"), "AUTO")
    selected_label = st.selectbox(
        "Manufacturing process",
        process_labels,
        index=process_idx,
        key="process_label",
    )
    process = process_values[process_labels.index(selected_label)]
    st.session_state["process"] = process
    
    # AM Technology selector (only shown when process == "AM")
    am_tech_opts = ["AUTO", "FDM", "METAL_LPBF", "THERMOPLASTIC_HIGH_TEMP", "SLA", "SLS", "MJF"]
    am_tech_labels = ["Auto", "FDM", "Metal LPBF", "High-temp Thermoplastic", "SLA (Resin)", "SLS (Powder polymer)", "MJF (HP Multi Jet Fusion)"]
    if process == "AM":
        am_tech_idx = _idx(am_tech_opts, st.session_state.get("am_tech", "AUTO"), "AUTO")
        am_tech_label = st.selectbox(
            "AM Technology",
            am_tech_labels,
            index=am_tech_idx,
            key="am_tech_label",
        )
        # Map label back to value
        am_tech = am_tech_opts[am_tech_labels.index(am_tech_label)]
        st.session_state["am_tech"] = am_tech
    else:
        am_tech = st.session_state.get("am_tech", "AUTO")
    
    material_opts = ["Aluminum", "Steel", "Plastic", "Stainless Steel", "Titanium"]
    volume_opts = ["Proto", "Small batch", "Production"]
    load_opts = ["Static", "Dynamic", "Shock"]
    tol_opts = ["Low", "Medium", "High"]

    material = st.selectbox(
        "Material",
        material_opts,
        index=_idx(material_opts, st.session_state.get("material", "Aluminum"), "Aluminum"),
        key="material",
    )
    # Map display names to Inputs-compatible values (backward compatibility)
    # Inputs only accepts ["Aluminum", "Steel", "Plastic"], so map new options to closest match
    # The material resolver will detect "stainless" or "titanium" from user_text if present
    material_for_inputs_map = {
        "Stainless Steel": "Steel",  # Map to Steel for Inputs validation; resolver checks user_text for "stainless"
        "Titanium": "Steel",  # Map to Steel for Inputs validation; resolver checks user_text for "titanium"
    }
    material_for_inputs = material_for_inputs_map.get(material, material)
    production_volume = st.selectbox(
        "Production volume",
        volume_opts,
        index=_idx(volume_opts, st.session_state["production_volume"], "Proto"),
        key="production_volume",
    )
    load_type = st.selectbox(
        "Load type",
        load_opts,
        index=_idx(load_opts, st.session_state["load_type"], "Static"),
        key="load_type",
    )
    tolerance_criticality = st.selectbox(
        "Tolerance criticality",
        tol_opts,
        index=_idx(tol_opts, st.session_state["tolerance_criticality"], "Medium"),
        key="tolerance_criticality",
    )

    st.text_area(
        "Part description / notes (optional)",
        value=st.session_state.get("user_text", ""),
        key="user_text",
        placeholder="Example: cosmetic part, textured surface, gate near this face, insert molding, draft concerns...",
        height=140,
        help="Used for keyword-based checks and to improve knowledge-base lookup (RAG).",
    )

    # ---- ÚJ: preset blokk (kicsi, egyszerű) ----
    st.divider()
    st.header("Demo presets")

    preset_names = ["(none)"] + list(PRESETS.keys())
    preset_choice = st.selectbox("Load preset", preset_names)

    col_a, col_b = st.columns(2)
    with col_a:
        apply_preset = st.button("Apply preset", use_container_width=True)
    with col_b:
        reset = st.button("Reset", use_container_width=True)

    if reset:
        for k, v in DEFAULTS.items():
            st.session_state[k] = v
        st.rerun()

    if apply_preset and preset_choice != "(none)":
        st.session_state.update(PRESETS[preset_choice])
        st.rerun()

    # ---- STEP upload (CAD-derived bins) ----
    st.divider()
    st.header("CAD (optional)")
    part_summary_mode = st.selectbox(
        "Analysis mode",
        ["Fast (bins)", "Detailed (numeric, if supported)"],
        index=0 if st.session_state.get("part_summary_mode", "bins") == "bins" else 1,
        key="part_summary_mode_ui",
        help="Fast: bins only. Detailed: numeric geometry analysis when supported (CNC/CNC_TURNING).",
    )
    part_summary_mode_val = "numeric" if part_summary_mode.startswith("Detailed") else "bins"
    st.session_state["part_summary_mode"] = part_summary_mode_val

    step_file = st.file_uploader(
        "Upload STEP (.step/.stp) [optional]",
        type=["step", "stp"],
        help="Optional. If parsed, part_size / feature_variety / accessibility_risk / has_clamping_faces are derived from geometry.",
    )
    if step_file is not None:
        try:
            upload_dir = Path(__file__).resolve().parents[1] / "data" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            suffix = ".step" if step_file.name.lower().endswith(".step") else ".stp"
            tmp_path = upload_dir / f"{step_file.name}"
            tmp_path.write_bytes(step_file.getvalue())
            st.session_state["step_path"] = str(tmp_path)
            from agent.cad import ingest_step_to_bins
            cad_status = ingest_step_to_bins(str(tmp_path))
            st.session_state["cad_status"] = cad_status
            bins_preview = cad_status.get("bins_preview")
            st.session_state["cad_bins_preview"] = bins_preview
            if cad_status["success"] and not st.session_state.get("use_cad_bins_user_set", False):
                st.session_state["use_cad_bins_ui"] = True
            elif not cad_status["success"]:
                st.warning("CAD file could not be parsed; using manual inputs.")
        except Exception as e:
            st.session_state["cad_status"] = {
                "success": False,
                "message": str(e),
                "bins_preview": None,
            }
            st.session_state["cad_bins_preview"] = None
            st.warning("CAD file could not be parsed; using manual inputs.")
    else:
        # No file: clear step_path for this session
        st.session_state["step_path"] = None

    if part_summary_mode_val == "numeric" and process not in ("CNC", "CNC_TURNING"):
        st.warning("Detailed numeric analysis not yet supported for this process; using bins.")

    drawing_file = st.file_uploader(
        "Upload 2D drawing (PDF/DXF) [optional]",
        type=["pdf", "dxf"],
        help="Optional but recommended. Used to increase confidence; not parsed yet.",
    )
    if drawing_file is not None:
        upload_dir = Path(__file__).resolve().parents[1] / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = upload_dir / f"{drawing_file.name}"
        tmp_path.write_bytes(drawing_file.getvalue())
        st.session_state["has_2d_drawing"] = True
    else:
        st.session_state["has_2d_drawing"] = False

    st.checkbox(
        "STEP model dimensions are real-world scale (not illustrative)",
        value=bool(st.session_state.get("step_scale_confirmed", True)),
        key="step_scale_confirmed",
        help="If OFF, size-based risks are treated as indicative only.",
    )

    st.checkbox(
        "Turning workholding support available (tailstock / steady rest if required)",
        value=bool(st.session_state.get("turning_support_confirmed", False)),
        key="turning_support_confirmed",
        help="If OFF, slender turning parts may have higher deflection/chatter risk.",
    )

    cad_status = st.session_state["cad_status"]
    if not cad_status["success"] and cad_status["message"]:
        st.caption(f"CAD: {cad_status['message']}")
    if cad_status["bins_preview"]:
        preview = cad_status["bins_preview"]
        with st.expander("CAD-derived Bins (Preview)"):
            bbox = preview.get("bbox_mm")
            if bbox is not None:
                st.text(f"bbox (dx, dy, dz) mm: {bbox}")
            for k in ("part_size", "feature_variety", "accessibility_risk", "has_clamping_faces"):
                if k in preview:
                    st.text(f"{k}: {preview[k]}")

        def _mark_use_cad_bins_touched():
            st.session_state["use_cad_bins_user_set"] = True

        st.checkbox(
            "Use CAD-derived bins",
            value=bool(st.session_state.get("use_cad_bins_ui", False)),
            key="use_cad_bins_ui",
            on_change=_mark_use_cad_bins_touched,
            help="When ON, part_size / feature_variety / accessibility_risk / has_clamping_faces come from the STEP file.",
        )

    # ---- Part summary (binned) ----
    st.divider()
    st.header("Manual Part Summary Settings (Fallback / Override)")
    st.caption("Manual bins. If CAD-derived bins are enabled and parsing succeeds, the agent may override some values.")

    part_size_opts = ["Small", "Medium", "Large"]
    radius_opts = ["Small", "Medium", "Large", "Unknown"]
    wall_opts = ["Thin", "Medium", "Thick", "Unknown"]
    hole_depth_opts = ["None", "Moderate", "Deep", "Unknown"]
    pocket_opts = ["OK", "Risky", "Extreme", "Unknown"]
    variety_opts = ["Low", "Medium", "High"]
    access_opts = ["Low", "Medium", "High"]

    part_size = st.selectbox(
        "Part size",
        part_size_opts,
        index=_idx(part_size_opts, st.session_state["part_size"], "Small"),
        key="part_size",
    )
    min_internal_radius = st.selectbox(
        "Min internal radius",
        radius_opts,
        index=_idx(radius_opts, st.session_state["min_internal_radius"], "Medium"),
        key="min_internal_radius",
    )
    min_wall_thickness = st.selectbox(
        "Min wall thickness",
        wall_opts,
        index=_idx(wall_opts, st.session_state["min_wall_thickness"], "Medium"),
        key="min_wall_thickness",
    )
    hole_depth_class = st.selectbox(
        "Hole depth class",
        hole_depth_opts,
        index=_idx(hole_depth_opts, st.session_state["hole_depth_class"], "None"),
        key="hole_depth_class",
    )
    pocket_aspect_class = st.selectbox(
        "Pocket aspect class",
        pocket_opts,
        index=_idx(pocket_opts, st.session_state["pocket_aspect_class"], "OK"),
        key="pocket_aspect_class",
    )
    feature_variety = st.selectbox(
        "Feature variety",
        variety_opts,
        index=_idx(variety_opts, st.session_state["feature_variety"], "Low"),
        key="feature_variety",
    )
    accessibility_risk = st.selectbox(
        "Accessibility risk",
        access_opts,
        index=_idx(access_opts, st.session_state["accessibility_risk"], "Low"),
        key="accessibility_risk",
    )
    has_clamping_faces = st.checkbox(
        "Has clamping/datum faces",
        value=bool(st.session_state["has_clamping_faces"]),
        key="has_clamping_faces",
    )

    st.divider()
    rag_enabled = st.checkbox("Force knowledge-base lookup (Agent may trigger automatically)", value=False, key="rag_enabled")

    run = st.button("Analyze", type="primary")


if run:
    am_tech_value = st.session_state.get("am_tech", "AUTO")
    user_text = st.session_state.get("user_text", "") or ""
    # Add material hint to user_text if user selected Stainless Steel or Titanium (for resolver)
    if material in ("Stainless Steel", "Titanium"):
        user_text = (user_text or "") + f" {material.lower()}"
    inputs = Inputs(
        process=process,
        material=material_for_inputs,
        production_volume=production_volume,
        load_type=load_type,
        tolerance_criticality=tolerance_criticality,
        am_tech=am_tech_value,
        user_text=user_text,
    )
    # Manual values from selectboxes (sidebar ran this run)
    part_size_manual = part_size
    feature_variety_manual = feature_variety
    accessibility_risk_manual = accessibility_risk
    has_clamping_faces_manual = has_clamping_faces

    cad_ok = st.session_state.get("cad_status", {}).get("success", False)
    cad_bins = st.session_state.get("cad_bins_preview", {}) or {}
    use_cad = bool(st.session_state.get("use_cad_bins_ui", False))

    def cad_or_manual(key: str, manual_value):
        if use_cad and cad_ok:
            v = cad_bins.get(key)
            if v is not None and v != "" and v != "Unknown":
                return v if key != "has_clamping_faces" else bool(v)
        return manual_value

    summary = PartSummary(
        part_size=cad_or_manual("part_size", part_size_manual),
        feature_variety=cad_or_manual("feature_variety", feature_variety_manual),
        accessibility_risk=cad_or_manual("accessibility_risk", accessibility_risk_manual),
        has_clamping_faces=cad_or_manual("has_clamping_faces", has_clamping_faces_manual),
        min_internal_radius=min_internal_radius,
        min_wall_thickness=min_wall_thickness,
        hole_depth_class=hole_depth_class,
        pocket_aspect_class=pocket_aspect_class,
    )

    # Final PartSummary preview (pre-run)
    with st.sidebar:
        st.caption("**Final PartSummary preview (pre-run)**")
        preview_status = "✅ CAD override active" if (use_cad and cad_ok) else "ℹ️ Manual bins active"
        st.caption(preview_status)
        preview_dict = {
            "part_size": summary.part_size,
            "feature_variety": summary.feature_variety,
            "accessibility_risk": summary.accessibility_risk,
            "has_clamping_faces": summary.has_clamping_faces,
        }
        st.json(preview_dict)

    # Debug panel: only after summary is built; never stops execution
    if debug:
        st.sidebar.caption("**Final Bins Used by Agent**")
        st.sidebar.write("Manual feature_variety:", feature_variety_manual)
        st.sidebar.write(
            "CAD feature_variety:",
            (st.session_state.get("cad_bins_preview") or {}).get("feature_variety"),
        )
        st.sidebar.write("FINAL feature_variety (pre-run_agent):", summary.feature_variety)
        user_text_debug = st.session_state.get("user_text", "")
        if user_text_debug:
            st.sidebar.caption("**User Text (first 200 chars)**")
            st.sidebar.text(user_text_debug[:200])

    conf_inputs = ConfidenceInputs(
        has_2d_drawing=bool(st.session_state.get("has_2d_drawing", False)),
        step_scale_confirmed=bool(st.session_state.get("step_scale_confirmed", True)),
        turning_support_confirmed=bool(st.session_state.get("turning_support_confirmed", False)),
    )
    cad_metrics = st.session_state.get("cad_bins_preview", {}) or {}
    part_summary_mode = st.session_state.get("part_summary_mode", "bins")
    step_path = st.session_state.get("step_path") if cad_ok else None
    with st.spinner("Running agent..."):
        out = run_agent(
            inputs,
            summary,
            rag_enabled=rag_enabled,
            confidence_inputs=conf_inputs,
            cad_metrics=cad_metrics,
            user_text=user_text,
            part_summary_mode=part_summary_mode,
            step_path=step_path,
        )

    err = out.get("error")
    if err is not None:
        if isinstance(err, dict):
            err_node = err.get("node", "?")
            err_msg = err.get("message", "Unknown error")
        else:
            err_node = getattr(err, "node", "?")
            err_msg = getattr(err, "message", "Unknown error")
        st.error(f"**{err_node}:** {err_msg}")
    if debug and "part_summary" in out:
        st.sidebar.write("FINAL feature_variety (post-graph):", out["part_summary"].feature_variety)

    findings = out.get("findings", [])
    report_md = out.get("report_markdown", "")
    usage = out.get("usage", {})

    conf = out.get("confidence")
    if conf is not None:
        _conf_d = conf.model_dump() if hasattr(conf, "model_dump") and callable(conf.model_dump) else (conf if isinstance(conf, dict) else {})
        score = _conf_d.get("score")
        if isinstance(score, (int, float)):
            st.subheader("Agent confidence")
            st.metric("Score", f"{float(score):.2f}")
            if score >= 0.8:
                st.success("High confidence")
            elif score >= 0.6:
                st.warning("Moderate confidence")
            else:
                st.error("Low confidence")

    trace = out.get("trace") or []
    if trace:
        with st.expander("Agent decision trace"):
            st.markdown("\n".join(f"- {e}" for e in trace))

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Findings")
        if not findings:
            st.success("No findings.")
        else:
            for f in findings:
                if f.severity == "HIGH":
                    st.error(f"**{f.title}**\n\n{f.why_it_matters}\n\n*Recommendation:* {f.recommendation}")
                elif f.severity == "MEDIUM":
                    st.warning(f"**{f.title}**\n\n{f.why_it_matters}\n\n*Recommendation:* {f.recommendation}")
                else:
                    st.info(f"**{f.title}**\n\n{f.why_it_matters}\n\n*Recommendation:* {f.recommendation}")

    with col2:
        st.subheader("Report (Markdown)")
        st.caption("Alternative processes (Secondary) are informational when not a close call.")
        st.code(report_md, language="markdown")
        st.subheader("Usage (tokens)")
        if usage:
            total_tokens = usage.get("total_tokens")
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            cost_usd = usage.get("total_cost_usd")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total tokens", total_tokens)
            c2.metric("Prompt tokens", prompt_tokens)
            c3.metric("Completion tokens", completion_tokens)
            c4.metric("Cost (USD)", f"{cost_usd:.6f}" if isinstance(cost_usd, (int, float)) else cost_usd)
        else:
            st.caption("Token usage not available (callback missing).")
        
        st.download_button(
            "Download report.md",
            data=report_md.encode("utf-8"),
            file_name="cnc_review_report.md",
            mime="text/markdown",
        )
else:
    st.info("Set inputs in the sidebar, then click **Analyze**.")