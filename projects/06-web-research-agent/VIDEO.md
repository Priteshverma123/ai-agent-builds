# Video hooks · 06 Web Research Agent

- **hook:** This agent researches like an analyst, and every claim is cited.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [think ] plan -> 3 search queries
           2. heat pump cold climate evidence study
  [tool  ] search("heat pump cold climate evidence study")
            3.69  https://coldclimate-lab.example.org/field-study-2025
  [read  ] fetch https://coldclimate-lab.example.org/field-study-2025  -> source [3] (study)
           "Across all homes, cold-climate heat pumps kept an average COP above 1.8 down to
           -20 C outdoor temperature."
  [skip  ] already read https://hottakes.example.net/heat-pumps-fail
  [check ] citations verified: 5 sources, 0 unsupported line(s) removed
  ```
- **diagram:** Plan queries → Search + Fetch → Extract facts + cite → Write brief → Verify citations
- **real_world:** A consultant gets a cited one-page brief on "Should our client switch to heat pumps?" in seconds, and can check every claim.
- **try_it:** Make the model lie by adding a fake `[42]` citation, and watch the verifier remove it.
- **flow_steps:**
  1. `cli.py` loads settings from `config.py`, opens the local web in `examples/web/` with `corpus.py`, and hands your question to `ResearchAgent` in `agent.py`.
  2. `plan()` asks the model in `llm.py` to split the question into 3 search queries: the topic, the evidence, the drawbacks.
  3. For each query, `LocalWeb.search()` ranks pages with BM25; the agent fetches new pages until the fetch budget runs out, skipping ones it already read.
  4. `extract()` copies out the facts that matter, and `SourceTracker` in `sources.py` gives each useful page a citation number like [3].
  5. `write()` drafts the brief from the numbered notes only, `remove_unverified_lines()` deletes any line citing a source that was never read, and `trace.py` prints the brief with its sources.
