# Video hooks · 03 ReAct Agent Loop

- **hook:** Every AI agent is just this loop: think, act, look.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  | step 2                                                                     |
  |   thought : I need facts about Golden Gate Bridge.                         |
  |   action  : search[Golden Gate Bridge]                                     |
  | step 3                                                                     |
  |   thought : I found 1889 and 1937. The difference needs exact math.        |
  |   action  : calculator[1937 - 1889]                                        |
  |   observe : 48                                                             |
  |   answer  : 48 years                                                       |
  | result    : answered in 4 step(s)                                          |
  ```
- **diagram:** `Question` → `Thought + Action` → `Run tool` → `Observation (loop back)` → `Final Answer`
- **real_world:** A support agent that looks up your order, then the refund policy, then calculates your refund, one step at a time.
- **try_it:** Run `python demo.py --max-steps 2` on the Eiffel Tower question and watch the step limit kick in.
- **flow_steps:**
  1. `cli.py` builds a `ReActAgent` with the `search` and `calculator` tools from `tools.py` and a step limit from `config.py`.
  2. `agent.py` sends the question to the model in `llm.py`, which replies with a `Thought:` and an `Action: tool[input]`.
  3. `parser.py` reads that reply (and throws away any `Observation:` the model tried to invent).
  4. `agent.py` runs the tool and appends its output as an `Observation:`; then the loop goes around again.
  5. When the model writes `Final Answer:` (or the step limit hits), `cli.py` prints every thought, action and observation.
