# Manufacturing AI Design Review Engine  
### Offline-First Manufacturability Intelligence System

---

> **Portfolio / public version**  
> This repository is a **portfolio-safe release** of an industrial AI engineering prototype.  
> **Production manufacturability heuristics and proprietary tuning are intentionally not included.**  
> Process selection uses simplified deterministic baseline rules in `agent/scoring/portfolio_scoring.py`.  
> No private datasets, API keys, FAISS indices, or internal optimization layers are committed.

---

## Executive Summary

**cncreviewcad** is an offline-first, privacy-focused manufacturability analysis engine for mechanical engineers.

It is **not a chatbot**.

It is a deterministic engineering decision system that:

- Parses CAD geometry (STEP)
- Applies rule-based manufacturability scoring
- Performs geometry-driven manufacturing classification (AUTO mode)
- Generates audit-safe engineering findings
- Optionally enriches explanations using a local GPU LLM
- Runs fully offline (RAG + embeddings + scoring independent of cloud)

Engineering decisions are deterministic.  
AI is used only for explanation.

This project focuses on reliable engineering decision support rather than generative AI workflows, targeting privacy-sensitive industrial environments where deterministic evaluation and offline capability are critical.

---

## Core Philosophy

> Geometry first.  
> Deterministic scoring first.  
> AI only for explanation.

Architecture layers:

1. Geometry analysis  
2. Deterministic manufacturing scoring  
3. Process classification (AUTO)  
4. Explanation layer (LLM optional)  
5. Reporting + audit trace  

LLM is **not required** for manufacturability scoring.

---

## What This Is

- Deterministic manufacturability scoring engine
- Geometry-driven manufacturing classifier
- Offline Design-for-Manufacturability assistant
- Privacy-safe engineering evaluation tool
- Agentic explanation layer (optional)

---

## What This Is Not

- Not a chatbot
- Not cloud dependent
- Not LLM-driven classification
- Not consumer AI tooling
- Not hobby CAD assistant

---

## System Architecture

### Geometry Layer (Fully Local)

- STEP ingestion via local Python libs
- CAD feature extraction
- Bounding box analysis
- Thin-wall detection
- Accessibility heuristics
- Turning symmetry detection
- Sheet metal heuristics
- Extrusion profile heuristics

No cloud calls.

---

### Deterministic Manufacturing Scoring Engine

Supported processes:

- CNC machining
- CNC turning
- Sheet metal fabrication
- Extrusion
- Additive manufacturing
- Casting
- Forging
- MIM

Features:

- Geometry-driven AUTO mode
- Deterministic tie-break logic
- Hybrid process modelling
- Risk flag generation
- Golden test validation
- Material property modifiers (machinability, formability, castability, extrudability, AM readiness)

**Material System:**

- Material profiles with property vectors stored in `data/materials/material_profiles.json`
- Deterministic resolver: maps user input strings to material profiles with properties
- Material modifiers affect process scores (e.g., hard materials penalize CNC, high AM readiness boosts AM)
- Backward compatible: existing "Steel"/"Aluminum"/"Plastic" inputs work as before
- Supports: Steel, Aluminum, Plastic, Stainless Steel, Titanium (with AM properties)

Runs fully offline.

---

### AUTO Process Selection Mode

AUTO mode:

- Geometry + bins driven
- No user bias
- Deterministic scoring
- Golden test validated
- Hybrid logic cannot override AUTO primary

AUTO is a convenience feature, not the core value.

---

### Explanation Layer (Local LLM Optional)

Primary local LLM:

- Ollama runtime
- Default model: `jamba2-3b-q6k`
- GPU inference

Used for:

- Narrative explanation
- Report phrasing
- RAG enrichment
- Engineering clarification

Not used for:

- Scoring
- Classification
- Rule evaluation

LLM can be disabled completely.

---

### Local RAG (Fully Offline)

- Markdown knowledge base
- FAISS vector store
- Process-specific indexes
- Deterministic triggering

Embeddings:

- Local (default)
- OpenAI optional fallback

