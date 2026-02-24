# Dev environment: set local Ollama as default (run after activating venv).
# Usage: .\scripts\dev_env.ps1
# CNCR_OFFLINE disables cloud only; local Ollama remains active.
$env:LLM_MODE = "local"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "jamba2-3b-q6k"
$env:LLM_TIMEOUT_SECONDS = "180"
Write-Host "LLM: local (Ollama) | OLLAMA_BASE_URL=$env:OLLAMA_BASE_URL | OLLAMA_MODEL=$env:OLLAMA_MODEL"
