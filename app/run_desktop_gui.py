#!/usr/bin/env python3
"""
GUI entrypoint for PyInstaller: runs the desktop launcher with no console and no stdout/stderr.
Use this as the --onefile or spec entry point for a windowed Windows EXE.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path (when run as script or from PyInstaller bundle)
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from app.run_desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
