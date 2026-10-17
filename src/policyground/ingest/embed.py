"""Local embedders (D8). Vectors are L2-normalised, so cosine distance = 1 - dot."""

from __future__ import annotations

from functools import cache

import numpy as np
from sentence_transformers import SentenceTransformer

EMBEDDERS = {
    # bge v1.5 works without a query instruction; we add none for now.
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
}


@cache
def _model(name: str) -> SentenceTransformer:
    return SentenceTransformer(EMBEDDERS[name])


def embed(name: str, texts: list[str]) -> list[np.ndarray]:
    vectors = _model(name).encode(texts, normalize_embeddings=True, batch_size=64)
    return list(vectors)