No browsing. No data exfiltration.

---

## Offline Operation

Full offline includes:

- CAD parsing
- Deterministic scoring
- Local FAISS store
- Local embeddings
- Local Ollama LLM
- No OpenAI dependency

Industrial default = offline-first.

---

## Cloud Usage (Optional)

OpenAI:

- Explanation fallback only
- Legacy compatibility
- Hybrid mode optional

Not required for:

- Scoring
- Classification
- CAD ingestion
- RAG

Migration toward fully local-only ongoing.

---

## Validation & Reliability

Golden tests:

    python scripts/run_golden_tests.py --auto

Features:

- Deterministic regression testing
- AUTO alignment checks
- Trace-on-fail debugging
- Multi-pack validation
- Stable baseline coverage

Primary system risk:

**Heuristic tuning — not architectural instability.**

---

## Tech Stack

- Python 3.11–3.13
- Ollama (local LLM runtime)
- Jamba2 3B local model
- FAISS vector store
- Sentence-transformers embeddings
- LangGraph agent workflow
- LangChain orchestration
- Streamlit UI
- Pure Python deterministic scoring

---

## Target Users

### Primary

- Manufacturing engineers
- Mechanical engineers
- DFM reviewers
- CNC / fabrication engineers

### Secondary

- Engineering startups
- Privacy-sensitive industrial orgs
- CAD automation developers

### Not Target

- Hobby CAD users
- Consumer AI users
- General chatbot audiences

---

## Project Status

### Stable

- STEP ingestion
- Geometry feature extraction
- Deterministic scoring
- AUTO process classification
- Golden tests
- Local RAG
- Local LLM inference
- CLI interface
- Streamlit UI
- Reporting pipeline

### Not Yet Production Hardened

- Packaging
- API layer
- Monitoring
- Security hardening
- Deployment automation
- Error taxonomy

Advanced engineering prototype with stable architecture.

---

## Knowledge Base (KB) indexing — rebuild FAISS indices

The RAG layer uses **local FAISS indices** built from the markdown knowledge base.  
If you pull the repo fresh, change embedding mode/model, or modify KB markdown files, you must **rebuild the indices**.

### When do I need to rebuild?
Rebuild FAISS indices if any of these are true:

- You changed `EMBEDDING_MODE` (`local` ↔ `openai`)
- You changed the embedding model (e.g. `LOCAL_EMBED_MODEL`)
- You pulled new/updated KB markdown files
- You deleted `data/outputs/kb_index/` or want a clean rebuild
- You see errors like `rag_index_missing`, `FileNotFoundError: index.faiss`, or dimension mismatch

### Where are indices stored?
Built indices are written to:

- `data/outputs/kb_index/<process>/index.faiss`
- `data/outputs/kb_index/<process>/metadata.json`

Example processes: `cnc`, `sheet_metal`, `am`, `casting`, `forging`, etc.

### Rebuild all indices (recommended)
From repo root:

powershell
```python scripts/build_kb_index.py```

## Local embeddings (offline-friendly)

Default mode is local embeddings. To force it explicitly:

```$env:EMBEDDING_MODE="local"
$env:LOCAL_EMBED_MODEL="BAAI/bge-small-en-v1.5"
python scripts/build_kb_index.py
```

"Note: The first run may download the embedding model if it is not already cached.
For fully air-gapped machines, you must provide the model files (HuggingFace cache or a prepacked model folder)."

## Important: embedding dimension must match the index

FAISS indices are embedding-dimension specific.
If you switch embedding backends/models, you must rebuild all indices, otherwise you may get runtime errors or poor retrieval.

Quick verification

After rebuild, verify the index directories exist:

data/outputs/kb_index/cnc/index.faiss

data/outputs/kb_index/cnc/metadata.json

## How to Run Locally (Windows)

    ```python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    streamlit run app/streamlit_app.py```

---

## Optional Local LLM Explanations (Fully Offline)

Manufacturing scoring and process classification remain fully deterministic.  
The optional LLM layer is used only for explanation, phrasing, and report clarity.

