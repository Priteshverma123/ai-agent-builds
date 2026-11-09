# VIDEO · 29 SRE Incident Agent

**hook:** This AI finds the outage cause, then asks permission to fix it.

**demo_cmd:** `python demo.py`

**demo_output:**
```
  [ 1] 14:12  ACT     detect_anomalies()  risk=none
              OBSERVE 3 anomalies: checkout-api.latency_p95_ms since 14:05 (179.73 -> 966.17)
  [ 4] 14:15  OBSERVE checkout-api v2.14.0 deploy (#4812) caused the regression (0.95)
              PLAN    runbook 'Suspected bad deploy': freeze_deploys > restart_service > rollback_deploy > verify_recovery
  [ 6] 14:19  ACT     restart_service(service=checkout-api)  risk=medium  -> needs human approval
              DENIED  by on-call (alex): a restart won't undo a config change; roll back instead
  [ 7] 14:21  ACT     rollback_deploy(service=checkout-api, to_version=v2.13.2)  risk=high  -> needs human approval
              OK      approved by on-call (alex): regression started 2 min after the deploy
  [ 8] 14:24  OBSERVE checkout-api p95=184.0ms errors=0.4% -> within SLO
  blameless lint: PASS (0 issues)
```

**diagram:** Alert → Detect anomalies + group logs → Rank hypotheses (evidence) → Runbook tools + human approval → Timeline + postmortem

**real_world:** An e-commerce on-call engineer gets paged at 2 a.m.; the agent has already found the bad deploy and is waiting for a "y" to roll it back.

**try_it:** Run `python demo.py --interactive`, deny the rollback, and watch the agent escalate instead of faking success.

**flow_steps:**
1. `demo.py` calls `cli.main()`; `demo.py` in the package loads `Settings` and wires `FileTelemetry`, `MockInfra`, the on-call `ScriptedApprover` and the LLM into `IncidentAgent` (`services/agent.py`).
2. Each turn the LLM (`adapters/llm.py`) reads the `AgentState` and proposes one tool; `ToolRegistry.execute()` in `services/tools.py` runs read-only tools straight away: anomalies, log signatures, recent deploys.
3. `rank()` in `services/hypotheses.py` scores every candidate cause with evidence; the v2.14.0 deploy wins at 0.95 and `load_runbook()` turns its runbook into a plan.
4. Every mutating step goes to the human first: the restart is denied, the rollback is approved, and `MockInfra` (`adapters/infra.py`) really rolls back.
5. `verify_recovery` confirms the service is back within SLO, then `build_timeline()` and `postmortem.render()` write `out/postmortem.md` and `lint_blameless()` checks it.

