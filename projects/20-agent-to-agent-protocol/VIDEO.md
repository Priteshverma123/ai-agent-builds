# Video hooks · 20 Agent-to-Agent Protocol

- **hook:** One agent hires two others, and one of them asks it a question back.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [<--   ] FX Desk: card: FX Desk v1.0.0, skills: convert_currency
  [plan  ] convert_currency  -> FX Desk          "Convert 500 dollars to JPY."
  [plan  ] packing_forecast  -> Packing Weather  "What should I pack for Tokyo in April?"
  [<--   ] FX Desk: tasks/get x1 -> task f3e45611d117: input-required: Which dollars do you
           mean: USD, CAD, AUD?
  [think ] FX Desk needs input. From the request, the answer is: CAD
  [-->   ] FX Desk: message/send (non-blocking, task f3e45611d117): CAD
  [<--   ] FX Desk: tasks/get x1 -> task f3e45611d117: completed: 500 CAD = 54,562 JPY
  [answer] Here's your trip brief: 500 CAD = 54,562 JPY; Tokyo in April: 19C / 10C, ...
  ```
- **diagram:** User → Planner (reads agent cards) → message/send to FX Desk + Weather agents → input-required / polling → Summary
- **real_world:** A travel company's booking assistant asks a partner bank's FX agent for a quote and a weather provider's agent for a packing list, without sharing any code.
- **try_it:** Ask for a trip from Chicago and watch the FX agent's question get answered with USD.

- **flow_steps:**
  1. `cli.py` starts two separate HTTP agents with `serve.py` (FX Desk and Packing Weather), each built by `server.py`'s `create_agent_app()`.
  2. `planner.py` reads each agent's card through `client.py`, so it learns their skills instead of hard-coding them.
  3. The planner's model (`llm.py`) splits the trip request into one sub-task per skill, and both are sent at once as non-blocking tasks.
  4. `agents.py`'s FX Desk stops in `input-required` ("which dollars?"); the planner answers "CAD" on the same task id and the FX agent finishes.
  5. The planner polls the slow weather task until it completes, then summarises both artifacts into one trip brief.
