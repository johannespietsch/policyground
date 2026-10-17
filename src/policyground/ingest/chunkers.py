"""Chunkers. M1 has only the naive one; M2 adds a structural chunker to compare."""

from __future__ import annotations


def naive(text: str, size: int = 800) -> list[str]:
    """Fixed-size character windows, no overlap. Deliberately ignores structure:
    it will cut a rule off from its exception (PLAN M1 trap, D13)."""
    return [text[i : i + size] for i in range(0, len(text), size)]


CHUNKERS = {"naive-800": naive}