If no LLM is configured, the system still produces complete deterministic reports.

### Install Ollama

https://ollama.ai/download

Verify:

```bash
ollama --version```

Pull a model
```ollama pull jamba2-3b-q6k```

Enable local LLM

Windows (PowerShell):
```$env:LLM_MODE="local"
$env:OLLAMA_BASE_URL="http://localhost:11434"
$env:OLLAMA_MODEL="jamba2-3b-q6k"```

Linux / macOS:
```export LLM_MODE=local
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=jamba2-3b-q6k```

Then run:
```streamlit run app/streamlit_app.py```

Disable LLM completely
```LLM_MODE=off```

Notes:
- Runs fully offline when using local models.
- Cloud APIs are optional and disabled by default in offline mode.
- Smaller models are recommended for local demo performance.

---

## Smoke test (quick manual check)

Run the CLI on a sample STEP file to confirm the pipeline and portfolio scoring work:

1. **With a STEP in the repo (e.g. under `data/uploads/` or any path):**
   ```powershell
   python scripts/run_step_cli.py path\to\your\file.STEP
   ```
2. **With process/material/volume overrides:**
   ```powershell
   python scripts/run_step_cli.py path\to\file.STEP --process AUTO --material Aluminum --volume Proto
   ```
3. **Expect:** A report with a **primary** process, **secondary** options, **findings**, and **reasons**. No errors.

---

## Desktop Mode (Native Window)

    pip install -r requirements.txt -r requirements-desktop.txt
    python scripts/run_desktop.py

Modes:

- Browser mode → streamlit run app/streamlit_app.py  
- Desktop mode → python scripts/run_desktop.py  
- Debug → python scripts/run_desktop.py --no-webview  

Env overrides:

- CNCR_UI_HOST (127.0.0.1)
- CNCR_UI_PORT (8501)
- CNCR_DEBUG=1

---

## Full Offline Mode (Embeddings + LLM)

    $env:EMBEDDING_MODE="local"
    $env:LLM_MODE="local"

Rebuild FAISS index:

    python scripts/build_kb_index.py

Optional per process:

    python scripts/build_kb_index.py --process cnc

Test:

    python scripts/test_local_embeddings.py
    python scripts/test_kb_query_local.py

Important:

- Rebuild indices when switching embedding backend
- OpenAI dim ≈ 1536
- Local dim ≈ 384
- Query embedding cache TTL ≈ 7 days

Embedding env vars:

- EMBEDDING_MODE = local | openai
- LOCAL_EMBED_MODEL = BAAI/bge-small-en-v1.5
- EMBEDDING_CACHE_DIR
- EMBEDDING_BATCH_SIZE

---

## Quick CAD Test

1. Upload STEP in sidebar  
2. Check CAD bins preview  
3. Toggle “Use CAD-derived bins”  
4. Compare results vs manual bins  

---

## STEP CLI

    python scripts/run_step_cli.py tests/golden/parts/cnc/CNC1.step
    python scripts/run_step_cli.py tests/golden/parts/edge/EDGE2.STEP --process EXTRUSION --material Aluminum --volume Production
    python scripts/run_step_cli.py edge/EDGE2.STEP

Outputs:

- Primary process
- Secondary processes
- Findings
- Markdown + JSON reports in artifacts/reports/

---

## Roadmap

### Short Term

- Sheet metal detection refinement
- Extrusion heuristic stabilization
- Golden pack expansion
- Documentation cleanup

### Mid Term

- Numeric scoring refactor
- Unified manufacturing classifier
- Confidence scoring reliability
- Hybrid process modelling
- Deployment packaging

### Long Term

- Cost estimation layer
- Manufacturability simulation hooks
- CAM integration
- CAD plugins
- Full offline industrial deployment

---

## Elevator Summary

Offline-first manufacturability analysis engine.

Deterministic engineering scoring + optional local AI explanation.

CAD geometry → manufacturing evaluation → audit-ready report.

Built for privacy-sensitive industrial workflows.s
