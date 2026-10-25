"""Deterministic answer validator (PLAN M2, D24 strict; generic over tenants, D44).

Every date, time, EUR amount and duration (hours/days) in a non-abstained answer must
be backed by evidence the answer CITES: a cited KG fact, a cited chunk's text, or the
question itself. Which facts are amounts, durations or times, and how a deadline follows
from facts, comes from the tenant spec (facts[].unit/type, deadlines[]).

Claim-level checks on top of the value checks (INCIDENTS #3, #5):
  - a stated deadline ("until/by <date> [<time>]") must BE a deadline computed from a
    cited offset fact, not merely consist of values found somewhere in the evidence;
  - a duration stated as the window ("until/up to/within N <unit>", "N-<unit> window")
    must match a cited offset fact, not a gap derived from the question.

The LLM's output stays untrusted until this passes. No LLM is involved here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from policyground.eval import normalize

_UNIT_RX = {
    "hours": r"(?:hours?|hrs?|h)",
    "days": r"(?:days?)",
}
# "EUR 0" is backed only when the answer says nothing is charged (Q43 false positive).
_NO_CHARGE = re.compile(r"\bno (?:charge|fee|cost)|\bnothing\b|not be charged|free of charge", re.I)
_DEADLINE = re.compile(r"\b(?:until|by|no later than|up until)\b(?P<clause>[^,;()]{0,45})", re.I)
_CLAUSE_END = re.compile(r"\b(?:before|prior|hours?|days?|after|when|which|for)\b|[.!?](?:\s|$)", re.I)


def _durations(text: str, unit: str) -> set[int]:
    return {int(n) for n in re.findall(rf"\b(\d{{1,3}})\s*(?:-\s*)?{_UNIT_RX[unit]}\b", text, re.I)}


def _window_claims(text: str, unit: str) -> set[int]:
    u = _UNIT_RX[unit]
    rx = re.compile(rf"\b(?:until|up to|at least|no later than|within)\s+(\d{{1,3}})\s*(?:-\s*)?{u}"
                    rf"|\b(\d{{1,3}})[- ]{u}\s+(?:free[- ])?(?:cancellation\s+)?window", re.I)
    return {int(a or b) for a, b in rx.findall(text)}


@dataclass
class Verdict:
    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _units(spec) -> list[str]:
    return sorted({f["unit"] for f in spec.facts.values() if f.get("unit") in _UNIT_RX})


def validate(question: str, answer: str, abstain: bool, raw_citations: list[str],
             facts: list[dict], chunks: list[dict], spec) -> Verdict:
    facts_by_id = {f["id"]: f for f in facts}
    chunks_by_id = {c["id"]: c for c in chunks}
    claims = {"date": normalize.dates(answer), "time": normalize.times(answer),
              "eur": normalize.eur_amounts(answer)}
    for u in _units(spec):
        claims[u] = _durations(answer, u)
        claims[f"window_{u}"] = _window_claims(answer, u)

    if abstain:
        # Nothing to reject (the flag governs). But an abstention that asserts values
        # nothing shown supports is the INCIDENTS #1 / Q21 pattern: warn. Abstentions
        # that mention real values as context ("the only fee listed is EUR 20") are
        # fine, so back-check leniently against everything shown, cited or not.
        shown = _backed_values(question, facts, "\n".join(c["text"] for c in chunks), spec)
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

    backed = _backed_values(question, cited_facts, cited_text, spec)
    if _NO_CHARGE.search(answer):
        backed["eur"].add(0.0)
    for kind, values in claims.items():
        for v in sorted(values, key=str):
            if v not in backed[kind]:
                problems.append(f"{kind} {v!r} is not backed by any cited evidence")
    for d, t in _deadline_claims(answer):
        if (d, t) not in backed["deadline"] and not (t is None and d in backed["deadline_dates"]):
            problems.append(f"deadline {d}{' ' + t if t else ''} doesn't follow from the cited offset"
                            f"{' and anchor time' if t else ''}")
    return Verdict(not problems, problems)


def _deadline_claims(answer: str) -> set[tuple[str, str | None]]:
    out = set()
    for m in _DEADLINE.finditer(answer):
        clause = m["clause"]
        if end := _CLAUSE_END.search(clause):
            clause = clause[:end.start()]
        dates, times = normalize.dates(clause), normalize.times(clause)
        if len(dates) == 1 and len(times) <= 1:
            out.add((dates.pop(), times.pop() if times else None))
    return out


def _backed_values(question: str, cited_facts: list[dict], cited_text: str, spec) -> dict[str, set]:
    def fact_values(keys):
        return {f["value"] for f in cited_facts if f["key"] in keys}

    q_dates, q_times = normalize.dates(question), normalize.times(question)
    units = _units(spec)
    offsets = {u: {int(v) for v in fact_values(spec.facts_with_unit(u))} | _durations(cited_text, u)
               for u in units}
    out: dict[str, set] = {
        "date": q_dates | normalize.dates(cited_text),
        "time": fact_values(spec.facts_of_type("time")) | normalize.times(cited_text) | q_times,
        "eur": {float(v) for v in fact_values(spec.facts_with_unit("EUR"))} | normalize.eur_amounts(cited_text),
        "deadline": set(), "deadline_dates": set(),
    }
    derived = {u: set() for u in units}
    for rule in spec.deadlines:
        unit = spec.facts[rule["offset"]]["unit"]
        windows = {int(v) for v in fact_values([rule["offset"]])} | _durations(cited_text, unit)
        step = timedelta(hours=1) if unit == "hours" else timedelta(days=1)
        sign = -1 if rule["direction"] == "before" else 1
        rule_dates = _anchor_dates(question, rule.get("anchor_date_hints", []))
        if rule.get("anchor_time"):
            anchors = (fact_values([rule["anchor_time"]])
                       | _anchor_times(cited_text, rule.get("anchor_text_hints", [])))
        else:
            anchors = {None}
        for d in rule_dates:
            for t in anchors:
                base = datetime.fromisoformat(f"{d} {t or '00:00'}")
                for w in windows:
                    dl = base + sign * w * step
                    out["date"].add(dl.date().isoformat())
                    out["deadline_dates"].add(dl.date().isoformat())
                    if t:
                        out["time"].add(dl.strftime("%H:%M"))
                    out["deadline"].add((dl.date().isoformat(), dl.strftime("%H:%M") if t else None))
                # Gaps between a moment in the question and the anchor ("cancels on
                # 2026-11-29 at 16:00" -> 96 hours before a 2026-12-03 16:00 check-in).
                for qd in q_dates:
                    for qt in (q_times or {None}):
                        moment = datetime.fromisoformat(f"{qd} {qt or '00:00'}")
                        gap = (base - moment) if sign < 0 else (moment - base)
                        if gap > timedelta(0) and gap % step == timedelta(0):
                            derived[unit].add(int(gap / step))
    for u in units:
        out[u] = offsets[u] | _durations(question, u) | derived[u]
        out[f"window_{u}"] = offsets[u]
    return out


def _anchor_dates(question: str, hints: list[str]) -> set[str]:
    """The question dates a deadline rule may start from. Without hints: every date in
    the question. With anchor_date_hints (e.g. [incident, happened]): only dates in a
    clause containing a hint, so with two rules (claim window from the incident, waiting
    period from the policy start) a date computed with the wrong rule can't validate."""
    if not hints:
        return normalize.dates(question)
    out = set()
    for clause in re.split(r"[,;.?!]|\band\b|\bbut\b", question):
        if any(h in clause.lower() for h in hints):
            out |= normalize.dates(clause)
    return out


def _anchor_times(text: str, hints: list[str]) -> set[str]:
    """Anchor times stated in chunk text, e.g. "Check-in starts at 15:00". Only sentences
    containing one of the spec's anchor_text_hints count, so a check-out time is never
    taken for the check-in time."""
    out = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if any(h in sentence.lower() for h in hints):
            out |= normalize.times(sentence)
    return out
