from pathlib import Path

from rag.answer import NO_CONTEXT_ANSWER, answer, build_prompt
from rag.chunking import chunk_document, split_sentences
from rag.embed import TfidfEmbedder, cosine, tokenize
from rag.index import VectorIndex
from rag.llm import MockLLM

DOCS = Path(__file__).resolve().parents[1] / "examples" / "docs"


class Fixed:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def complete(self, system, messages):
        return self.reply


def test_chunks_respect_size_and_overlap():
    text = " ".join(f"Sentence number {i} has exactly seven words." for i in range(10))
    chunks = chunk_document("doc.md", text, max_words=20, overlap=1)
    assert all(len(c.text.split()) <= 20 for c in chunks)
    assert chunks[0].id == "doc.md#0"
    last_of_first = split_sentences(chunks[0].text)[-1]
    assert chunks[1].text.startswith(last_of_first)  # overlap carries the boundary sentence


def test_tokenizer_drops_stopwords_and_stems():
    assert tokenize("The bags were shipped and returned") == ["bag", "were", "ship", "return"]


def test_tfidf_ranks_rare_shared_words_higher():
    embedder = TfidfEmbedder().fit(["coffee refund policy", "coffee brewing guide", "coffee shipping times"])
    query = embedder.embed("refund for coffee")
    scores = [cosine(query, embedder.embed(t)) for t in ["coffee refund policy", "coffee brewing guide"]]
    assert scores[0] > scores[1] > 0  # "refund" is rare, "coffee" is everywhere


def test_retrieval_finds_the_right_document():
    index = VectorIndex.from_folder(DOCS)
    assert index.search("How do I pause my subscription?")[0].chunk.source == "subscriptions.md"
    assert index.search("ship to Canada")[0].chunk.source == "shipping.md"
    assert index.search("CEO favourite film") == []


def test_answer_cites_real_sources():
    index = VectorIndex.from_folder(DOCS)
    result = answer("Can I return an opened bag of coffee?", index, MockLLM())
    assert "Opened bags can't be returned" in result.text
    assert result.cited and all(h.chunk.source == "refund-policy.md" for h in result.cited)
    assert result.bad_citations == []


def test_no_context_means_no_model_call():
    class Exploding:
        def complete(self, system, messages):
            raise AssertionError("the model must not be called without context")

    result = answer("What is your CEO's favourite film?", VectorIndex.from_folder(DOCS), Exploding())
    assert result.text == NO_CONTEXT_ANSWER


def test_invented_citations_are_flagged():
    index = VectorIndex.from_folder(DOCS)
    result = answer("How do I pause my subscription?", index, Fixed("Use the Account page [1]. Also see [9]."))
    assert result.bad_citations == [9]
    assert len(result.cited) == 1


def test_prompt_numbers_sources():
    hits = VectorIndex.from_folder(DOCS).search("pause subscription", k=2)
    prompt = build_prompt("q?", hits)
    assert prompt.startswith("Sources:\n[1] (subscriptions.md#0)")
    assert prompt.endswith("Question: q?")
