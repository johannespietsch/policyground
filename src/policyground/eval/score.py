"""Deterministic scoring of one answer against a golden expectation (no LLM judge).

Rules (deliberately simple; known leniency is noted):
  datetime  correct iff not abstained, and the expected date AND expected time both
            appear in the answer. Lenient: other dates may appear too (e.g. the
            check-in date), and date and time aren't checked to be adjacent.
  time      not abstained and the expected time appears.
  eur       not abstained and the expected amount appears as a EUR amount.
  no_free_cancellation  not abstained and the answer says it can't be cancelled
            free / is non-refundable.
  fee       not abstained and the answer names the expected late-cancellation fee.
  no_charge not abstained and the answer says nothing is charged.
  abstain   the `abstain` flag is set. The flag governs, not the wording.
"""

from __future__ import annotations

import re

from policyground.eval import normalize

_NO_FREE = re.compile(
    r"non-?refundable|not refundable|no refund|cannot (?:be )?cancel|can't (?:be )?cancel"
    r"|no free cancellation|not (?:be )?cancell?able", re.I)


_FEE = {
    "first_night": re.compile(r"first night", re.I),
    "full_stay": re.compile(r"full (?:cost|amount|price|value)|(?:entire|whole|full) stay", re.I),
    "50_percent": re.compile(r"\b50\s*%|\b50 percent|\bhalf\b", re.I),
}
_NO_CHARGE = re.compile(
    r"no (?:charge|fee|cancellation fee|cost)|nothing|(?:won't|will not|wouldn't|would not|not) be charged"
    r"|(?<!not )free of charge|without (?:any )?charge", re.I)


def is_correct(expected: dict, answer: str, abstain: bool) -> bool:
    kind, value = expected["kind"], expected["value"]
    if kind == "abstain":
        return abstain
    if abstain:
        return False
    if kind == "datetime":
        d, t = value.split(" ")
        return d in normalize.dates(answer) and t in normalize.times(answer)
    if kind == "time":
        return value in normalize.times(answer)
    if kind == "eur":
        return float(value) in normalize.eur_amounts(answer)
    if kind == "no_free_cancellation":
        return bool(_NO_FREE.search(answer))
    if kind == "fee":
        others = [rx for k, rx in _FEE.items() if k != value]
        return bool(_FEE[value].search(answer)) and not any(rx.search(answer) for rx in others)
    if kind == "no_charge":
        return bool(_NO_CHARGE.search(answer)) and not any(rx.search(answer) for rx in _FEE.values())
    raise ValueError(kind)


def is_supported(governing: dict, citations: list[str]) -> bool:
    """At least one citation is a chunk of a governing doc or a governing KG fact."""
    docs = set(governing["docs"])
    return any(c in governing["facts"] or c.split("#")[0] in docs for c in citations)
