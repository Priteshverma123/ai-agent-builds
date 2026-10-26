# Video hooks · 02 Tool Calling from Scratch

- **hook:** The AI never runs your code. It just asks politely.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  +-- Q1 | 2 model call(s) ----------------------------------------------------+
  | user     : What's the weather in Paris and Tokyo?                          |
  | model -> : get_weather({"city": "Paris"})                                  |
  | tool  <- : {"city": "Paris", "temp_c": 18, "conditions": "cloudy"}         |
  | model -> : get_weather({"city": "Tokyo"})                                  |
  | tool  <- : {"city": "Tokyo", "temp_c": 24, "conditions": "sunny"}          |
  | answer   : Paris: 18 C and cloudy. Tokyo: 24 C and sunny.                  |
  +----------------------------------------------------------------------------+
  ```
- **diagram:** `Question` → `LLM sees JSON schemas` → `Tool call` → `Validate + run` → `Result fed back → Answer`
- **real_world:** A travel assistant that quotes exact currency conversions from a rates API instead of guessing from memory.
- **try_it:** Add a `get_time(city: str)` tool with one decorator and ask "What time is it in Tokyo?"
- **flow_steps:**
  1. `cli.py` prints the JSON schemas that `tools.py` built from each function's type hints and docstring: that is all the model ever sees.
  2. `agent.py` `run()` sends your question plus those schemas to the model in `llm.py`.
  3. The model replies with tool calls (name + JSON arguments) instead of text; it never runs anything itself.
  4. `ToolRegistry.call()` in `tools.py` validates the arguments, runs the matching function from `demo_tools.py`, and turns any failure into an error result.
  5. `run()` feeds all results back in one message; the model reads them and writes the final answer, which `cli.py` draws in a box.
