# Video hooks · 12 Evaluator-Optimizer

- **hook:** One AI writes, another grades it, and the score climbs from 27 to 97.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [score ] iter  total    length  keywords   no_hype       cta   clarity  audience   words
  [score ]    1   26.6         5         2         1         1         2         2      69
  [fix   ] writer gets the top 2 issue(s)
           - Mention '10 seconds' (required). Mention 'free' (required).
  [score ]    2   65.6         4         5         5         1         3         2      82
  [score ]    3   78.1         4         5         5         5         3         2      90
  [score ]    4   96.9         4         5         5         5         5         5      35
  | stopped: target reached (96.9 >= 90)                                                   |
  ```
- **diagram:** Brief → Writer → Rubric (checks + LLM judge) → Top-2 fixes → Revise → Best draft
- **real_world:** A marketing team's launch copy that automatically passes brand rules: no hype words, the right length, key facts included, and a clear call to action.
- **try_it:** Run `OPT_TARGET=100 python demo.py` and see how many more rounds it costs to fix the last point.
- **flow_steps:**
  1. `cli.py` loads the brief from `examples/brief.json` (facts, required keywords, banned hype words, word range) and starts `EvaluatorOptimizer` in `optimizer.py`.
  2. The writer in `llm.py` produces a first draft from the brief.
  3. `rubric.py` scores the draft: code checks grade length, keywords, hype and the call to action, and the judge model grades clarity and audience, each with a concrete fix.
  4. `optimizer.py` prints the score row and stops if the score hit 90, stopped improving, or the iteration budget ran out.
  5. Otherwise the writer gets only the two most costly fixes and revises the draft, and the loop goes back to step 3.
  6. `optimizer.py` prints the best draft (not just the last one) and why it stopped.
