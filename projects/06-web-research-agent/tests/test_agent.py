from research_agent import MockResearchLLM, ResearchAgent, ResearchConfig, SourceTracker
from research_agent.corpus import Page
from research_agent.sources import CITATION


def run(web, **config):
    return ResearchAgent(web, MockResearchLLM(), ResearchConfig(**config)).run(
        "Are heat pumps worth it in cold climates?"
    )


def test_every_citation_in_the_brief_points_to_a_real_source(web):
    brief = run(web)
    cited = {int(n) for n in CITATION.findall(brief.text)}
    assert cited and cited == set(range(1, len(brief.bibliography) + 1))


def test_opinion_sources_are_flagged_as_contested(web):
    brief = run(web)
    contested = brief.text.split("Contested claims", 1)[1]
    assert "opinion piece" in contested


def test_fetch_budget_is_respected(web):
    brief = run(web, max_fetches=2)
    assert brief.fetched == 2


def test_tracker_strips_lines_citing_unknown_sources():
    tracker = SourceTracker()
    tracker.cite(Page("https://a.example", "A", "body"))
    clean, dropped = tracker.remove_unverified_lines("- real fact [1]\n- invented fact [7]")
    assert clean == "- real fact [1]" and dropped == 1


class LyingLLM(MockResearchLLM):
    """A model that hallucinates a citation in the brief."""

    def complete(self, system, prompt):
        text = super().complete(system, prompt)
        return text + "\n- A made-up statistic [42]" if "TASK: WRITE" in system else text


def test_hallucinated_citations_never_reach_the_brief(web):
    brief = ResearchAgent(web, LyingLLM()).run("Are heat pumps worth it in cold climates?")
    assert "[42]" not in brief.text
