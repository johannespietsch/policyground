"""Deterministic scoring of one answer against a golden expectation (no LLM judge).

Rules (deliberately simple; known leniency is noted):
  datetime  correct iff not abstained, and the expected date AND expected time both
            appear in the answer. Lenient: other dates may appear too (e.g. the
            check-in date), and date and time aren't checked to be adjacent.
  time      not abstained and the expected time appears.
  eur       not abstained and the expected amount appears as a EUR amount.
  no_free_cancellation  not abstained and the answer says it can't be cancelled
            free / is non-refundable.
  abstain   the `abstain` flag is set. The flag governs, not the wording.
"""

from __future__ import annotations

import re

from policyground.eval import normalize

_NO_FREE = re.compile(
    r"non-?refundable|not refundable|no refund|cannot (?:be )?cancel|can't (?:be )?cancel"
    r"|no free cancellation|not (?:be )?cancell?able", re.I)


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
    raise ValueError(kind)
