#!/usr/bin/env python3
"""Fail when a publication tree contains private or generated material."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


DENIED_DIRS = {
    ".agents",
    ".claude",
    ".codex",
    ".cxx",
    ".gradle",
    "backup",
    "hardware",
    "output",
    "ref",
    "tmp",
    "Testing",
}
DENIED_NAMES = {"AGENTS.md", "CLAUDE.md", "adbkey", "adbkey.pub", "local.properties"}
DENIED_SUFFIXES = {
    ".apk",
    ".aab",
    ".bin",
    ".img",
    ".jks",
    ".key",
    ".keystore",
    ".pcap",
    ".pcapng",
    ".squashfs",
}
TEXT_SUFFIXES = {
    "",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".json",
    ".kt",
    ".kts",
    ".md",
    ".properties",
    ".ps1",
    ".py",
    ".service",
    ".sh",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}
SECRET_PATTERNS = {
    "private key material": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/]"
    ),
    "Windows user path": re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\\\s]+", re.I),
    "Unix home path": re.compile(r"/home/[^/\s]+/"),
    "sshpass invocation": re.compile(r"\bsshpass\b", re.I),
    "literal password assignment": re.compile(
        r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*['\"]?(?!<|\$|\{)([^'\"\s]{4,})"
    ),
    "known private ADB endpoint": re.compile(r"172\.24\.91\.112(?::\d+)?"),
}


def is_vendor_header(path: Path) -> bool:
    return "gstreamer_libs_min" in path.parts


def inspect(root: Path) -> list[str]:
    findings: list[str] = []
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        paths = [root / item for item in result.stdout.decode("utf-8").split("\0") if item]
    else:
        paths = [path for path in root.rglob("*") if path.is_file()]

    for path in sorted(paths):
        relative = path.relative_to(root)
        parts = set(relative.parts)
        denied_parts = sorted(
            part for part in relative.parts[:-1]
            if part in DENIED_DIRS or part.startswith("build-")
        )
        if denied_parts:
            findings.append(f"denied directory content: {relative}")
        if relative.as_posix() == "scripts/check-public-tree.py":
            continue
        if path.name in DENIED_NAMES:
            findings.append(f"denied file: {relative}")
        if path.suffix.lower() in DENIED_SUFFIXES:
            findings.append(f"denied artifact: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES or is_vendor_header(relative):
            continue
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label}: {relative}")
    return findings


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    findings = inspect(root)
    if findings:
        print("Public tree check failed:")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("Public tree check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
