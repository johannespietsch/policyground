"""Validator behaviour on hand-built faults (D23). The measured catch rate over real
answers comes from `python -m policyground.eval.faults`."""

from policyground.validate import validate

Q = "A guest checks in at Meridian Urban Munich Central on 2026-12-17. Until when can they cancel free of charge?"
FACTS = [
    {"id": "kg:P042:cancel_window_hours", "key": "cancel_window_hours", "value": 72},
    {"id": "kg:P042:check_in_time", "key": "check_in_time", "value": "14:00"},
    {"id": "kg:P042:pet_fee_eur", "key": "pet_fee_eur", "value": 40},
]
CHUNKS = [{"id": "P042#0", "text": "Cancellation follows the Meridian Urban brand standard policy."}]
CITE = ["kg:P042:cancel_window_hours", "kg:P042:check_in_time"]
GOOD = "Free cancellation until 2026-12-14 at 14:00, 72 hours before the 14:00 check-in."


def v(answer, citations=CITE, abstain=False):
    return validate(Q, answer, abstain, citations, FACTS, CHUNKS)


def test_correct_answer_passes():
    assert v(GOOD).ok


def test_wrong_date_rejected():
    assert not v(GOOD.replace("2026-12-14", "2026-12-15")).ok


def test_wrong_time_rejected():
    assert not v(GOOD.replace("at 14:00", "at 15:00")).ok


def test_wrong_window_rejected():
    assert not v(GOOD.replace("72 hours", "48 hours")).ok


def test_uncited_correct_value_rejected():
    # Strict (D24): the value is right, but the window fact isn't cited.
    assert not v(GOOD, citations=["kg:P042:check_in_time"]).ok


def test_invented_citation_rejected():
    assert not v(GOOD, citations=CITE + ["P999#0"]).ok


def test_wrong_amount_rejected():
    assert not v("The pet fee is EUR 45 per night.", citations=["kg:P042:pet_fee_eur"]).ok
    assert v("The pet fee is EUR 40 per night.", citations=["kg:P042:pet_fee_eur"]).ok


def test_abstain_with_unbacked_values_warns_but_passes():
    verdict = v("I can't confirm, but probably 2026-12-20 at 09:00.", citations=[], abstain=True)
    assert verdict.ok and verdict.warnings


def test_abstain_mentioning_real_values_does_not_warn():
    verdict = v("No city tax info; the only per-night charge listed is the EUR 40 pet fee.",
                citations=[], abstain=True)
    assert verdict.ok and not verdict.warnings


def test_deadline_equal_to_checkin_moment_rejected():
    # INCIDENTS #3: 24h window; the broken deadline equals the check-in moment.
    q = "A guest checks in at X on 2026-11-25. Until when can they cancel free of charge?"
    facts = [{"id": "kg:P1:cancel_window_hours", "key": "cancel_window_hours", "value": 24},
             {"id": "kg:P1:check_in_time", "key": "check_in_time", "value": "16:00"}]
    cites = [f["id"] for f in facts]
    good = "Free cancellation until 2026-11-24 at 16:00, 24 hours before the 16:00 check-in on 2026-11-25."
    bad = good.replace("until 2026-11-24", "until 2026-11-25")
    assert validate(q, good, False, cites, facts, []).ok
    assert not validate(q, bad, False, cites, facts, []).ok


def test_until_time_on_date_form():
    assert v("They can cancel free of charge until 14:00 on 2026-12-14.").ok
    assert not v("They can cancel free of charge until 14:00 on 2026-12-17.").ok
