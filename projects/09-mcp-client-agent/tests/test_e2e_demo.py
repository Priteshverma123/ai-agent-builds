"""End-to-end: run demo.py, which launches project 08's server.py and lets the agent work through every task."""

import os
import subprocess
import sys
from pathlib import Path

from mcp_client_agent import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_demo_discovers_tools_and_completes_every_task():
    env = {**os.environ, "LLM_PROVIDER": "mock", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    for key in ("MCP_SERVERS_CONFIG", "AGENT_TASKS_FILE", "AGENT_MAX_STEPS"):
        env.pop(key, None)
    out = subprocess.run([sys.executable, str(ROOT / "demo.py")], cwd=ROOT, env=env, capture_output=True,
                         text=True, encoding="utf-8", timeout=90, check=True).stdout
    assert "notebook: launched `server.py` -> team-notebook 1.0.0, protocol 2025-06-18" in out
    assert "notebook__calculate" in out and "read_resource" in out
    assert "The handbook gives a 30-day refund window, which is 720 hours." in out
    assert "The answer is 409.5." in out  # recovered from a tool error
    assert "I don't have a tool that can help with that." in out  # the flight task
    assert "Servers closed (stdin EOF)" in out


def test_settings_defaults_and_overrides():
    defaults = Settings.from_env({})
    assert defaults.servers_config.name == "servers.json" and defaults.max_steps == 6
    custom = Settings.from_env({"MCP_TIMEOUT": "2.5", "AGENT_MAX_STEPS": "3", "LLM_PROVIDER": "Anthropic"})
    assert (custom.mcp_timeout, custom.max_steps, custom.llm_provider) == (2.5, 3, "anthropic")
