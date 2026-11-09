# Video hooks · 09 MCP Client Agent

- **hook:** This agent has zero tools until it launches a server.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  | notebook: launched `server.py` -> team-notebook 1.0.0, protocol 2025-06-18               |
  [tool  ] notebook__calculate      (expression        ) read-only
  [tool  ] read_resource            (uri               ) built-in -> resources/read
  [user  ] How many hours long is the refund window in our handbook policy?
  [call  ] read_resource({'uri': 'docs://handbook'})  -> resources/read
  [think ] (step 2) The handbook says 30 days. Convert to hours.
  [call  ] notebook__calculate({'expression': '30 * 24'})  -> notebook: tools/call calculate
  [answer] The handbook gives a 30-day refund window, which is 720 hours.
  [error ] Error: not a valid expression: '17.5% of 2,340'
  [answer] The answer is 409.5.
  ```
- **diagram:** servers.json → MCPHub (spawn + handshake) → tools/list → Agent loop with LLM → tools/call
- **real_world:** An internal ops copilot that gains Jira, database and runbook skills just by adding three lines per server to a config file.
- **try_it:** Add a second copy of the project-08 server to `servers.json` and watch the agent see `work__` and `home__` tools.
- **flow_steps:**
  1. `cli.py` reads `examples/servers.json` and `hub.py` (`MCPHub.from_config`) creates one client per server.
  2. `client.py` (`StdioMCPClient`) launches project 08's `server.py`, does the `initialize` handshake, then `hub.py` lists its tools and resources and renames them `notebook__calculate`, ... plus a built-in `read_resource`.
  3. `agent.py` (`MCPAgent.run`) gives the task, the system prompt and that discovered tool list to the model in `llm.py`.
  4. When the model asks for a tool, `hub.py` routes the call to the right server over stdio (`tools/call` or `resources/read`) and turns the reply, or any error, into text.
  5. The result goes back to the model, which calls another tool (handbook → calculator), retries after an error, or gives the final answer.
  6. When the tasks are done, `MCPHub.close()` closes each server's stdin so it exits cleanly.
