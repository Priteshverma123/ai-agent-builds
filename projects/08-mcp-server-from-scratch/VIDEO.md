# Video hooks · 08 MCP Server from Scratch

- **hook:** Claude can use your app after just 550 lines of Python.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [-->   ] {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-...
  [ok    ] talking to team-notebook 1.0.0, protocol 2025-06-18, capabilities: tools, resources
  [tool  ] calculate     (expression        ) read-only   Evaluate an arithmetic expressio...
  [tool  ] delete_note   (note_id           ) DESTRUCTIVE Permanently delete a note by id....
  [user  ] What is 2340 * 0.175 + 12?
  [think ] best tool: calculate  args: {'expression': '2340 * 0.175 + 12'}
  [result] {"expression": "2340 * 0.175 + 12", "result": 421.5}
  [model ] isError=True: Error: Invalid arguments for calculate: missing required argument
  [error ] -32601 Method not found: prompts/list
  ```
- **diagram:** MCP host → stdin (JSON-RPC line) → Method router → Tool / Resource registry → stdout reply
- **real_world:** A support team wraps its order database and refund handbook as an MCP server so Claude Desktop can answer "can this customer get a refund?" with real data.
- **try_it:** Add a `word_count(text: str)` tool with one decorator and watch it appear in `tools/list` with no other changes.
- **flow_steps:**
  1. The host (`cli.py` demo via `host.py`'s `StdioConnection`, or Claude Desktop) launches `server.py` and writes one JSON-RPC line to its stdin.
  2. `server.py` (`MCPServer.serve_stdio`) reads the line and `jsonrpc.py` (`parse_line`) checks it is a valid JSON-RPC 2.0 object.
  3. `MCPServer.handle` routes by method: `initialize` negotiates the protocol version, `tools/list` returns schemas built by `registry.py` from type hints.
  4. For `tools/call`, `registry.py` validates the arguments against the schema and runs the function in `notebook.py` (e.g. `calculate`).
  5. The result (or an `isError` result the model can fix) is wrapped by `jsonrpc.success` and written back as one line on stdout; logs go to stderr.
  6. When the host closes stdin, the loop ends and the server exits cleanly.
