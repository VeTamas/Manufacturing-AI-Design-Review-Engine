"""
Optional runtime file-access tracer for packaging diagnostics.

Enable with: CNCR_TRACE_FILES=1

Logs file access to stdout and optionally to data/outputs/logs/filetrace.log.
When disabled (default), wrappers are no-ops that delegate to the real builtins.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENABLED = os.environ.get("CNCR_TRACE_FILES", "").strip() == "1"
_LOG_FILE: Path | None = None


def _log(operation: str, path: str | Path, extra: str = "") -> None:
    if not _ENABLED:
        return
    line = f"[filetrace] {operation} {path!s}{(' ' + extra) if extra else ''}\n"
    try:
        print(line, end="")
    except OSError:
        pass
    try:
        global _LOG_FILE
        if _LOG_FILE is None:
            # Resolve once: project root is parent of agent/
            root = Path(__file__).resolve().parents[2]
            log_path = root / "data" / "outputs" / "logs" / "filetrace.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            _LOG_FILE = log_path
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def traced_open(path: str | Path, mode: str = "r", **kwargs):
    """Open a file; when CNCR_TRACE_FILES=1, log the access. When disabled, same as builtin open."""
    p = Path(path) if not isinstance(path, Path) else path
    if _ENABLED:
        _log("open", p, mode)
    return open(p, mode, **kwargs)


def traced_read_text(path: str | Path, encoding: str = "utf-8") -> str:
    """Read path as text; when CNCR_TRACE_FILES=1, log the access. When disabled, same as Path.read_text."""
    p = Path(path) if not isinstance(path, Path) else path
    if _ENABLED:
        _log("read_text", p)
    return p.read_text(encoding=encoding)


def traced_faiss_read_index(path: str | Path):
    """Call faiss.read_index(path); when CNCR_TRACE_FILES=1, log the access. When disabled, same as faiss.read_index."""
    import faiss
    p = Path(path) if not isinstance(path, Path) else path
    if _ENABLED:
        _log("faiss_read_index", p)
    return faiss.read_index(str(p))


def is_tracing() -> bool:
    """Return True if file tracing is enabled."""
    return _ENABLED
