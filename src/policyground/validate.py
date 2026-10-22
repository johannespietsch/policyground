"""Deterministic answer validator (PLAN M2, D24: strict).

Every date, time, EUR amount and "N hours" in a non-abstained answer must be backed
by evidence the answer CITES: a cited KG fact, a cited chunk's text, or the question
itself. Deadlines count as backed when they follow from a cited window and a backed
check-in time on a date from the question.

The LLM's output stays untrusted until this passes. No LLM is involved here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from policyground.eval import normalize

_HOURS = re.compile(r"\b(\d{1,3})\s*(?:-\s*)?(?:hours?|hrs?|h)\b", re.I)
# Hours stated AS the cancellation window. These must match a cited window; other
# hour mentions may also be a gap derived from the question's timestamps.
_WINDOW_HOURS = re.compile(
    r"\b(?:until|up to|at least|no later than|within)\s+(\d{1,3})\s*(?:-\s*)?hours?"
    r"|\b(\d{1,3})[- ]hours?\s+(?:free[- ])?(?:cancellation\s+)?window", re.I)
# A deadline claim: "until / by / no later than <date and time>". The clause is cut
# at the first comma or clause word, so "...72 hours before the 14:00 check-in on
# 2026-12-17" (the arrival, not the deadline) is never read as the claimed deadline.
_DEADLINE = re.compile(r"\b(?:until|by|no later than|up until)\b(?P<clause>[^,;()]{0,45})", re.I)
# "EUR 0" is backed only when the answer says nothing is charged (Q43 false positive).
_NO_CHARGE = re.compile(r"\bno (?:charge|fee|cost)|\bnothing\b|not be charged|free of charge", re.I)
_CLAUSE_END = re.compile(r"\b(?:before|prior|hours?|after|when|which|for)\b|[.!?](?:\s|$)", re.I)


@dataclass
class Verdict:
    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate(question: str, answer: str, abstain: bool, raw_citations: list[str],
             facts: list[dict], chunks: list[dict]) -> Verdict:
    facts_by_id = {f["id"]: f for f in facts}
    chunks_by_id = {c["id"]: c for c in chunks}
    claims = {
        "date": normalize.dates(answer),
        "time": normalize.times(answer),
        "eur": normalize.eur_amounts(answer),
        "hours": {int(h) for h in _HOURS.findall(answer)},
        "window_hours": {int(a or b) for a, b in _WINDOW_HOURS.findall(answer)},
    }

    if abstain:
        # Nothing to reject (the flag governs). But an abstention that asserts values
        # nothing shown supports is the INCIDENTS #1 / Q21 pattern: warn. Abstentions
        # that mention real values as context ("the only fee listed is EUR 20") are
        # fine, so back-check leniently against everything shown, cited or not.
        shown = _backed_values(question, facts, "\n".join(c["text"] for c in chunks))
        shown["eur"].add(0.0)
        stray = [f"{k} {v!r}" for k, vals in claims.items() for v in vals if v not in shown[k]]
        if stray:
            return Verdict(True, warnings=[f"abstained but states unbacked values: {stray}"])
        return Verdict(True)

    problems = []
    invented = [c for c in raw_citations if c not in facts_by_id and c not in chunks_by_id]
    if invented:
        problems.append(f"cites evidence it was never shown: {invented}")
    cited_facts = [facts_by_id[c] for c in raw_citations if c in facts_by_id]
    cited_text = "\n".join(chunks_by_id[c]["text"] for c in raw_citations if c in chunks_by_id)
    if not cited_facts and not cited_text:
        problems.append("no valid citations")

    backed = _backed_values(question, cited_facts, cited_text)
    if _NO_CHARGE.search(answer):
        backed["eur"].add(0.0)
    for kind, values in claims.items():
        for v in sorted(values, key=str):
            if v not in backed[kind]:
                problems.append(f"{kind} {v!r} is not backed by any cited evidence")
    # Claim-level check (INCIDENTS #3): a stated deadline must BE a computed deadline,
    # not merely consist of values that appear somewhere in the evidence.
    for d, t in _deadline_claims(answer):
        if (d, t) not in backed["deadline"]:
            problems.append(f"deadline {d} {t} doesn't follow from the cited window and check-in time")
    return Verdict(not problems, problems)


def _deadline_claims(answer: str) -> set[tuple[str, str]]:
    claims = set()
    for m in _DEADLINE.finditer(answer):
        clause = m["clause"]
        if end := _CLAUSE_END.search(clause):
            clause = clause[:end.start()]
        dates, times = normalize.dates(clause), normalize.times(clause)
        if len(dates) == 1 and len(times) == 1:
            claims.add((dates.pop(), times.pop()))
    return claims


def _backed_values(question: str, cited_facts: list[dict], cited_text: str) -> dict[str, set]:
    def fact_values(key):
        return {f["value"] for f in cited_facts if f["key"] == key}

    windows = {int(v) for v in fact_values("cancel_window_hours")} | {int(h) for h in _HOURS.findall(cited_text)}
    q_hours = {int(h) for h in _HOURS.findall(question)}
    checkin_times = fact_values("check_in_time") | _checkin_times_in(cited_text)
    q_dates = normalize.dates(question)

    deadline_dates, deadline_times, deadlines = set(), set(), set()
    for d in q_dates:
        for t in checkin_times:
            arrival = datetime.fromisoformat(f"{d} {t}")
            for w in windows:
                dl = arrival - timedelta(hours=w)
                deadline_dates.add(dl.date().isoformat())
                deadline_times.add(dl.strftime("%H:%M"))
                deadlines.add((dl.date().isoformat(), dl.strftime("%H:%M")))

    # Hours between a moment stated in the question and the arrival ("cancels on
    # 2026-11-29 at 16:00" -> 96 hours before a 2026-12-03 16:00 check-in).
    q_moments = [datetime.fromisoformat(f"{d} {t}") for d in q_dates for t in normalize.times(question)]
    arrivals = [datetime.fromisoformat(f"{d} {t}") for d in q_dates for t in checkin_times]
    derived_hours = {int((a - m).total_seconds() // 3600) for a in arrivals for m in q_moments
                     if a > m and (a - m).total_seconds() % 3600 == 0}

    return {
        "date": q_dates | deadline_dates | normalize.dates(cited_text),
        "time": (fact_values("check_in_time") | fact_values("check_out_time")
                 | normalize.times(cited_text) | normalize.times(question) | deadline_times),
        "eur": {float(v) for v in fact_values("pet_fee_eur")} | normalize.eur_amounts(cited_text),
        "hours": windows | q_hours | derived_hours,
        "window_hours": windows,
        "deadline": deadlines,
    }


def _checkin_times_in(text: str) -> set[str]:
    """Check-in times stated in chunk text ("Check-in starts at 15:00")."""
    out = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = sentence.lower()
        if "check in" in s or "check-in" in s or "arrival" in s or "rooms are available" in s:
            out |= normalize.times(sentence)
    return out
