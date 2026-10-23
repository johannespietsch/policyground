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


def test_upsert_twice_leaves_one_copy(tmp_path):
    """D30 / INCIDENTS #7: the DAG's upsert must be safe to re-run."""
    import argparse
    import json

    import numpy as np
    import psycopg
    import pytest

    from policyground.db import connect
    from policyground.ingest import steps

    try:
        connect("ingest_rw").close()
    except psycopg.OperationalError:
        pytest.skip("postgres not running")
    args = argparse.Namespace(tenant="test-idem", date="2026-01-01", chunker="naive-800",
                              embedder="bge-small-en-v1.5", root=tmp_path)
    out = steps.staging_dir(tmp_path, args.tenant, args.date, args.chunker, args.embedder)
    out.mkdir(parents=True)
    (out / "chunks.jsonl").write_text("\n".join(json.dumps(
        {"doc_id": "D", "chunk_index": i, "text": f"t{i}", "chunk_hash": str(i)}) for i in range(3)) + "\n")
    np.save(out / "embeddings.npy", np.zeros((3, 4), dtype=np.float32))
    try:
        steps.upsert(args)
        steps.upsert(args)
        with connect("api_ro") as conn:
            assert conn.execute("SELECT count(*) FROM chunks WHERE tenant='test-idem'").fetchone()[0] == 3
    finally:
        with connect("ingest_rw") as conn:
            conn.execute("DELETE FROM chunks WHERE tenant='test-idem'")
