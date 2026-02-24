# Manufacturing AI Design Review Engine  
### Offline-First Manufacturability Intelligence System

---

## Problem Statement

There has long been a persistent gap between design engineers and manufacturing technicians.  
Even when engineering calculations, simulations, and physics are correct, designs often turn out to be:

- unnecessarily expensive to manufacture  
- overly complex for the intended application  
- difficult or time-consuming to produce  
- prone to repeated design–manufacturing iteration cycles  

This leads to extended development timelines, increased costs, and inefficient communication between design and production teams.

This project explores how deterministic engineering analysis combined with modern AI assistance can help engineers identify manufacturability risks early in the design phase.

---

## Executive Summary

**Manufacturing Design Review Engine** is an offline-first manufacturability analysis system designed for mechanical and manufacturing engineers.

It is **not a chatbot** and does not rely on AI for engineering decisions.

Instead, it combines:

- deterministic manufacturability scoring  
- CAD geometry analysis  
- process classification logic  
- optional AI-generated explanations  

All core engineering decisions remain deterministic and auditable.  
AI is used only for explanation and documentation support.

---

## Core Philosophy

> Geometry first.  
> Deterministic engineering logic first.  
> AI only for explanation — never for engineering decisions.

Architecture layers:

1. Geometry analysis  
2. Deterministic manufacturability scoring  
3. Process classification (AUTO mode)  
4. Optional explanation layer (local LLM)  
5. Reporting and audit trace generation  

LLM functionality is entirely optional.

---

## What This Project Is

- Deterministic manufacturability scoring engine  
- Geometry-driven manufacturing classifier  
- Offline design-for-manufacturability assistant  
- Privacy-safe engineering evaluation tool  
- Hybrid deterministic + AI explanation system  

---

## What This Project Is Not

- Not a chatbot  
- Not AI-driven engineering decision making  
- Not cloud-dependent  
- Not consumer AI tooling  
- Not a hobby CAD assistant  

---

## System Architecture Overview

### Geometry Analysis Layer (Fully Local)

- STEP CAD ingestion  
- Feature extraction heuristics  
- Thin-wall detection  
- Accessibility analysis  
- Turning symmetry detection  
- Sheet-metal heuristics  
- Extrusion profile detection  

No cloud interaction required.

---

### Deterministic Manufacturing Scoring Engine

Supported processes include:

- CNC machining / turning  
- Sheet metal fabrication  
- Extrusion  
- Additive manufacturing  
- Casting and forging  
- Metal injection molding (MIM)

Key features:

- Geometry-driven AUTO classification  
- Deterministic scoring logic  
- Hybrid process modelling  
- Risk flag generation  
- Regression test validation  

Material properties influence manufacturability scoring through deterministic modifiers.

---

### Explanation Layer (Optional)

Local LLM integration via:

- Ollama runtime  
- GPU inference (optional)  

Used exclusively for:

- engineering explanation  
- report phrasing  
- contextual clarification  

Never used for:

- scoring  
- classification  
- engineering decisions  

The system functions fully without AI.

---

### Local RAG Knowledge Layer

- Offline markdown knowledge base  
- FAISS vector storage  
- Local embeddings by default  
- Optional OpenAI fallback  

Designed for privacy-sensitive industrial environments.

---

## Offline-First Operation

Fully offline capabilities include:

- CAD parsing  
- Manufacturability scoring  
- Knowledge retrieval  
- Local embeddings  
- Local LLM explanation  

No cloud dependency required.

---

## Validation and Reliability

Engineering reliability is prioritized via:

- deterministic regression testing  
- golden test datasets  
- traceable scoring decisions  
- explainable evaluation pipeline  

Primary risk area: heuristic tuning, not system architecture.

---

## Technology Stack

- Python 3.11–3.13  
- FAISS vector store  
- Sentence-Transformers embeddings  
- LangChain / LangGraph orchestration  
- Streamlit UI  
- Optional local LLM (Ollama)  
- Deterministic scoring engine (pure Python)

---

## Intended Users

### Primary

- Mechanical engineers  
- Manufacturing engineers  
- DFM reviewers  
- CNC and fabrication specialists  

### Secondary

- Engineering startups  
- Privacy-sensitive industrial organizations  
- CAD automation developers  

---

## Project Status

### Stable Prototype

- CAD ingestion  
- Geometry feature extraction  
- Deterministic scoring  
- Manufacturing classification  
- Offline RAG pipeline  
- Optional LLM explanation  
- Reporting workflows  

### Not Yet Production-Hardened

- Deployment packaging  
- API layer  
- Monitoring and logging hardening  
- Security review  
- CI/CD integration  

This repository represents an engineering prototype and research exploration rather than a commercial product.

---

## Note on Public Repository

To protect intellectual property and keep the repository portfolio-friendly:

- Core heuristics and production scoring logic are simplified  
- Some datasets and optimization layers are excluded  
- Architecture and design principles are fully documented  

Detailed implementation discussion available upon request.

---

## Elevator Summary

Offline manufacturability intelligence system combining:

- deterministic engineering analysis  
- CAD geometry evaluation  
- optional AI explanation layer  

Designed for privacy-sensitive industrial workflows where reliability, auditability, and offline capability matter.
