# VIDEO · 18 SQL Data Analyst Agent

hook: This AI writes SQL, fixes its own bugs, and refuses DELETE.

demo_cmd: python demo.py

demo_output:
```text
Q: What is the average order value by country?
  DRAFT    | SELECT c.country, ROUND(AVG(o.total), 2) AS avg_order_value ...
  ERROR    | sqlite: no such column: o.total
  REPAIR   | orders has no total column; compute totals from order_items first.
  EXECUTE  | 5 row(s) x 2 col(s) in 1.5 ms
| Germany | ############################## 218.25                            |
| USA     | #########################      184.00                            |
Q: Delete all refunded orders to clean up the data
  BLOCKED  | only SELECT queries are allowed, got DELETE - refusing, no retry
```

diagram:
1. Question -> schema grounding (tables, FKs, sample values)
2. LLM drafts SQL as JSON
3. SQL guard: unsafe = refuse, invalid = repair
4. Read-only SQLite (mode=ro + authorizer) executes
5. Chart inference -> answer + ChartSpec JSON

real_world: A sales manager asks "revenue by region last quarter?" in Slack and gets a chart, while the agent's
database user can only read a replica.

try_it: Ask "Which country has the most refunded orders?" and add the rule to the mock - or point it at a real model.

flow_steps:
1. `cli.py` loads settings from `config.py`, builds the shop database with `db.py`, and opens it read-only (`mode=ro` plus an authorizer).
2. `schema.py` picks the tables the question is about and writes a schema card with columns, foreign keys and sample values.
3. `agent.py` asks the model in `llm.py` for JSON `{sql, rationale}`; `guard.py` refuses writes outright and sends invalid SQL back for repair.
4. `ReadOnlyDatabase.run()` executes with a time budget; a SQLite error like "no such column" becomes a repair prompt and the model fixes its own query.
5. `chart.py` picks KPI, bar, line or table from the result's shape, and the answer's numbers come only from the database.
