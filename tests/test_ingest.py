from policyground.ingest.chunkers import naive


def test_naive_chunker_covers_text_without_overlap():
    text = "x" * 1700
    chunks = naive(text)
    assert [len(c) for c in chunks] == [800, 800, 100]
    assert "".join(chunks) == text
