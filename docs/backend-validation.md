# Backend validation

The backend runs without external model, weather or map credentials. Automated tests use an isolated temporary SQLite database, the real FastAPI application, deterministic agents, planner and persisted audit/event records. They do not replace the planner with mocks.

Run from the repository root:

```bash
.local/venv/bin/python -m pytest tests backend/test_engine.py -q --backend-api-coverage
.local/venv/bin/python -m tests.measure_backend
```

`--backend-api-coverage` checks that every required PRD method was actually requested during the full suite. Omit the option for a selected test or a unit-only run. The catalogue contains **47 methods across 41 paths**, all under `/api/v1`; no catalogue endpoint is deferred. OpenAPI completeness is checked separately, including route parameters with different names.

Verified result on 11 October 2026: **99 backend tests passed in 3.06 seconds; 47/47 PRD API methods exercised**. The suite includes the independent engine cases and the backend module's engine regression tests.

## Acceptance coverage

| PRD requirement | What the tests establish |
| --- | --- |
| Scenario → incident → six agents → persisted ranking → proposal | Creation commits the incident, records six structured logical agent outputs, exposes evidence/history and recalculates scores. Lists filter, search, sort and paginate persisted data. |
| Real coordination after weather/resource changes | Material changes create higher proposal versions, flag prior proposals stale, preserve input references, exclude disabled resources and return explicit access/capacity infeasibility. |
| Feasible alternatives and zero over-allocation | Independent checks verify positive integer quantities, known capacities, category eligibility, UTC window ordering, exclusive resource overlap and complete incident demand coverage for generated plans and alternatives. A distinct alternative can be approved. |
| Human review | Approval, rejection and revision persist their status, actor, timestamp and reason. Subset proposals approve only selected incidents. Wrong proposal versions and stale/invalid plans return conflicts without reservations. |
| Concurrent decisions | Two concurrent approvals of one proposal commit once. Two competing proposals sharing resources cannot both approve. Audit decisions and reservations remain consistent. |
| Permissions | Viewer writes fail, analyst decisions/settings/reset fail, unauthorized writes require a session, and a forged role header cannot elevate a viewer session. Roles are explicitly local demo sessions. |
| Unknown values and input validation | Unknown measurements remain null, including deliberate clearing by PATCH. Invalid coordinates and explicit nulls for required fields fail validation without changing versions. Error responses contain structured codes/messages. |
| Optimistic concurrency and idempotency | Stale incident/resource/weather/settings versions fail. A replayed event returns the original response without duplicate incidents; reuse of a key with another payload fails. Queued job replay preserves run IDs and produces no duplicate proposal. |
| Asynchronous jobs | Analysis/retry/stress endpoints return queued `202` bodies. Polling returns completed results under the same IDs. A queued analysis re-reads inputs changed before execution while retaining its initial input snapshot. Failed retry fixtures retain the original failure record. |
| Live event persistence | One-shot SSE replay exactly matches committed database events, includes incident and proposal events, and resumes after `Last-Event-ID`. It verifies event persistence before delivery. Browser reconnect/polling behavior is covered separately by browser tests. |
| Simulation controls and scope | Pause stops generator ticks, resume advances weather/replanning, scenario switching preserves separate material state, and a confirmed administrator reset preserves unrelated scenario data and existing audit records. |
| Persistence and readiness | Incident, approved proposal and decision history survive a second application instance using the same SQLite file. Database failure returns readiness `503` while process health remains available. |
| Stress test honesty | A persisted 20-case planner run reports percentile timings, zero invalid assignments and explicit null ranking/conflict accuracy metrics. The microbenchmark does not change operational incidents/resources/missions. |

The full API catalogue is exercised by these test groups:

| Methods and endpoint family | Test workflow |
| --- | --- |
| Health, readiness, dashboard summary/activity | Seeded state metrics, dependency failure and recent persisted activity |
| Incident list/create/read/update/analyze/evidence/history | Incident lifecycle, filtering, unknowns, validation, version conflicts and queued analysis |
| Agent registry/detail/runs/start/result/retry | All six contracts, individual queued jobs, successful-run retry rejection and failed-run retry |
| Resource list/create/read/update/assignments/availability | Inventory, filters, versioned availability changes and approved reservations |
| Mission list/generate/read/regenerate/conflicts/approve/reject/revision/history | Current-state planning, constraints, alternatives, decisions, audit and concurrent approval |
| Simulator scenarios/load/inject/weather/resources/conflicts/pause/resume/reset/stress/create-result | Deterministic scenarios, events, both resource add/update modes, version conflicts, scoped state and metrics |
| Audit, settings read/update and SSE stream | Searchable immutable decisions, configurable scoring and committed event replay |

## Labeled deterministic cases

`tests/test_engine.py` contains 14 named constraint cases covering a valid assignment, capacity overrun, zero/fractional allocation, unavailable/wrong-capability resources, weather/incident access blocking, missing people/damage/capacity, unmet demand and invalid time windows. Additional cases check overlapping reservations, adjacent half-open windows and malformed existing reservations. Ranking fixtures document the expected order `highest → middle → lower` using explicit people, severity and delay values.

These are transparent regression fixtures, not a representative operational accuracy dataset. Passing them does not establish the proposed ≥90% ranking accuracy or ≥95% conflict-detection targets. There is no trained vision model, live drone feed, external weather observation or LLM accuracy evaluation in these tests.

Normalization is tested as people/500, severity/10, delay/120 (longer delay increases urgency), and 0–1 conflict/friction penalties. The weighted sum is divided by the sum of positive weights, then clamped to a 0–100 score. Missing factors remain unknown with null contributions and lower confidence. Resource capacity is synthetic: one unit supports 100 people for an exclusive 60-minute response window, rounding demand up.

## Measured local backend timings

Measured on 11 October 2026 with Python 3.12.14, Linux x86_64, five visible CPUs, temporary SQLite WAL and FastAPI TestClient. Thirty accepted synthetic events grow the dataset from 3 to 33 incidents with 6 resources. Every resulting complete proposal passes the independent allocation checks; **zero invalid assignments** were observed.

| Measurement | p50 | p95 | Maximum | Samples |
| --- | ---: | ---: | ---: | ---: |
| Incident ingestion roundtrip, including commit, agents and proposal | 31.296 ms | 86.455 ms | 107.176 ms | 30 |
| Accepted event → committed SSE consumed by test client | 36.266 ms | 92.287 ms | 114.840 ms | 30 |
| Recorded agent and proposal generation | 17.835 ms | 41.175 ms | 67.190 ms | 30 |
| Dashboard summary roundtrip | 62.165 ms | 197.953 ms | 211.574 ms | 30 |

The script measures in-process request roundtrips, committed backend events and deterministic CPU processing. It excludes browser render time, network transit, map tiles, external inference and operational dispatch. These results support local prototype performance only; they do not prove the end-to-end ≤2-second live-UI or production ≤5-second response targets. Hardware/load changes can alter the measurements; the command above reproduces the method.

## Remaining boundaries

SQLite and simulated local roles are suitable for this prototype. Production authentication, PostgreSQL/PostGIS migration, provider integrations and licensed vision datasets remain separate work. The failed-agent retry test injects a persisted failed-run fixture; it verifies retry/persistence behavior rather than an actual external-provider outage. Browser navigation, accessibility, map fallback and UI control tests are reported separately.

Starlette currently emits a deprecation warning for its `httpx` TestClient compatibility path. The pinned tests pass through that supported path; it does not indicate a failed request or validation.
