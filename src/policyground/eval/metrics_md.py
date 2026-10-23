"""Append rows to a named table in METRICS.md. Several tables live in one file, so
rows must go after the last row of their own section, not at the end of the file."""

from __future__ import annotations

from pathlib import Path


def append_to_table(path: Path, section: str, row: str) -> None:
    lines = path.read_text().splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith(section))
    end = start + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    last_row = max(i for i in range(start, end) if lines[i].startswith("|"))
    lines.insert(last_row + 1, row if row.endswith("\n") else row + "\n")
    path.write_text("".join(lines))
