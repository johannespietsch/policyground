"""Retrieval configuration in one place.

PRODUCTION is what the API's kg graph, `make ingest` and the nightly DAG use (D31).
BASELINE is pinned to the M1 configuration so `make eval GRAPH=rag` stays comparable
with every earlier METRICS row.
"""

from __future__ import annotations

PRODUCTION = {"chunker": "structural-v1", "embedder": "e5-base-v2"}
BASELINE = {"chunker": "naive-800", "embedder": "bge-small-en-v1.5"}
