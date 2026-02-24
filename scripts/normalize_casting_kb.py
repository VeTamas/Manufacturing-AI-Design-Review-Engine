"""Normalize casting knowledge base files: append 'Agent Heuristics' section if missing."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KB_CASTING = PROJECT_ROOT / "knowledge_base" / "casting"

HEURISTICS_SECTION = """

## Agent Heuristics
- Missing draft/parting/ejection discussion for casting process → MEDIUM to HIGH risk
- Tight tolerances assumed as-cast without machining plan → HIGH risk
- Thick/hot-spot geometry without coring/feeding plan → MEDIUM to HIGH risk
- Poor access for finishing/inspection on critical features → HIGH risk
"""


def normalize_casting_kb() -> None:
    """Append Agent Heuristics section to casting .md files that don't have it."""
    md_files = list(KB_CASTING.rglob("*.md"))
    changed_count = 0
    
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        if "## Agent Heuristics" not in content:
            md_file.write_text(content + HEURISTICS_SECTION, encoding="utf-8")
            changed_count += 1
            print(f"Added heuristics section to: {md_file.relative_to(PROJECT_ROOT)}")
    
    print(f"\nNormalization complete: {changed_count} file(s) updated out of {len(md_files)} total.")


if __name__ == "__main__":
    normalize_casting_kb()
