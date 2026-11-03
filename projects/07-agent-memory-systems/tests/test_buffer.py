from memory_agent import ShortTermMemory, estimate_tokens


def test_estimate_tokens_is_roughly_words_times_1_3():
    assert estimate_tokens("one two three four five six seven eight nine ten") == 13


def test_buffer_evicts_oldest_messages_when_over_budget():
    buffer = ShortTermMemory(max_tokens=10)
    assert buffer.add("user", "one two three") == []
    evicted = buffer.add("assistant", "four five six seven eight")
    assert [m.text for m in evicted] == ["one two three"]
    assert buffer.tokens <= 10


def test_buffer_keeps_the_newest_message_even_if_it_alone_is_too_big():
    buffer = ShortTermMemory(max_tokens=2)
    buffer.add("user", "this message is much longer than the budget")
    assert len(buffer.messages) == 1
