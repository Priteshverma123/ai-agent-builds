from pathlib import Path

from chat_memory.chat import ChatSession
from chat_memory.llm import MockLLM
from chat_memory.memory import ConversationMemory
from chat_memory.tokens import count_tokens


def test_token_counter_counts_words_and_punctuation():
    assert count_tokens("Hello, world!") == 4
    assert count_tokens("") == 0
    assert count_tokens("internationalization") > count_tokens("cat")


def test_window_keeps_everything_when_budget_is_large():
    memory = ConversationMemory("Be brief.", budget=10_000)
    for i in range(5):
        memory.add("user", f"message {i}")
        memory.add("assistant", f"reply {i}")
    window = memory.window()
    assert len(window.messages) == 10
    assert window.dropped == []
    assert window.tokens_used <= window.budget


def test_window_drops_oldest_first_and_stays_within_budget():
    memory = ConversationMemory("Be brief.", budget=60)
    for i in range(10):
        memory.add("user", f"message number {i}")
        memory.add("assistant", f"reply number {i}")
    window = memory.window()
    assert window.tokens_used <= 60
    assert window.messages[-1].content == "reply number 9"  # newest kept
    assert window.dropped[0].content == "message number 0"  # oldest gone
    assert window.messages[0].role == "user"  # APIs want a user turn first
    assert window.dropped + window.messages == memory.history  # contiguous, nothing lost


def test_newest_message_is_kept_even_if_over_budget():
    memory = ConversationMemory("Be brief.", budget=5)
    memory.add("user", "a very long message " * 20)
    assert len(memory.window().messages) == 1


def test_mock_remembers_only_what_is_in_the_window():
    roomy = ChatSession(MockLLM(), ConversationMemory("Be brief.", budget=1_000))
    roomy.send("My name is Priya.")
    assert roomy.send("What's my name?").reply == "Your name is Priya."

    cramped = ChatSession(MockLLM(), ConversationMemory("Be brief.", budget=40))
    cramped.send("My name is Priya.")
    cramped.send("Tell me a fun fact about octopuses.")
    assert "don't know" in cramped.send("What's my name?").reply


def test_save_and_load_round_trip(tmp_path: Path):
    memory = ConversationMemory("Be brief.", budget=123)
    memory.add("user", "hi")
    memory.add("assistant", "hello")
    path = tmp_path / "session.json"
    memory.save(path)
    restored = ConversationMemory.load(path)
    assert restored == memory
