"""An agent that launches MCP servers, discovers their tools at runtime and uses them."""

__version__ = "1.0.0"

from .agent import MCPAgent, build_system_prompt
from .client import MCPError, StdioMCPClient
from .config import Settings
from .hub import MCPHub
from .llm import MockLLM, make_llm
from .trace import Trace

__all__ = ["MCPAgent", "MCPError", "MCPHub", "MockLLM", "Settings", "StdioMCPClient", "Trace", "build_system_prompt",
           "make_llm"]
