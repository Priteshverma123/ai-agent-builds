"""Deduplicate findings: the same fact from five mirrors is one fact with five sources.

Workers run independently, so they find overlapping material: a press release and the news sites
that syndicated it, two workers reading the same page. Without dedup the report repeats itself
and - worse - looks more certain than it is. We cluster near-duplicate claims with word-shingle
Jaccard similarity and keep the union of their sources as a *corroboration* count.
"""

from __future__ import annotations

from .corpus import terms
from .models import Cluster, Finding


def shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    words = terms(text)
    if len(words) < n:
        return {tuple(words)}
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def deduplicate(findings: list[Finding], threshold: float = 0.5) -> list[Cluster]:
    """Greedy clustering in input order (which is plan order, so each fact lands in its first section).

    Each finding joins the first cluster whose representative claim is similar enough; otherwise it
    starts a new cluster. The shortest variant is kept as the representative wording.
    """
    clusters: list[Cluster] = []
    signatures: list[set] = []
    for f in findings:
        sig = shingles(f.claim)
        match = next((i for i, s in enumerate(signatures) if jaccard(sig, s) >= threshold), None)
        if match is None:
            clusters.append(Cluster(claim=f.claim, subq=f.subq, doc_ids=[f.doc_id]))
            signatures.append(sig)
            continue
        c = clusters[match]
        c.variants += 1
        if f.doc_id not in c.doc_ids:
            c.doc_ids.append(f.doc_id)
        if len(f.claim) < len(c.claim):
            c.claim = f.claim
    return clusters
