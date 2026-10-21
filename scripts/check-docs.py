#!/usr/bin/env python3
"""Validate local Markdown links and the required architecture diagrams."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
REQUIRED_DIAGRAMS = {
    "System Overview",
    "IP Packet Flow",
    "RC Input Flow",
    "Startup Sequence",
    "Module Relationship",
}


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.md"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        markdown_files = sorted(
            root / item
            for item in result.stdout.decode("utf-8").split("\0")
            if item
        )
    else:
        markdown_files = sorted(root.rglob("*.md"))
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        for raw_target in LINK_RE.findall(text):
            target = raw_target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / unquote(target)).resolve()
            if not resolved.exists():
                errors.append(f"broken link in {path.relative_to(root)}: {raw_target}")

    architecture = root / "docs" / "architecture.md"
    architecture_text = architecture.read_text(encoding="utf-8")
    if architecture_text.count("```mermaid") != 5:
        errors.append("docs/architecture.md must contain exactly five Mermaid blocks")
    if architecture_text.count("```") != 10:
        errors.append("docs/architecture.md has unbalanced or unexpected code fences")
    headings = set(re.findall(r"^## (.+)$", architecture_text, re.MULTILINE))
    missing = sorted(REQUIRED_DIAGRAMS - headings)
    if missing:
        errors.append("missing architecture diagram headings: " + ", ".join(missing))

    if errors:
        print("Documentation check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"Documentation check passed ({len(markdown_files)} Markdown files, 5 Mermaid diagrams)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
