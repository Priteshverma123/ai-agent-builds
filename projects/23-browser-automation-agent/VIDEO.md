# Video hooks · 23 Browser Automation Agent

- **hook:** This agent never sees HTML, and it still checks out.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  |     - searchbox "Search products" [ref=e4]                                               |
  [think ] (step 1) I see a searchbox 'Search products' [e4]. Search for the product.
  [act   ] type e4 (searchbox "Search products") {'text': 'blue ceramic mug', 'submit': True}
  [think ] (step 3) Quantity is 1; I need 2.
  [think ] (step 9) Dialog says 'Place order for $24.00?'. I expect $24.00 (cart + shipping):
           matches, confirm.
  [ok    ] Accepted dialog "Place order for $24.00?". Submitted form, now at /order (HTTP 422)
  [think ] (step 10) The page shows an error: 'Please accept the terms of sale to place your
  [act   ] check e35 (checkbox "I accept the terms of sale")
  [answer] Thank you, Ada Lovelace! Order A1001: $24.00. A receipt was sent to
  ```
- **diagram:** HTML page → DOM → Accessibility snapshot with refs → LLM picks "click e16" → Browser acts → new snapshot
- **real_world:** A small shop's agent reorders stock every Monday from a supplier portal that has no API.
- **try_it:** Run `python demo.py --goal "Buy 1 Red Ceramic Mug with standard shipping for Ada Lovelace (ada@example.com)"` and watch the agent notice the disabled button.

- **flow_steps:**
  1. `cli.py` loads settings from `config.py`, starts the simulated shop in `site.py`, and hands the goal to `BrowserAgent` in `agent.py`.
  2. `browser.py` loads the page, `dom.py` parses the HTML, and `a11y.py` turns it into an accessibility snapshot where every button and field gets a ref like `e16`.
  3. The model (`llm.py`) reads only that snapshot and picks a tool from `tools.py`, such as "type e4 blue ceramic mug" or "click e16".
  4. `tools.execute()` runs it on the browser; the shop answers, and the agent gets OK or ERROR plus a fresh snapshot (here, a 422 "accept the terms" error it then fixes).
  5. Before confirming, the agent checks the dialog total matches the cart, places the order, and calls `finish`; the CLI prints what the shop really received.
