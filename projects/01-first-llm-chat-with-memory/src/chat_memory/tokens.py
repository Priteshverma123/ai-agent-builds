"""A tiny, dependency-free token counter.

Real models split text with a learned tokenizer (BPE). Exact counts differ per model,
but the rule of thumb holds: short words are ~1 token, punctuation is ~1 token, and
long words cost more. This approximation is close enough to *see* a context budget
fill up, which is the whole point of this project.
"""

import re

# A "piece" is either a run of letters/digits or a single punctuation mark.
_PIECE = re.compile(r"\w+|[^\w\s]")

# Chat APIs wrap every message in role markers, which cost a few tokens each.
MESSAGE_OVERHEAD = 4


def count_tokens(text: str) -> int:
    """Approximate token count: 1 per piece, plus 1 for every 6 characters of a long word."""
    return sum(1 + len(piece) // 6 for piece in _PIECE.findall(text))
