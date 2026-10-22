"""Local embedders (D8, D25). Vectors are L2-normalised, so cosine distance = 1 - dot.

Dimensions differ (384 vs 768); the untyped `chunks.embedding` column holds both (D16).
Neither model needs trust_remote_code.
"""

from __future__ import annotations

from functools import cache
from typing import Literal

import numpy as np
from sentence_transformers import SentenceTransformer

EMBEDDERS = {
    # bge v1.5 works without a query instruction; we add none.
    "bge-small-en-v1.5": {"model": "BAAI/bge-small-en-v1.5", "query": "", "doc": ""},
    # e5 is trained with these prefixes and degrades without them.
    "e5-base-v2": {"model": "intfloat/e5-base-v2", "query": "query: ", "doc": "passage: "},
}


@cache
def _model(name: str) -> SentenceTransformer:
    return SentenceTransformer(EMBEDDERS[name]["model"])


def embed(name: str, texts: list[str], kind: Literal["doc", "query"] = "doc") -> list[np.ndarray]:
    prefix = EMBEDDERS[name][kind]
    vectors = _model(name).encode([prefix + t for t in texts], normalize_embeddings=True, batch_size=64)
    return list(vectors)
