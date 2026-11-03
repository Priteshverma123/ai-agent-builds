from memory_agent import LongTermMemory, MemoryAgent, MockMemoryLLM


def test_agent_uses_long_term_memory_in_a_new_session(tmp_path):
    db = tmp_path / "memory.db"
    day1 = MemoryAgent(MockMemoryLLM(), LongTermMemory(db))
    day1.chat("I'm vegetarian, and I'm allergic to peanuts.")
    day1.store.close()

    day2 = MemoryAgent(MockMemoryLLM(), LongTermMemory(db))
    report = day2.chat("Can you suggest a dinner for tonight?")
    assert "vegetarian" in report.reply and "no peanuts" in report.reply


def test_evicted_turns_are_summarised():
    agent = MemoryAgent(MockMemoryLLM(), LongTermMemory(), buffer_tokens=20)
    agent.chat("Hi! My name is Priya and I live in London.")
    agent.chat("I'm training for a half marathon in March.")
    assert "Priya" in agent.summary


def test_end_session_saves_an_episode():
    agent = MemoryAgent(MockMemoryLLM(), LongTermMemory(), buffer_tokens=20)
    agent.chat("Hi! My name is Priya and I live in London.")
    agent.chat("I'm training for a half marathon in March.")
    agent.end_session()
    assert any(m.kind == "episode" for m in agent.store.all())


def test_repeated_fact_is_reported_as_already_known():
    agent = MemoryAgent(MockMemoryLLM(), LongTermMemory())
    agent.chat("I'm vegetarian.")
    report = agent.chat("Just so you know, I'm vegetarian.")
    assert report.stored == [] and report.already_known == ["User is vegetarian"]
