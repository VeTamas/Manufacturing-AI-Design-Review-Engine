#!/usr/bin/env python3
"""
Desktop launcher: starts Streamlit in a subprocess and opens it in a native window (pywebview).
Works fully offline. Use --no-webview to run Streamlit normally for debugging.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

DEBUG = os.environ.get("CNCR_DEBUG", "0") == "1"
HOST = os.environ.get("CNCR_UI_HOST", "127.0.0.1")
PORT = int(os.environ.get("CNCR_UI_PORT", "8501"))


def _wait_for_port(host: str, port: int, timeout: float = 20.0, interval: float = 0.3) -> bool:
    """Poll TCP connect until ready or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(interval)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch CNC Review Agent in desktop window")
    parser.add_argument(
        "--no-webview",
        action="store_true",
        help="Run Streamlit normally (no native window); useful for debugging",
    )
    args = parser.parse_args()

    streamlit_app = project_root / "app" / "streamlit_app.py"
    if not streamlit_app.exists():
        print(f"[run_desktop] ERROR: {streamlit_app} not found", file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(streamlit_app),
        "--server.address",
        HOST,
        "--server.port",
        str(PORT),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]

    print(f"[run_desktop] Starting Streamlit at {HOST}:{PORT} ...")
    proc = subprocess.Popen(
        cmd,
        cwd=str(project_root),
        env={**os.environ},
        stdout=None if DEBUG else subprocess.DEVNULL,
        stderr=None if DEBUG else subprocess.DEVNULL,
    )

    try:
        if not _wait_for_port(HOST, PORT):
            print(f"[run_desktop] ERROR: Streamlit did not become ready within timeout", file=sys.stderr)
            proc.terminate()
            proc.wait(timeout=5)
            return 1
        print(f"[run_desktop] Streamlit ready at http://{HOST}:{PORT}")

        if args.no_webview:
            print("[run_desktop] No webview; Streamlit running. Press Ctrl+C to stop.")
            proc.wait()
            return 0

        try:
            import webview
        except ImportError:
            print(
                "[run_desktop] pywebview not installed. Install with: pip install pywebview",
                file=sys.stderr,
            )
            print("[run_desktop] Falling back to --no-webview behavior.", file=sys.stderr)
            proc.wait()
            return 0

        url = f"http://{HOST}:{PORT}"
        print("[run_desktop] Opening native window ...")
        webview.create_window("CNC Review Agent", url)
        webview.start()
    except KeyboardInterrupt:
        if not DEBUG:
            print("\n[run_desktop] Shutting down ...")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("[run_desktop] Streamlit stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
