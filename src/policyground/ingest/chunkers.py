"""Chunkers compared in M2 (METRICS, "hit@5 per chunker × embedder")."""

from __future__ import annotations

import re


def naive(text: str, size: int = 800) -> list[str]:
    """Fixed-size character windows, no overlap. Deliberately ignores structure:
    it will cut a rule off from its exception (PLAN M1 trap, D13)."""
    return [text[i : i + size] for i in range(0, len(text), size)]


def structural(text: str, keep_together: tuple[str, ...] = ()) -> list[str]:
    """One chunk per '## ' section. Sections named in the tenant spec's
    chunking.keep_together (hotels: Cancellation + Rate plans) are merged into one
    chunk, so an exception stays with its rule (PLAN M2). Every chunk starts
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
        if title in keep_together:
            merged.append(f"## {title}\n\n{body}")
            if len(merged) == sum(t in sections for t in keep_together):
                chunks.append(f"{header}\n\n" + "\n\n".join(merged))
        else:
            chunks.append(f"{header}\n\n## {title}\n\n{body}")
    return chunks


CHUNKERS = {"naive-800": lambda text, spec=None: naive(text),
            "structural-v1": lambda text, spec=None: structural(text, spec.keep_together if spec else ())}
