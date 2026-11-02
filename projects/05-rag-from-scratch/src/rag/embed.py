"""Step 2 of RAG: turn text into vectors so 'similar meaning' becomes 'nearby numbers'.

Production systems use neural embedding models. Here we use TF-IDF, the classic, fully
local approach: a word scores high in a chunk if it is frequent there (TF) but rare across
the corpus (IDF). "refund" tells you a lot about a chunk; "the" tells you nothing.
Vectors are sparse dicts {term: weight}, L2-normalised so cosine similarity is a dot product.
"""

from __future__ import annotations

import math
import re
from collections import Counter

Vector = dict[str, float]

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i if in is it me my of on or our so that the "
    "their them then this to we what when where which who why will with you your".split()
)


def stem(word: str) -> str:
    """A deliberately tiny stemmer: bags -> bag, returned -> return, shipping -> ship."""
    for suffix in ("ing", "ed", "s"):
        if word.endswith(suffix) and not word.endswith("ss") and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "ls":
                word = word[:-1]  # shipp -> ship, stopp -> stop
            break
    return word


def tokenize(text: str) -> list[str]:
    """Lowercase, split into words, drop stopwords, stem."""
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


def _normalise(vector: Vector) -> Vector:
    norm = math.sqrt(sum(v * v for v in vector.values()))
    return {t: v / norm for t, v in vector.items()} if norm else {}


class TfidfEmbedder:
    def __init__(self) -> None:
        self.idf: dict[str, float] = {}

    def fit(self, texts: list[str]) -> TfidfEmbedder:
        """Learn how rare each term is across the corpus."""
        doc_freq = Counter(term for text in texts for term in set(tokenize(text)))
        n = len(texts)
        self.idf = {term: math.log((1 + n) / (1 + df)) + 1 for term, df in doc_freq.items()}
        return self

    def embed(self, text: str) -> Vector:
        counts = Counter(tokenize(text))
        # Terms never seen in the corpus can't match any chunk, so they are dropped.
        return _normalise({t: c * self.idf[t] for t, c in counts.items() if t in self.idf})

    @property
    def vocabulary_size(self) -> int:
        return len(self.idf)


def cosine(a: Vector, b: Vector) -> float:
    """Dot product of two normalised sparse vectors (iterate over the smaller one)."""
    if len(a) > len(b):
        a, b = b, a
    return sum(weight * b.get(term, 0.0) for term, weight in a.items())
