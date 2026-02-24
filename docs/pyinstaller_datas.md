# PyInstaller —add-data draft (Windows)

Use these **datas** entries so the EXE can find runtime assets. Format on Windows: `source;dest` (semicolon). Run PyInstaller from the **project root** so paths are correct.

---

## Recommended --add-data entries

```text
# Application and UI (desktop launcher resolves project_root / "app" / "streamlit_app.py")
app;app

# Material profiles (agent/materials.py)
data/materials;data/materials

# Built KB indices — include every process index you ship (cnc, am_fdm, etc.)
data/outputs/kb_index;data/outputs/kb_index

# Prompt templates (agent/nodes explain, self_review, refine)
agent/prompts;agent/prompts
```

---

## One-line for pyinstaller (Windows, from project root)

```bash
pyinstaller --onefile ^
  --add-data "app;app" ^
  --add-data "data/materials;data/materials" ^
  --add-data "data/outputs/kb_index;data/outputs/kb_index" ^
  --add-data "agent/prompts;agent/prompts" ^
  --hidden-import=agent.utils.filetrace ^
  app/run_desktop_gui.py
```

Adjust:

- **Entry point:** Use `app/run_desktop_gui.py` for a windowed EXE (no console), or `app/run_desktop.py` if you want a console for debugging.
- **KB index:** Ensure `data/outputs/kb_index/` contains the built indices (e.g. `cnc/index.faiss` + `cnc/metadata.json`, `am_fdm/`, …) before running PyInstaller; only existing subdirs are bundled. Add more `--add-data` lines if you keep indices elsewhere.
- **Optional:** To ship a default `.env`, add `--add-data ".env;."` (only if you want a bundled default).

---

## Optional / do not bundle

| Asset | Recommendation |
|-------|----------------|
| `knowledge_base/*.md` | Do **not** bundle for normal EXE; runtime only needs `data/outputs/kb_index/`. Bundle only if the EXE will run “rebuild index”. |
| `data/outputs/cache` | Do not bundle; let the app create at runtime. |
| Tests, `scripts/run_golden_tests.py`, golden STEP/JSON | Do not bundle. |

---

## Verifying paths in the EXE

After building, run with tracing to confirm every file access:

```bash
set CNCR_TRACE_FILES=1
cncreviewcad.exe
```

Check stdout and `data/outputs/logs/filetrace.log` (relative to the current working directory when the EXE runs). Ensure the EXE’s working directory or `sys._MEIPASS` (PyInstaller unpack dir) is correct so that paths like `data/materials/material_profiles.json` and `data/outputs/kb_index/cnc/index.faiss` resolve. If you use `__file__`-based resolution (e.g. `Path(__file__).resolve().parents[2]`), PyInstaller sets `__file__` inside the bundle; ensure your code uses a single “project root” that works both from source and from the EXE (e.g. `sys._MEIPASS` when frozen).
