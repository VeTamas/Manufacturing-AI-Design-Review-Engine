#!/usr/bin/env python3
"""Local demo: runs the STEP CLI on a golden part (or path from argv)."""
from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        default = project_root / "tests" / "golden" / "parts" / "cnc" / "CNC1.step"
        if default.exists():
            sys.argv.append(str(default))
            print(f"No path given. Using: {default}\n")
        else:
            print("Usage: python scripts/run_local_demo.py <path_to_step_file>", file=sys.stderr)
            sys.exit(1)
    from scripts.run_step_cli import main
    sys.exit(main())
