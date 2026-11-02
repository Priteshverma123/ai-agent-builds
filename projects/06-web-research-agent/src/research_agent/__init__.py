"""06 - Web research agent: multi-step research over a local "web" with cited briefs."""

from .agent import Brief, ResearchAgent, ResearchConfig
from .config import Settings
from .corpus import LocalWeb, Page, PageNotFound, SearchResult
from .llm import MockResearchLLM, make_llm
from .sources import SourceTracker
from .trace import Trace

__all__ = [
    "Brief", "LocalWeb", "MockResearchLLM", "Page", "PageNotFound", "ResearchAgent",
    "ResearchConfig", "SearchResult", "Settings", "SourceTracker", "Trace", "make_llm",
]

__version__ = "1.0.0"
