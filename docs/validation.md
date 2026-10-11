# Implementation and environment validation

MissionSync's local synthetic workflow was implemented and validated on 11 October 2026. The cloud machine runs Python 3.12.14, Node.js 24.19.0, npm 11.9.0 and system Chromium 154 on Linux with five visible CPUs. No external inference, API credentials or GPU were used.

## Executed checks

| Check | Outcome |
| --- | --- |
| Frozen dependency installation and refresh | `bash scripts/install.sh` passed; pinned transitive Python requirements, npm lockfile, package consistency and frontend build. The installer was rerun successfully. |
| Backend and deterministic engine | 99 tests passed; automated runtime coverage requested all 47 required PRD API methods. See [backend-validation.md](backend-validation.md). |
| Browser workflows | 21 Playwright tests passed in 39.32 seconds using real system Chromium and running services. No tests were skipped. |
| Frontend production build | TypeScript and Vite build passed. |
| Last small fixes | Focused regression checks passed for failed-agent health metrics and notification dismissal; the frontend build passed again. |
| Reusable startup | `bash scripts/start.sh` started both services. Health, database readiness and browser requests passed. Sending TERM to the launch shell stopped its children; restart preserved SQLite state. |
| Isolated check script | `bash scripts/check.sh` passed, launching on temporary ports with a disposable database, then shutting down its services and removing the test database. |
| Repository state | The repository initially contained no commits or project files. All source, docs, manifests and lockfiles are new implementation files. Dependencies, caches, databases and generated builds remain ignored local outputs. |

The browser tests exercise all required route families, landing navigation and demo loading, incident create/edit/cancel/filter/evidence, map focus/markers/keyboard/zoom/filter/resource visibility, resource creation/editing, persisted role choice and disabled viewer writes, revision/approval/rejection/audit, stale-plan blocking and regeneration, scenario switching, severity/weather/resource changes, conflict injection, asynchronous stress results, pause/resume, confirmed reset/cancel, agent output inspection, settings save/discard, dashboard actions and metric navigation, mobile navigation and service error/retry. This is coverage of critical workflows; it is not a formal claim that every possible UI/input combination was exhaustively tested.

The application has also been visually inspected at desktop and mobile sizes. The schematic map is explicitly labeled and works without external tiles. Seeded incidents are automatically fitted to the map.

## Measured HTTP and live-update timings

The loopback benchmark in `scripts/measure.py` runs against a disposable SQLite database. It starts with 3 incidents and 6 resources, measures 50 dashboard requests and 30 complete proposal requests, then injects 10 medical incidents, growing to 13 incidents. Event timings include ingestion, agents, scoring, planning and commit. Live SSE reception excludes browser rendering. Exact recorded results are in [performance.json](performance.json).

| Workflow | p50 | p95 | Maximum | Samples |
| --- | ---: | ---: | ---: | ---: |
| Dashboard HTTP | 3.063 ms | 3.662 ms | 4.059 ms | 50 |
| Complete proposal HTTP | 9.849 ms | 12.901 ms | 17.384 ms | 30 |
| Incident ingestion HTTP | 32.753 ms | 97.031 ms | 97.031 ms | 10 |
| Accepted request → committed SSE reception | 499.380 ms | 502.471 ms | 502.471 ms | 10 |

A separate browser test timed one accepted synthetic event until its incident link became visible without a page reload: **850.58 ms**. This is one local sample, not a UI latency percentile or production guarantee.

The 100-case deterministic planner microbenchmark over the final 13 incidents and 6 resources measured p50 9.103 ms, p95 15.638 ms and maximum 31.416 ms, with **zero invalid assignments**. The independent hard-constraint tests also validate generated and approved assignment capacity/exclusivity. No production over-allocation guarantee follows from a finite synthetic test set.

Reproduce backend/browser validation with:

```bash
cd /workspace/MissionSync
bash scripts/install.sh
bash scripts/check.sh
```

For timing measurements, start the application with a disposable database rather than normal user state:

```bash
MISSION_SYNC_DB="$PWD/.local/benchmark.db" bash scripts/start.sh
# In another shell, from the repository root:
.local/venv/bin/python scripts/measure.py
```

The benchmark deliberately resets its selected scenario and injects synthetic reports. Timing results vary with hardware, concurrent load and accumulated audit/history data.

## Boundaries and deferred integrations

The required PRD API catalogue and local end-to-end coordination workflow are implemented. Vision assessment is a labeled synthetic adapter, report processing is deterministic, and weather/terrain inputs are synthetic configuration. The map uses a coordinate-based schematic fallback. There is no live drone feed, trained image model, uploaded-image inference, external LLM/weather adapter, licensed imagery dataset evaluation, or real-world dispatch integration.

SQLite and simulated role sessions are the local prototype options allowed by the PRD. A deployed service needs a real identity provider, deployment authorization, HTTPS and production database operations. `MISSION_SYNC_ENV=production` or `MISSION_SYNC_DEMO_AUTH=false` blocks demo login and demo-session writes; this does not supply a production login implementation.

Ranking accuracy, conflict precision/recall, image-model quality and operational latency targets remain unverified against a representative labeled dataset. Accuracy fields are explicitly null. The small documented ranking/constraint fixtures are regression cases rather than operational ground truth.

Installation/startup draft fields describe how to reuse the prepared filesystem. Saving a configuration draft does not publish the environment or establish successful restoration in a new task. Publication remains a separate environment-settings action.
