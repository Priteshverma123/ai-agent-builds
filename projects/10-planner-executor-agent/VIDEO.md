# Video hooks · 10 Planner-Executor Agent

- **hook:** The hotel was sold out. The agent rewrote only one step of its plan.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [FAIL  ] s4   book_hotel(hotel_id=H-ALFAMA, nights=2)
           x Alfama Patio Hotel is sold out for those dates
  [think ] step s4 failed -> asking the planner for plan v2
  [diff  ] plan v1 -> v2   (= kept  ~ changed  - removed  + added)
           = s2   book_flight(flight_id=$s1.0.id)   (done)
           - s4   book_hotel(hotel_id=$s3.0.id, nights=2)
           + s3b  search_hotels(city=Lisbon, check_in=2026-11-12, nights=2, exclude=[H-ALFAMA])
           + s4b  book_hotel(hotel_id=$s3b.0.id, nights=2)
  [run   ] s4b  book_hotel(hotel_id=H-BAIXA, nights=2)
  Booked: TAP 07:05; Baixa House x2 nights  |  total 378 EUR
  ```
- **diagram:** Goal → Planner (plan v1) → Executor → Failure → Re-plan + diff → Done
- **real_world:** A travel assistant books your conference trip, and when the hotel is full it rebooks without touching the flight it already bought.
- **try_it:** Mark every Lisbon hotel as sold out and watch the agent give up after two re-plans instead of looping.
- **flow_steps:**
  1. `cli.py` reads the goal from `examples/goal.txt` and hands it to `PlanExecuteAgent` in `agent.py`.
  2. The planner in `llm.py` returns the whole trip as a JSON plan, and `plan.py` (`parse_plan`) checks every tool and `$s1.0.id` reference before anything runs.
  3. The `Executor` in `agent.py` runs the steps in order, filling in references from earlier outputs, against `TravelWorld` in `tools.py`.
  4. Booking the cheapest hotel fails (sold out), so `agent.py` sends the plan, what already succeeded and the error back to the planner.
  5. The planner returns plan v2, `plan.py` (`diff_plans`) shows what was kept, changed and added, and only the new steps run: no flight is booked twice.
  6. The run ends with a RESULT box and the bookings and total spend printed by `cli.py`.
