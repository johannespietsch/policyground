from policyground.ingest.chunkers import naive


def test_naive_chunker_covers_text_without_overlap():
    text = "x" * 1700
    chunks = naive(text)
    assert [len(c) for c in chunks] == [800, 800, 100]
    assert "".join(chunks) == text


def test_structural_keeps_exception_with_rule_and_adds_header():
    from policyground.ingest.chunkers import structural
    doc = ("# Hotel X\n\nProperty ID: P1 · Brand: B · Chain: C\n\n## Overview\n\nNice.\n\n"
           "## Cancellation\n\nFree until 48 hours before.\n\n## Pets\n\nNo pets.\n\n"
           "## Rate plans\n\n- **Non-Refundable Rate** — no refund.\n")
    chunks = structural(doc)
    assert all(c.startswith("# Hotel X\n\nProperty ID: P1") for c in chunks)
    booking = [c for c in chunks if "48 hours" in c]
    assert len(booking) == 1 and "Non-Refundable" in booking[0]
    assert len(chunks) == 3  # overview, booking terms (cancellation + rate plans), pets
