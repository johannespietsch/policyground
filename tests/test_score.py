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
