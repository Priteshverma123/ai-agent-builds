"""The 'brain'. MockLLM is a deterministic SRE policy; RealLLM asks a provider and falls back to it.

Either way the LLM only *proposes* actions. The ToolRegistry decides what actually runs.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any, Protocol

from sre_agent.config import Settings
from sre_agent.domain.models import Action
from sre_agent.domain.state import AgentState


class LLM(Protocol):
    def next_action(self, state: AgentState, tools: list[dict[str, Any]]) -> Action: ...

    def summarize(self, state: AgentState) -> str: ...


def _iso(ts) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


class MockLLM:
    """Investigate -> hypothesise -> follow the runbook -> verify -> finish (or escalate)."""

    def next_action(self, state: AgentState, tools: list[dict[str, Any]]) -> Action:
        a = state.alert
        if state.anomalies is None:
            return Action(f"{a.id} says '{a.rule}'. First: which signals actually moved, and when?",
                          "detect_anomalies")
        if not state.anomalies:
            return Action("Nothing deviates from baseline; likely a flapping alert.", "finish", {"status": "no_anomaly"})
        first = state.first_anomaly
        if state.signatures is None:
            return Action(f"{first.series} broke first at {first.start:%H:%M}. Read WARN/ERROR logs from 10 min "
                          f"before that.", "search_logs", {"since": _iso(first.start - timedelta(minutes=10))})
        if state.deploys is None:
            top = state.signatures[0].template[:50] if state.signatures else "no errors"
            return Action(f"Dominant error: '{top}...'. What changed in the hour before?",
                          "list_deploys", {"since": _iso(first.start - timedelta(minutes=60))})
        if state.hypotheses is None:
            return Action("I have symptoms, errors and changes. Score each candidate cause against them.",
                          "rank_hypotheses")
        if state.plan:
            return state.plan[0]
        if state.verified:
            return Action("Service is back within SLO. Mitigated; hand over to postmortem.", "finish",
                          {"status": "mitigated"})
        if not state.paged:
            team = f"{a.service}-owners"
            return Action("Runbook exhausted and the service is still unhealthy. Escalate to a human.",
                          "page_oncall", {"team": team, "summary": f"{a.service} unresolved after runbook"})
        return Action("Escalated; stopping automation.", "finish", {"status": "escalated"})

    def summarize(self, state: AgentState) -> str:
        h, first = state.top_hypothesis, state.first_anomaly
        if not h or not first:
            return f"{state.alert.id} fired but no sustained anomaly was found."
        outcome = "was mitigated by" if state.verified else "was not mitigated despite"
        steps = [r.tool for r in state.records if r.status == "executed" and r.risk.value != "none"]
        return (f"Starting {first.start:%H:%M} UTC, {first.service} breached its latency and error SLOs. "
                f"The most likely trigger is the {h.params.get('service', '')} {h.params.get('version', '')} "
                f"deploy ({h.params.get('change', h.title)}). The incident {outcome} "
                f"{', '.join(steps) or 'the runbook'}.")


class RealLLM:
    """Ask a real model for the next action as JSON. Any failure -> the MockLLM policy decides."""

    def __init__(self, provider: str, settings: Settings | None = None) -> None:
        import httpx
        self.provider, self._http, self._fallback = provider, httpx.Client(timeout=30), MockLLM()
        self.settings = settings or Settings.from_env()

    def next_action(self, state: AgentState, tools: list[dict[str, Any]]) -> Action:
        suggestion = self._fallback.next_action(state, tools)
        prompt = (
            "You are an SRE incident agent. Choose the next tool. Reply ONLY with JSON "
            '{"thought": str, "tool": str, "args": object}. Use tool "finish" with {"status": ...} to stop.\n'
            f"Tools: {json.dumps(tools)}\nRunbook suggests: {json.dumps(suggestion.__dict__)}\n"
            f"State: anomalies={state.anomalies!r}\nerrors={state.signatures!r}\nverified={state.verified}")
        try:
            data = json.loads(re.search(r"\{.*\}", self._complete(prompt), re.S).group(0))
            return Action(str(data["thought"]), str(data["tool"]), dict(data.get("args", {})))
        except Exception:  # noqa: BLE001 - any provider/parse problem means: use the safe policy
            return suggestion

    def summarize(self, state: AgentState) -> str:
        try:
            return self._complete("Write a 3-sentence blameless incident summary. Facts: "
                                  + self._fallback.summarize(state)).strip()
        except Exception:  # noqa: BLE001
            return self._fallback.summarize(state)

    def _complete(self, prompt: str) -> str:
        if self.provider == "anthropic":
            r = self._http.post("https://api.anthropic.com/v1/messages", headers={
                "x-api-key": self.settings.anthropic_api_key, "anthropic-version": "2023-06-01"}, json={
                "model": self.settings.model, "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            return r.json()["content"][0]["text"]
        r = self._http.post("https://api.openai.com/v1/chat/completions", headers={
            "Authorization": f"Bearer {self.settings.openai_api_key}"}, json={
            "model": self.settings.model, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def default_llm(settings: Settings | None = None) -> LLM:
    settings = settings or Settings.from_env()
    provider = settings.llm_provider
    return RealLLM(provider, settings) if provider in ("anthropic", "openai") else MockLLM()
