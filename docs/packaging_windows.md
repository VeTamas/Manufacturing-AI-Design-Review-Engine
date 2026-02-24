# Packaging CNC Review Agent for Windows (Offline Desktop EXE)

This guide describes how to build a **windowed** Windows EXE that runs the Streamlit UI in a pywebview window, with no console and fully offline (using the existing HuggingFace cache in `agent/embeddings/local_embedder.py`).

**Run all commands from the repository root.**

---

## 1. Install dependencies

```powershell
pip install pyinstaller pywebview
```

Ensure the rest of the project deps are installed (e.g. `pip install -r requirements.txt` if present, or install streamlit, sentence-transformers, etc. as needed).

---

## 2. Warm the HuggingFace cache (optional, once online)

To run fully offline after packaging, pre-download the embedding model into `.cache/hf`:

- Run the agent pipeline once so the local embedder pulls the model (e.g. BAAI/bge-small-en-v1.5). For example:

  ```powershell
  python scripts/run_step_cli.py path\to\some.step
  ```

- Or run the Streamlit app once while online so any embedding usage triggers the download.

The cache will be under `.cache/hf` (see `agent/embeddings/local_embedder.py` for `HF_HOME` / `HUGGINGFACE_HUB_CACHE`).

---

## 3. Offline environment (runtime)

For the packaged app to run without internet, set (or rely on defaults in `local_embedder.py`):

- `HF_HUB_OFFLINE=1`
- `TRANSFORMERS_OFFLINE=1`

The codebase already sets these by default in `agent/embeddings/local_embedder.py`. When running the EXE, ensure the HuggingFace cache is either bundled (see below) or present next to the EXE (e.g. `.cache/hf` in the same directory as the EXE or in a known location).

---

## 4. PyInstaller build (GUI EXE, no console)

Use **`app/run_desktop_gui.py`** as the entry point. It calls the desktop launcher `main()` (from `app/run_desktop.py`) and is intended to produce a windowed app with no console.

**Minimal example (no bundled cache):**

```powershell
pyinstaller --windowed --name CNCReviewAgent --paths . app/run_desktop_gui.py
```

**With HuggingFace cache bundled** (so the EXE directory contains `.cache/hf` and the app runs offline without a separate cache):

```powershell
pyinstaller --windowed --name CNCReviewAgent --paths . --add-data ".cache\hf;.cache\hf" app/run_desktop_gui.py
```

On Windows, PyInstaller expects `--add-data` in the form `source;dest` (semicolon). Use backslashes for Windows paths. The destination is relative to the bundle root (e.g. the folder containing the EXE in `onedir` mode).

For a full one-dir build with Streamlit and sentence-transformers stacks collected, use the helper script:

```powershell
.\scripts\build_windows_exe.ps1
```

Optional: include the HF cache in the bundle:

```powershell
.\scripts\build_windows_exe.ps1 -IncludeHFCache
```

---

## 5. Output location

- **One-file (if you use `--onefile`):** `dist\CNCReviewAgent.exe`
- **One-dir (default):** `dist\CNCReviewAgent\` with `CNCReviewAgent.exe` inside.

Run `dist\CNCReviewAgent.exe` (or from `dist\CNCReviewAgent\`). The app starts Streamlit internally and opens the pywebview window.

---

## 6. Validation (before packaging)

From repo root:

- **Streamlit only (no webview):**  
  `python app/run_desktop.py --no-webview`  
  → Streamlit should start and print the ready URL (e.g. http://127.0.0.1:8501).

- **With pywebview:**  
  `python app/run_desktop.py`  
  → A native window should open showing the Streamlit UI (if pywebview is installed).

Environment variables (optional): `CNCR_DEBUG=1`, `CNCR_UI_HOST`, `CNCR_UI_PORT`.
