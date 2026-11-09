# VIDEO · 22 Parallel Research Swarm

hook: Four AI researchers, one shared browser, zero duplicate facts.

demo_cmd: python demo.py

demo_output:
```text
[ 0.04s] planner  | 4 sub-questions: cost, lifespan, safety, savings
[ 0.17s] cost     | done: 4 findings from 3 docs in 130 ms
[ 0.40s] lifespan | done: 6 findings from 3 docs in 355 ms
[ 0.92s] safety   | FAILED slow-blog: gave up after 2 attempts (TimeoutError)
[ 0.92s] reducer  | 18 findings -> 16 unique claims from 8 sources
- A typical 10 kWh home battery costs between $8,000 and $14,000 installed in 2026. [2][3] (corroborated by 2 sources)
| retried / shared : 2 retried, 2 fetches shared via single-flight           |
| wall time        :     912 ms                                              |
| time in requests :    1465 ms  (what a one-at-a-time crawler would wait)   |
```

diagram:
1. Planner splits the question
2. Parallel workers (asyncio)
3. Shared fetcher: limit, timeout, retry, single-flight
4. Dedup: shingles + Jaccard
5. Cited report with corroboration

real_world: An investment analyst's bot researches a company's market, risks and competitors in parallel and hands
over one deduplicated brief with sources.

try_it: Run with --concurrency 1 and compare the wall time, then add a third mirror of battery-basics (and raise docs_per_worker) to push corroboration to 3.

flow_steps:
1. `cli.py` loads settings from `config.py` and `build_swarm()` builds a search index and one shared `Fetcher` over the local corpus.
2. `swarm.py` asks the planner model (`llm.py`) to split the question into four sub-questions: cost, lifespan, safety, savings.
3. Four workers start at once; each searches the index and fetches its top documents through `corpus.py`'s `Fetcher`, which caps requests at 3 in flight, retries a 503, times out the slow blog, and shares duplicate fetches.
4. The extractor quotes claims from each document, and `grounded()` throws away anything that is not really in the text.
5. `dedup.py` merges the same fact from different sources into one claim with a corroboration count, and `report.py` prints the cited brief and the swarm stats.
