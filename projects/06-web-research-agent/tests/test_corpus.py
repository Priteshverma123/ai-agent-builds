import pytest

from research_agent import PageNotFound
from research_agent.corpus import tokenize


def test_tokenize_drops_stopwords_and_plurals():
    assert tokenize("Are heat pumps worth it?") == ["heat", "pump"]


def test_search_ranks_the_field_study_first_for_evidence_queries(web):
    results = web.search("heat pump cold climate evidence study", k=2)
    assert results[0].url.endswith("field-study-2025")
    assert results[0].score >= results[1].score


def test_search_returns_nothing_for_unrelated_query(web):
    assert web.search("chocolate cake recipe") == []


def test_fetch_unknown_url_raises(web):
    with pytest.raises(PageNotFound):
        web.fetch("https://nowhere.example.com")
