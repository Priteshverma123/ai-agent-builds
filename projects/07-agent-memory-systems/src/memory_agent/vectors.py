"""A toy embedding model: hashed bag-of-words plus a small concept table.

Real embedding models place "run" near "marathon" because they learned it from data.
We fake that with ``CONCEPTS``: words that share a concept share an extra feature.
Swap ``embed()`` for a real embedding API and nothing else in the project changes.
"""

from __future__ import annotations

import hashlib
import math
import re

DIM = 256
STOPWORDS = frozenset(
    "a an and are as at be can do for from i i'm im in is it me my of on or should "
    "that the this to user user's was what where with you your again".split()
)
CONCEPTS = {
    "food": "eat eating dinner lunch breakfast meal cook recipe snack vegetarian vegan allergic allergy peanut food",
    "exercise": "run running marathon training train workout gym race fitness",
    "location": "live lives living moved move city home address",
    "identity": "name called",
}
WORD_TO_CONCEPT = {word: concept for concept, words in CONCEPTS.items() for word in words.split()}


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in STOPWORDS]


def _bucket(feature: str) -> int:
    return int(hashlib.md5(feature.encode()).hexdigest(), 16) % DIM


def embed(text: str) -> list[float]:
    """Unit-length vector: one feature per word, plus a stronger one per concept."""
    vec = [0.0] * DIM
    for word in tokens(text):
        vec[_bucket(word)] += 1.0
        if word in WORD_TO_CONCEPT:
            vec[_bucket("concept:" + WORD_TO_CONCEPT[word])] += 2.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
