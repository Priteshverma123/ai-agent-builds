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
