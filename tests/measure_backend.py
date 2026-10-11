"""Reproduce local synthetic API timings: python -m tests.measure_backend.

This reports measurements, not browser latency or operational/model accuracy.
Every sample persists a new event, runs agents/planning, then consumes committed
SSE messages. Optional external providers and network transit are excluded.
"""

import json
import math
import os
import platform
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from fastapi.testclient import TestClient

from backend.app import create_app
from tests.test_api import BASE, _parse_sse, incident_payload
from tests.test_engine import assert_plan_invariants


def percentiles(values):
    ordered = sorted(values)
    return {
        "p50_ms": round(median(ordered), 3),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 3),
        "max_ms": round(max(ordered), 3),
        "sample_count": len(values),
    }


def measure(sample_count=30):
    ingestion, delivery, planning, summary = [], [], [], []
    with TemporaryDirectory(prefix="missionsync-measure-") as folder:
        with TestClient(create_app(database_path=f"{folder}/measurement.sqlite3")) as client:
            token = client.post(BASE + "/auth/demo", json={"role": "analyst"}).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            sequence = client.app.state.service.store.events_after(0)[-1]["id"]
            for index in range(sample_count):
                start = perf_counter()
                response = client.post(BASE + "/simulator/incidents", json=incident_payload(
                    title=f"Measured synthetic incident {index + 1}",
                    category=("flood", "fire", "medical")[index % 3],
                    people_at_risk=50 + (index * 37) % 500,
                ), headers={**headers, "Idempotency-Key": f"measurement-event-{index}"})
                assert response.status_code == 201, response.text
                ingestion.append((perf_counter() - start) * 1000)
                incident_id = response.json()["id"]
                events = client.get(BASE + "/events/stream", params={"once": "true"}, headers={"Last-Event-ID": sequence})
                messages = _parse_sse(events.text)
                assert any(row["type"] == "incident.created" and row["data"]["entity_id"] == incident_id for row in messages)
                assert any(row["type"] == "mission.generated" for row in messages)
                delivery.append((perf_counter() - start) * 1000)
                sequence = messages[-1]["id"]
                state = client.get(BASE + "/state").json()
                mission = state["missions"][0]
                assert mission["status"] == "pending_review"
                assert_plan_invariants(mission["assignments"], state["incidents"], state["resources"])
                planning.append(mission["generation_ms"])
                start = perf_counter()
                response = client.get(BASE + "/dashboard/summary")
                assert response.status_code == 200
                summary.append((perf_counter() - start) * 1000)
            return {
                "environment": {"python": platform.python_version(), "platform": platform.system(), "architecture": platform.machine(), "visible_cpu_count": os.cpu_count()},
                "dataset": {"initial_incidents": 3, "final_incidents": 3 + sample_count, "resources": 6, "accepted_synthetic_events": sample_count, "invalid_assignments": 0},
                "ingestion_roundtrip": percentiles(ingestion),
                "event_to_committed_sse_consumed": percentiles(delivery),
                "agent_and_proposal_generation": percentiles(planning),
                "dashboard_summary_roundtrip": percentiles(summary),
                "scope": "In-process FastAPI TestClient, temporary SQLite WAL, deterministic CPU agents, growing synthetic incident dataset. Excludes network, browser, map tiles and external inference. Every resulting complete plan checked with independent invariants.",
            }


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
