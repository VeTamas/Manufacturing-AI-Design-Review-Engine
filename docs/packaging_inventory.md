# Packaging inventory (PyInstaller EXE — Desktop Mode)

This document lists runtime file/folder assets derived from **code search** (static analysis). Use it together with optional runtime tracing (`CNCR_TRACE_FILES=1`) to ensure the EXE bundle is complete.

---

## Part A — Static inventory (code-derived)

### 1. File access patterns searched

| Pattern | Location (project code only) |
|--------|------------------------------|
| `open(...)` | `agent/materials.py` (material_profiles.json) |
| `Path(...).read_text` / `.read_bytes` | `agent/nodes/explain.py`, `agent/nodes/self_review.py`, `agent/nodes/refine.py`, `agent/geometry/*.py`, `scripts/build_kb_index.py`, `scripts/normalize_casting_kb.py` |
| `json.load(...)` | `agent/materials.py`, `agent/tools/kb_tool.py` (metadata.json) |
| `faiss.read_index` / `faiss.write_index` | `agent/tools/kb_tool.py`, `scripts/build_kb_index.py` |
| `load_dotenv` / `dotenv` | `agent/config.py`, `scripts/build_kb_index.py`, `scripts/test_hybrid_confidence.py` |
| `glob` / `rglob` (KB) | `scripts/build_kb_index.py` (kb_dir.rglob("*.md")) |
| **No** `yaml.safe_load` / `pickle.load` / `importlib.resources` / `pkgutil.get_data` in project code for data assets |

Streamlit: `app/streamlit_app.py` uses `st.file_uploader` (runtime uploads to `data/uploads`); no static markdown/image assets loaded from disk in the scanned app code.

---

### 2. MUST bundle (required at runtime)

| Asset | Path / pattern | Used by |
|-------|----------------|--------|
| **Material profiles** | `data/materials/material_profiles.json` | `agent/materials.py` — `load_material_profiles()`; raises `FileNotFoundError` if missing |
| **KB FAISS indices** | `data/outputs/kb_index/<process>/index.faiss` + `metadata.json` | `agent/tools/kb_tool.py` — `_load_index()`; per-process (cnc, am, am_fdm, sheet_metal, injection_molding, casting, forging, etc.); raises `FileNotFoundError` if index missing |
| **Prompt templates** | `agent/prompts/explain_system.txt`, `agent/prompts/explain_user.txt`, `agent/prompts/self_review_system.txt` | `agent/nodes/explain.py`, `agent/nodes/self_review.py` — `_read_text(_PROMPTS_DIR / "…")` |
| **App entry + Streamlit UI** | `app/` (e.g. `streamlit_app.py`, `run_desktop.py`, `run_desktop_gui.py`) | Desktop launcher and Streamlit; `run_desktop.py` resolves `project_root / "app" / "streamlit_app.py"` |
| **Agent package** | `agent/` (all Python + prompts) | All agent logic, config, tools, nodes |

**Paths derived from code:**

- Materials: `Path(__file__).resolve().parents[1]` (agent) → `data/materials/material_profiles.json`
- KB index base: `PROJECT_ROOT / "data" / "outputs" / "kb_index"` in `agent/tools/kb_tool.py` and `agent/nodes/rag.py`
- Index layout: `index_dir = INDEX_BASE / key` (e.g. `cnc`, `am_fdm`), `index.faiss` + `metadata.json`
- Prompts: `Path(__file__).resolve().parents[1] / "prompts"` in `agent/nodes/` → files above

---

### 3. OPTIONAL bundle (example configs, caches)

| Asset | Path | Notes |
|-------|------|--------|
| Example / default `.env` | (project root) | `load_dotenv()` in `agent/config.py` — optional; EXE can rely on env vars only |
| Embedding cache | `data/outputs/cache/embeddings` (or `EMBEDDING_CACHE_DIR`) | Created at runtime; optional to pre-bundle |
| General cache | `data/outputs/cache` | `CONFIG.cache_dir`; optional |

---

### 4. DO NOT bundle

| Asset | Reason |
|-------|--------|
| **Tests** | `scripts/run_golden_tests.py`, test fixtures, `GOLDEN_CASES` (rglob `*.json`) — test-only |
| **Golden packs / step fixtures** | Large STEP or golden JSON used only in tests |
| **`knowledge_base/` markdown source** | Used by `scripts/build_kb_index.py` to *build* indices; at runtime the app only needs **built** `data/outputs/kb_index/*` (FAISS + metadata). Do not bundle KB .md for EXE unless you ship a “rebuild index” feature |
| **`.venv`** | Virtualenv; not part of EXE |
| **`clean-repo/`** | Duplicate/copy of repo; exclude from packaging |

---

## Part B — Runtime file tracer (optional)

- **Module:** `agent/utils/filetrace.py`
- **Enable:** `CNCR_TRACE_FILES=1`
- **Provides:** `traced_open()`, `traced_read_text()`, `traced_faiss_read_index()`
- **Logs:** stdout and optionally `data/outputs/logs/filetrace.log`

Use tracing to confirm every path the EXE touches at runtime; then add any missing entries to this inventory and to PyInstaller `datas`.

---

## Part C — PyInstaller datas list (draft)

See **`docs/pyinstaller_datas.md`** for the recommended `--add-data` entries for Windows.

---

## Summary table

| Category | Paths |
|----------|--------|
| **MUST** | `data/materials/`, `data/outputs/kb_index/` (built indices), `agent/` (incl. `agent/prompts/`), `app/` |
| **OPTIONAL** | `.env`, `data/outputs/cache/` (or leave empty) |
| **DO NOT** | tests, golden packs, `knowledge_base/` .md (unless rebuilding), `.venv`, `clean-repo/` |
