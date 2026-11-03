from memory_agent import Fact, LongTermMemory


def test_slot_update_replaces_contradicting_fact():
    store = LongTermMemory()
    store.write(Fact("User lives in London", "profile", "city", 0.7))
    result = store.write(Fact("User lives in Berlin", "profile", "city", 0.7))
    assert result.action == "updated" and result.previous == "User lives in London"
    assert [m.text for m in store.all()] == ["User lives in Berlin"]


def test_near_duplicate_is_not_stored_twice():
    store = LongTermMemory()
    store.write(Fact("User likes green tea"))
    assert store.write(Fact("User likes green tea!")).action == "duplicate"
    assert len(store.all()) == 1


def test_recall_ranks_relevant_memories_and_ignores_unrelated_ones():
    store = LongTermMemory()
    store.write(Fact("User is allergic to peanuts", "preference", "allergy:peanuts", 1.0))
    store.write(Fact("User's name is Priya", "profile", "name", 0.9))
    hits = store.recall("What should I cook for dinner?")
    assert [h.memory.text for h in hits] == ["User is allergic to peanuts"]


def test_importance_breaks_ties_between_equally_similar_memories():
    store = LongTermMemory()
    store.write(Fact("User enjoys a snack", importance=0.1))
    store.write(Fact("User is allergic to peanuts", importance=1.0))
    hits = store.recall("snack ideas please", k=2)
    assert hits[0].memory.text == "User is allergic to peanuts"


def test_memory_survives_a_restart(tmp_path):
    db = tmp_path / "memory.db"
    first = LongTermMemory(db)
    first.write(Fact("User's name is Priya", "profile", "name", 0.9))
    first.tick()
    first.close()
    second = LongTermMemory(db)
    assert second.turn == 1
    assert second.all()[0].text == "User's name is Priya"
