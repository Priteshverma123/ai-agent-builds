# VIDEO · 21 Debate and Consensus

hook: Four AI agents argue, and the judge refuses to fake agreement.

demo_cmd: python demo.py

demo_output:
```text
  pm         CONDITIONAL  0.60  toil: auto-merge only patch releases
             ^ shifted from FOR, because: (no reason given!)
  -> no stance changed this round: debate has settled
+-- JUDGE -------------------------------------------------------------------+
| NO CONSENSUS  (strongest side only 43%, after 3 rounds)                    |
|   conditional  #############                  1.15                         |
|   against      #########                      0.80                         |
|   for          ########                       0.70                         |
|   - security: against=sre; for=architect                                   |
|   - pm r2: for -> conditional   [FLAG: unexplained - possible herding]     |
```

diagram:
1. Question
2. Round 1: independent openings (parallel)
3. Rebuttal rounds until stances settle
4. Judge: weighted tally + threshold
5. Verdict: decision, dissent, cruxes, flags

real_world: An engineering team runs architecture decisions past an architect, SRE, product and finance agent
and files the verdict, including the dissent, in the decision record.

try_it: Edit debates.json so the SRE changes their mind in round 2, and watch the verdict flip to consensus.

flow_steps:
1. `cli.py` reads the question from `examples/debates.json` and `debater.py`'s `make_panel()` seats an architect, an SRE, a PM and a finance lead.
2. `debate.py` runs round 1 with everyone at once and nobody seeing anybody, so no one anchors on the first speaker.
3. From round 2, `transcript_for()` shows each agent the other agents' claims; `debater.py` validates every reply as an `Argument` and retries once if it is malformed.
4. As soon as a round changes no stance, `debate.py` stops and hands all rounds to `judge.py`.
5. `judge.py` tallies confidence-weighted stances against the 66% threshold, keeps the dissent, finds the cruxes and flags anyone who changed sides without a reason.
