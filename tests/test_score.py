import pytest

from policyground.eval.normalize import dates, eur_amounts, times
from policyground.eval.score import is_correct


@pytest.mark.parametrize("text,expected", [
    ("Free cancellation until 2026-12-17 14:00.", ("2026-12-17", "14:00")),
    ("Cancel by 17 December 2026 at 2:00 PM.", ("2026-12-17", "14:00")),
    ("Until December 17, 2026, 2pm.", ("2026-12-17", "14:00")),
    ("Until 2 p.m. on 17th Dec 2026.", ("2026-12-17", "14:00")),
    ("By noon on 5 Nov 2026.", ("2026-11-05", "12:00")),
])
def test_datetime_formats(text, expected):
    d, t = expected
    assert d in dates(text)
    assert t in times(text)


def test_iso_date_is_not_read_as_a_time():
    assert times("on 2026-12-17") == set()


@pytest.mark.parametrize("text", ["EUR 25 per night", "€25", "25 euros", "25.00 EUR"])
def test_eur(text):
    assert 25.0 in eur_amounts(text)


def test_abstain_flag_governs():
    exp = {"kind": "no_free_cancellation", "value": None}
    assert not is_correct(exp, "They cannot cancel free of charge.", abstain=True)
    assert is_correct(exp, "They cannot cancel free of charge.", abstain=False)


def test_wrong_time_fails():
    exp = {"kind": "datetime", "value": "2026-12-17 14:00"}
    assert not is_correct(exp, "Until 2026-12-17 at 15:00.", abstain=False)


def test_supported_needs_governing_evidence():
    from policyground.eval.score import is_supported
    gov = {"docs": ["brand-C5-B1"], "facts": ["kg:P042:cancel_window_hours"]}
    assert not is_supported(gov, ["P042#0", "chain-C5#0"])  # INCIDENTS #2 (Q24)
    assert is_supported(gov, ["brand-C5-B1#0"])
    assert is_supported(gov, ["kg:P042:cancel_window_hours"])


def test_fee_and_no_charge():
    fee = {"kind": "fee", "value": "first_night"}
    assert is_correct(fee, "They will be charged the first night's rate.", abstain=False)
    assert not is_correct(fee, "They will be charged 50% of the booking.", abstain=False)
    none = {"kind": "no_charge", "value": None}
    assert is_correct(none, "Nothing: they are still inside the free-cancellation window.", abstain=False)
    assert not is_correct(none, "This is not free of charge; the first night is charged.", abstain=False)


def test_append_to_table_targets_its_own_section(tmp_path):
    from policyground.eval.metrics_md import append_to_table
    p = tmp_path / "M.md"
    p.write_text("## A\n\n| a |\n|---|\n| 1 |\n\n## B\n\n| b |\n|---|\n| 2 |\n")
    append_to_table(p, "## A", "| 1b |")
    append_to_table(p, "## B", "| 2b |")
    assert p.read_text() == "## A\n\n| a |\n|---|\n| 1 |\n| 1b |\n\n## B\n\n| b |\n|---|\n| 2 |\n| 2b |\n"


def test_phrase_without_value_key():
    """Onboarding finding: phrase items have no `value`; the scorer used to KeyError."""
    exp = {"kind": "phrase", "patterns": [r"not covered|excluded"], "reject": [r"\d{4}-\d{2}-\d{2}"]}
    assert is_correct(exp, "Baggage is excluded on this policy, so it is not covered.", abstain=False)
    assert not is_correct(exp, "Not covered; file by 2026-12-01 anyway.", abstain=False)
