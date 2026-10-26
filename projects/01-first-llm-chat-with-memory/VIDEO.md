# Video hooks · 01 First LLM Chat with Memory

- **hook:** Your chatbot doesn't forget. Your name just stopped fitting.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  +-- turn 4 --------------------------------------------------------------+
  | you : What's my name?                                                  |
  | bot : Your name is Priya.                                              |
  | ctx : [################....] 115/140 tokens | 7 msgs sent | 0 dropped  |
  +-- turn 7 --------------------------------------------------------------+
  | you  : What's my name?                                                 |
  | bot  : I don't know. If you told me, it has scrolled out of my context |
  | ctx  : [####################] 138/140 tokens | 9 msgs sent | 4 dropped |
  | lost : fell out of the window: "I live in Pune."                       |
  ```
- **diagram:** `You type` → `Full history` → `Token-budget window` → `LLM` → `Reply (saved to history)`
- **real_world:** A support bot that loses your order number halfway through a long chat. It fell out of the context window.
- **try_it:** Run `python demo.py --budget 1000` and find the smallest budget where the bot still remembers your name at turn 7.
- **flow_steps:**
  1. `cli.py` reads your message (or the next line of `examples/demo_conversation.txt`) and hands it to `ChatSession.send()` in `chat.py`.
  2. `memory.py` appends it to the full transcript with `ConversationMemory.add()`; nothing is ever deleted.
  3. `ConversationMemory.window()` pays for the system prompt, then walks back from the newest message, using `tokens.py` to keep only what fits the budget.
  4. `llm.py` sends just that window to the model (`MockLLM` offline, or Claude/OpenAI chosen by `config.py`).
  5. The reply is saved to the transcript, and `cli.py` + `ui.py` draw the box: reply, context meter, and any message that just fell out.
