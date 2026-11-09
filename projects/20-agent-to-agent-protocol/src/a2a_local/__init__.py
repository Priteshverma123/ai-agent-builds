"""A2A-style agent-to-agent delegation over local HTTP: agent cards, JSON-RPC tasks, polling."""

from .agents import build_currency_agent, build_weather_agent
from .client import A2AClient, A2AError
from .llm import MockLLM, make_llm
from .models import AgentCard, Task, TaskState
from .planner import Planner
from .server import Reply, create_agent_app
from .trace import Trace

__version__ = "0.2.0"

__all__ = ["A2AClient", "A2AError", "AgentCard", "MockLLM", "Planner", "Reply", "Task", "TaskState", "Trace",
           "build_currency_agent", "build_weather_agent", "create_agent_app", "make_llm"]
