# Video hooks · 04 Structured Output Extractor

- **hook:** The AI's JSON was wrong. So we showed it the errors.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  +-- invoice_acme.txt -> Invoice ---------------------------------------------+
  | attempt 1 : invalid (3 error(s))                                           |
  |             - invoice_date: Input should be a valid date or datetime,      |
  |             - total: Input should be a valid decimal (got '$725.75')       |
  | attempt 2 : valid                                                          |
  | result    : OK: a validated Invoice after 2 attempt(s)                     |
  +-- invoice_bad_total.txt -> Invoice ----------------------------------------+
  |             - (whole object): Value error, total 300.00 does not equal     |
  | result    : FAILED: send to a human for review (bad data in, no valid data |
  ```
- **diagram:** `Messy email` → `LLM + JSON Schema` → `Pydantic validate` → `Repair with errors (loop)` → `Typed JSON or human review`
- **real_world:** An accounts-payable inbox where invoices become ERP-ready JSON, and invoices that don't add up get flagged.
- **try_it:** Edit `examples/invoice_bad_total.txt` so the total is right and watch it pass.
- **flow_steps:**
  1. `cli.py` reads a messy document from `examples/` and picks the target pydantic model from `schemas.py`.
  2. `extract.py` puts that model's exact JSON Schema in the prompt and asks the model in `llm.py` for one JSON object.
  3. `parse_json()` digs the object out of the reply, and the pydantic model validates types, formats and business rules (does the total add up?).
  4. If it fails, `extract()` sends the model its own output plus the exact errors and asks for a fix, up to the attempt limit from `config.py`.
  5. `cli.py` prints every attempt: a validated, typed object, or "send to a human for review" when bad data can't be repaired.
