"""Pull dates, times and EUR amounts out of free text (D18 follow-up: regex scoring).

The M2 validator reuses this, so it has to handle what the model actually
writes: "2026-12-17 14:00", "17 December 2026 at 2:00 PM", "December 17, 2026, 14:00",
"EUR 25", "€25", "25 euros".
"""

from __future__ import annotations

import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
MONTHS |= {m[:3]: i for m, i in list(MONTHS.items())}
_MON = r"(?P<mon>" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"

_ISO = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b")
_DMY = re.compile(rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON},?\s+(?P<y>\d{{4}})\b", re.I)
_MDY = re.compile(rf"\b{_MON}\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y>\d{{4}})\b", re.I)

_TIME_24 = re.compile(r"\b(?P<h>[01]?\d|2[0-3])[:.](?P<mi>[0-5]\d)\b(?!\s*[ap]\.?m\b)", re.I)
_TIME_12 = re.compile(r"\b(?P<h>1[0-2]|0?[1-9])(?:[:.](?P<mi>[0-5]\d))?\s*(?P<ap>[ap])\.?m\.?(?![a-z])", re.I)
_NOON = re.compile(r"\bnoon\b|\bmidday\b", re.I)
_MIDNIGHT = re.compile(r"\bmidnight\b", re.I)

_EUR = re.compile(
    r"(?:\bEUR\s*|€\s*)(?P<a>\d+(?:[.,]\d{1,2})?)"
    r"|(?P<b>\d+(?:[.,]\d{1,2})?)\s*(?:EUR\b|€|euros?\b)", re.I)


def dates(text: str) -> set[str]:
    found = set()
    for m in _ISO.finditer(text):
        found.add(_iso(int(m["y"]), int(m["m"]), int(m["d"])))
    for rx in (_DMY, _MDY):
        for m in rx.finditer(text):
            found.add(_iso(int(m["y"]), MONTHS[m["mon"].lower()], int(m["d"])))
    found.discard(None)
    return found


def times(text: str) -> set[str]:
    found = set()
    # Strip ISO dates first so "2026-12-17" isn't read as a time.
    text = _ISO.sub(" ", text)
    for m in _TIME_12.finditer(text):
        h = int(m["h"]) % 12 + (12 if m["ap"].lower() == "p" else 0)
        found.add(f"{h:02d}:{int(m['mi'] or 0):02d}")
    for m in _TIME_24.finditer(_TIME_12.sub(" ", text)):
        found.add(f"{int(m['h']):02d}:{m['mi']}")
    if _NOON.search(text):
        found.add("12:00")
    if _MIDNIGHT.search(text):
        found.add("00:00")
    return found


def eur_amounts(text: str) -> set[float]:
    return {float((m["a"] or m["b"]).replace(",", ".")) for m in _EUR.finditer(text)}


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None
