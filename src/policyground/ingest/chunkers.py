"""Chunkers compared in M2 (METRICS, "hit@5 per chunker × embedder")."""

from __future__ import annotations

import re


def naive(text: str, size: int = 800) -> list[str]:
    """Fixed-size character windows, no overlap. Deliberately ignores structure:
    it will cut a rule off from its exception (PLAN M1 trap, D13)."""
    return [text[i : i + size] for i in range(0, len(text), size)]


# Sections that state a rule and its exceptions: kept in one chunk (PLAN M2).
BOOKING_TERMS = ("Cancellation", "Rate plans")


def structural(text: str) -> list[str]:
    """One chunk per '## ' section, with Cancellation and Rate plans merged so the
    non-refundable exception stays with the cancellation rule. Every chunk starts
    with the document's title and ID line (D26), so a chunk always says which
    property, brand or chain it is about (INCIDENTS #1)."""
    head, *parts = re.split(r"(?m)^## ", text)
    header = head.strip()
    sections = {}
    for part in parts:
        title, _, body = part.partition("\n")
        sections[title.strip()] = body.strip()

    chunks, merged = [], []
    for title, body in sections.items():
        if title in BOOKING_TERMS:
            merged.append(f"## {title}\n\n{body}")
            if len(merged) == sum(t in sections for t in BOOKING_TERMS):
                chunks.append(f"{header}\n\n" + "\n\n".join(merged))
        else:
            chunks.append(f"{header}\n\n## {title}\n\n{body}")
    return chunks


CHUNKERS = {"naive-800": naive, "structural-v1": structural}
