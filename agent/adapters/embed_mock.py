"""Embedding mock: hashing de tokens a 1024 dims (misma forma que bge-m3). Solo para correr local; no mide calidad de retrieval."""
from __future__ import annotations
import hashlib
import math
import re

DIMS = 1024


class EmbedMock:
    model_version = "mock-hash-1024"

    def __init__(self, settings=None):
        pass

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        v = [0.0] * DIMS
        for tok in re.findall(r"\w+", text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % DIMS] += 1.0
            v[(h // DIMS) % DIMS] += 0.5
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]
