# Video hooks · 11 Router Agent

- **hook:** When this AI isn't sure, it asks instead of guessing.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [user  ] I was charged twice on invoice INV-1042
  [route ] billing       conf 0.95  via rule
  [user  ] Do you offer discounts for teams of 50 people?
  [route ] sales         conf 0.94  via llm
           closest example: "Do you offer a discount for nonprofits?"
  [user  ] I can't log in and I also want a refund
  [route ] fallback      conf 0.31  via fallback
  [reply ] (fallback) I can help with that. Is this mainly about billing or tech support?
  | ROUTER EVAL  accuracy 16/17 = 94%   (fallback 4, llm 5, rule 8)                        |
  ```
- **diagram:** Message → Regex rules → LLM classifier (confidence) → Threshold → Specialist or Fallback
- **real_world:** A SaaS support inbox where billing, bug and sales messages each reach the right specialist agent, and mixed messages get a clarifying question.
- **try_it:** Fix the one `XX` in the eval ("Why did my price go up?") without breaking any other row.
- **flow_steps:**
  1. `cli.py` loads the intents from `examples/intents.json` into the `Router` and hands each customer message to `RouterAgent.handle` in `agent.py`.
  2. `router.py` tries the cheap regex rules first: if exactly one team's rule fires (like `INV-1042` → billing), the message is routed with no model call.
  3. Otherwise `router.py` asks the classifier in `llm.py` for an intent, a confidence and a reason, using the few-shot examples.
  4. If the confidence is below the 0.6 threshold, or the answer is broken or made up, the message goes to the fallback, which asks a clarifying question instead of guessing.
  5. A confident decision is dispatched to one specialist in `specialists.py` (billing, tech support or sales), which writes the reply.
  6. Finally `agent.py` (`evaluate`) routes the labelled set in `examples/labelled.jsonl` and prints the router's accuracy.
