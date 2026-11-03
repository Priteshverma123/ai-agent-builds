# Video hooks · 07 Agent Memory Systems

- **hook:** Restart the program and the agent still remembers your peanut allergy.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [store ] ~ updated #2 slot=city: "User lives in London" -> "User lives in Berlin"
  [evict ] 2 old message(s) left the 60-token buffer -> summarised
  | DAY 2 - process restarted, same SQLite file                                            |
  [user  ] (turn 7) What should I eat before my long run on Sunday?
  [recall] top 4 memories (score = .6 sim + .25 importance + .15 recency)
            0.71  sim 0.52  imp 1.0  rec 0.97  User is allergic to peanuts
            0.64  sim 0.50  imp 0.8  rec 0.97  User is vegetarian
  [agent ] How about a chickpea and spinach curry with rice (vegetarian, no peanuts)? It's
           carb-rich, good fuel while you're training for a half marathon.
  ```
- **diagram:** User message → Extract facts → SQLite memory → Recall (similarity + importance + recency) → Prompt → Reply
- **real_world:** A meal-planning assistant that remembers your diet, allergies and goals across weeks, and updates them when you move or change your diet.
- **try_it:** Tell the agent "I'm vegan" on day 2 and watch the `diet` slot update instead of duplicating.
- **flow_steps:**
  1. `cli.py` loads `examples/sessions.json` and opens `LongTermMemory` on one SQLite file for day 1.
  2. `agent.py` (`MemoryAgent.chat`) asks the LLM to EXTRACT facts, and `store.py` writes them: new rows are added, a fact with the same slot (like `city`) replaces the old one.
  3. `store.py` recalls the top memories for the message, scored by similarity (`vectors.py`) + importance + recency.
  4. `agent.py` builds the prompt from summary, memories, recent buffer and the message, and the LLM replies.
  5. `buffer.py` evicts turns over the 60-token budget; `agent.py` summarises them, and `end_session()` saves the summary as an episode.
  6. Day 2 reopens the same SQLite file in a fresh `MemoryAgent`, and recall brings back the allergy, diet and new city.
