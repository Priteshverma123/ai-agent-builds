"""A browser automation agent that reads pages as an accessibility tree with element refs."""

from .agent import BrowserAgent
from .browser import ActionResult, Browser
from .llm import MockLLM, make_llm, parse_snapshot
from .site import FileSite, ShopSite
from .trace import Trace

__version__ = "0.2.0"

__all__ = ["ActionResult", "Browser", "BrowserAgent", "FileSite", "MockLLM", "ShopSite", "Trace", "make_llm",
           "parse_snapshot"]
