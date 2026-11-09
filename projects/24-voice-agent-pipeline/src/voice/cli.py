"""Demo: a three-turn phone call with barge-in and a slow tool, then streaming vs batch latency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio import MockMicrophone, Utterance
from .brain import MockVoiceLLM, StreamingLLM, provider_from_env
from .budget import LatencyBudget, TurnMetrics
from .clock import Clock, RealClock, VirtualClock
from .config import load_settings
from .mouth import MockTTS
from .pipeline import Mode, Timeline, VoiceAgent


def load_script(path: Path | None = None) -> list[Utterance]:
    """The mock caller's utterances (default: ``CONVERSATION_SCRIPT`` or examples/conversation.json)."""
    data = json.loads(Path(path or load_settings().script_path).read_text(encoding="utf-8"))
    return [Utterance(u["start_ms"], u["text"]) for u in data["utterances"]]


def simulate(script: list[Utterance], mode: Mode = "streaming", *, echo: bool = False,
             llm: StreamingLLM | None = None, clock: Clock | None = None,
             filler_after_ms: float | None = 450) -> tuple[list[TurnMetrics], VoiceAgent]:
    """Run one session. Virtual time unless a real model (with real latency) is plugged in."""
    clock = clock or (RealClock() if llm else VirtualClock())
    agent = VoiceAgent(clock, llm or MockVoiceLLM(clock), MockTTS(clock), mode=mode,
                       filler_after_ms=filler_after_ms, timeline=Timeline(clock, echo=echo))
    turns = clock.run(agent.run(MockMicrophone(clock, script)))
    return turns, agent


def latency_table(turns: list[TurnMetrics], budget: LatencyBudget) -> str:
    def ms(v: float | None) -> str:
        return "   -" if v is None else f"{v:4.0f}"

    limits = budget.stage_limits()
    lines = [f"budget: total {budget.total_ms:.0f} ms = endpoint {limits['endpoint']:.0f} + stt {limits['stt']:.0f}"
             f" + llm {limits['llm']:.0f} + tts {limits['tts']:.0f}", "",
             "turn  user said                           heard after  endpoint  stt   llm   tts   verdict",
             "----  ----------------------------------  -----------  --------  ----  ----  ----  -------"]
    for t in turns:
        ok, problems = budget.check(t)
        s = t.stages
        verdict = "PASS" if ok else "FAIL"
        if ok and t.filler:
            verdict += " via filler"
        if problems:
            verdict += f" ({problems[0]})"
        said = t.user_text if len(t.user_text) <= 34 else t.user_text[:31] + "..."
        lines.append(f"{t.index:>4}  {said:<34}  {ms(t.perceived_ms)} ms   {ms(s['endpoint']):>8}  {ms(s['stt'])}  "
                     f"{ms(s['llm'])}  {ms(s['tts'])}  {verdict}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="STT -> LLM -> TTS voice pipeline with mock audio")
    parser.add_argument("--mode", choices=["streaming", "batch"], default=settings.mode)
    parser.add_argument("--no-filler", action="store_true", help="disable the filler phrase")
    args = parser.parse_args(argv)

    script = load_script(settings.script_path)
    budget = LatencyBudget(total_ms=settings.budget_total_ms)
    provider = provider_from_env(settings)
    print(f"VOICE AGENT  mode={args.mode}  model={provider.name if provider else 'mock-voice-llm'}  "
          f"clock={'real' if provider else 'virtual (instant, deterministic)'}\n")
    turns, agent = simulate(script, args.mode, echo=True, llm=provider,
                            filler_after_ms=None if args.no_filler else settings.filler_after_ms)

    print("\n" + latency_table(turns, budget))
    for t in turns:
        if t.barge_in_reaction_ms is not None:
            print(f"\nbarge-in on turn {t.index}: agent went quiet {t.barge_in_reaction_ms:.0f} ms after the user "
                  f"started talking; memory keeps only what was heard:\n  assistant: \"{t.heard} [interrupted]\"")

    if provider is None:
        other: Mode = "batch" if args.mode == "streaming" else "streaming"
        other_turns, _ = simulate(script, other)
        print(f"\nsame call in {other} mode -> first turn heard after {other_turns[0].perceived_ms:.0f} ms "
              f"(vs {turns[0].perceived_ms:.0f} ms in {args.mode} mode)")
    return 0
