"""Voice pipeline behaviour on the virtual clock: latency budget, barge-in, filler, determinism."""

import asyncio

import pytest

from voice.audio import FRAME_MS, AudioFrame, Utterance
from voice.budget import LatencyBudget
from voice.cli import load_script, simulate
from voice.clock import Deadlock, VirtualClock
from voice.ears import EnergyVAD
from voice.mouth import AudioChunk, PhraseChunker, Speaker

BUDGET = LatencyBudget()


@pytest.fixture(scope="module")
def streaming():
    return simulate(load_script(), "streaming")


# --- building blocks -------------------------------------------------------------------------

def test_virtual_clock_jumps_and_runs_sleepers_concurrently():
    clock = VirtualClock()

    async def main():
        await asyncio.gather(clock.sleep(5000), clock.sleep(3000))
        return clock.now_ms

    assert clock.run(main()) == 5000  # concurrent, not 8000 - and instantly


def test_virtual_clock_detects_deadlock():
    clock = VirtualClock()

    async def main():
        await asyncio.Queue().get()  # nobody will ever put

    with pytest.raises(Deadlock):
        clock.run(main())


def test_vad_needs_consecutive_loud_frames_and_enough_silence():
    vad = EnergyVAD(start_frames=2, end_silence_ms=300)
    loud = [AudioFrame(t, 0.7) for t in range(0, 100, FRAME_MS)]
    quiet = [AudioFrame(t, 0.02) for t in range(100, 600, FRAME_MS)]
    events = [(f.t_ms, vad.feed(f)) for f in loud + quiet]
    changes = [(t, e) for t, e in events if e]
    assert changes[0] == (20, "start")          # second loud frame
    assert changes[1][1] == "end" and changes[1][0] + FRAME_MS - 100 >= 300
    assert len(changes) == 2


def test_phrase_chunker_breaks_on_punctuation_and_length():
    chunker = PhraseChunker(max_words=3)
    out = [chunker.push(t) for t in ["Sure! ", "one ", "two ", "three ", "four "]]
    assert out == ["Sure!", None, None, "one two three", None]
    assert chunker.flush() == "four"


def test_speaker_remembers_only_what_was_audible():
    clock = VirtualClock()
    speaker = Speaker(clock)

    async def main():
        task = asyncio.ensure_future(speaker.play(AudioChunk("one two three four", 1000)))
        await clock.sleep(500)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    clock.run(main())
    assert speaker.take_heard() == "one two"


# --- latency budget --------------------------------------------------------------------------

def test_streaming_meets_the_budget_on_every_turn(streaming):
    turns, _ = streaming
    assert [BUDGET.check(t)[0] for t in turns] == [True, True, True]
    assert turns[0].perceived_ms == 800
    assert turns[0].stages == {"endpoint": 300, "stt": 120, "llm": 250, "tts": 130}


def test_batch_mode_blows_the_budget():
    turns, _ = simulate(load_script(), "batch")
    ok, problems = BUDGET.check(turns[0])
    assert not ok and problems[0].startswith("total")
    assert turns[0].perceived_ms > 2 * 800


def test_filler_bridges_a_slow_tool_call(streaming):
    turns, _ = streaming
    weather = turns[2]
    assert weather.filler and weather.stages["llm"] == 950
    assert weather.first_audio_ms < weather.first_token_ms < weather.answer_audio_ms
    assert BUDGET.check(weather)[0]
    no_filler, _ = simulate(load_script(), "streaming", filler_after_ms=None)
    assert not no_filler[2].filler and not BUDGET.check(no_filler[2])[0]


# --- barge-in --------------------------------------------------------------------------------

def test_barge_in_stops_speaking_within_one_vad_window(streaming):
    turns, _ = streaming
    first = turns[0]
    assert first.interrupted_at_ms == 6000  # the second utterance starts at 6.0 s
    assert first.barge_in_reaction_ms <= 2 * FRAME_MS
    assert first.done_ms is None  # never finished


def test_nothing_from_the_cancelled_answer_plays_after_barge_in(streaming):
    turns, agent = streaming
    stopped = turns[0].stopped_at_ms
    next_answer = turns[1].first_audio_ms
    played_between = [e for e in agent.timeline.events if e[1] == "speaker" and stopped <= e[0] < next_answer]
    assert played_between == []


def test_memory_keeps_only_the_heard_part_of_an_interrupted_answer(streaming):
    _, agent = streaming
    first_reply = agent.history[1]
    assert first_reply[0] == "assistant" and first_reply[1].endswith("[interrupted]")
    assert "holidays" not in first_reply[1]  # generated, maybe synthesised, but never heard
    assert first_reply[1].startswith("Sure! We're open")


def test_no_barge_in_when_the_user_waits_for_the_agent(streaming):
    turns, _ = streaming
    assert turns[1].interrupted_at_ms is None and turns[1].done_ms is not None


def test_simulation_is_deterministic():
    script = [Utterance(0, "what are your opening hours"), Utterance(2500, "and on sunday")]
    a = simulate(script)[1].timeline.events
    b = simulate(script)[1].timeline.events
    assert a == b and a
