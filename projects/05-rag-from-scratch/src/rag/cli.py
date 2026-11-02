"""CLI: index the example docs, then answer each demo question showing retrieval scores and citations.

Used by `demo.py`, `python -m rag` and the `rag` console script.

    python demo.py
    python demo.py "How long should I steep a French press?"
    python demo.py --docs path/to/markdown/folder "your question"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .answer import answer
from .config import EXAMPLES_DIR, Settings
from .index import VectorIndex
from .llm import make_llm
from .ui import banner, box



def bar(score: float, width: int = 12) -> str:
    filled = min(width, round(score * width))
    return "#" * filled + "." * (width - filled)


def main(argv: list[str] | None = None) -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="RAG from scratch: chunk, embed, retrieve, answer with citations.")
    parser.add_argument("question", nargs="?", help="ask your own question instead of the demo set")
    parser.add_argument("--docs", type=Path, default=settings.docs_dir, help="folder of .md files (env: RAG_DOCS_DIR)")
    parser.add_argument("-k", type=int, default=settings.top_k, help="chunks to retrieve (env: RAG_TOP_K)")
    args = parser.parse_args(argv)

    llm = make_llm(settings)
    index = VectorIndex.from_folder(args.docs, max_words=settings.chunk_words)
    print(banner(f"05 - RAG from scratch | model: {type(llm).__name__} | retriever: TF-IDF (local)"))
    print(
        f"Indexed {len(index.sources)} documents -> {len(index.chunks)} chunks -> "
        f"{index.embedder.vocabulary_size} distinct terms\n"
    )

    questions = [args.question] if args.question else [
        q.strip() for q in (EXAMPLES_DIR / "questions.txt").read_text(encoding="utf-8").splitlines() if q.strip()
    ]
    for number, question in enumerate(questions, start=1):
        result = answer(question, index, llm, k=args.k, min_score=settings.min_score)
        rows = [("question", question)]
        if not result.hits:
            rows.append(("retrieve", "no chunk above the similarity floor -> skip the LLM entirely"))
        for i, hit in enumerate(result.hits, start=1):
            rows.append(("retrieve" if i == 1 else "", f"[{i}] {hit.score:.2f} {bar(hit.score)} {hit.chunk.id}"))
        rows.append(("answer", result.text))
        for hit in result.cited:
            rows.append(("cites", f'{hit.chunk.id}: "{hit.chunk.text}"'))
        if result.bad_citations:
            rows.append(("WARNING", f"citations {result.bad_citations} point at no source"))
        print(box(f"Q{number}", rows))


if __name__ == "__main__":
    main()
