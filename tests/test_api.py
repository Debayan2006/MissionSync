"""Contract and end-to-end tests of the persisted coordination workflow.

Assertions check observable state and permission/transaction boundaries rather
than mocking the agents, planner, or database.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import re
import sqlite3
from time import monotonic, sleep

import pytest

from tests.api_catalogue import API_CATALOGUE
from tests.test_engine import assert_plan_invariants


BASE = "/api/v1"
AGENT_IDS = {"vision", "incident", "weather", "resource", "risk", "coordinator"}


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def items(response):
    return ok(response)["items"]


def incident_payload(**overrides):
    payload = {
        "title": "Synthetic urgent rescue report",
        "description": "Synthetic ground report: people stranded by rising flood water.",
        "category": "flood",
        "coordinates": {"lat": 22.57, "lng": 88.36},
        "people_at_risk": 80,
        "damage_severity": 8.0,
        "response_time_minutes": 90,
    }
    payload.update(overrides)
    return payload


def generate(client, roles, **payload):
    return ok(client.post(f"{BASE}/missions/generate", json=payload, headers=roles["analyst"]), 201)


def completed(client, path, roles):
    deadline = monotonic() + 5
    while True:
        result = ok(client.get(BASE + path, headers=roles["viewer"]))
        if result["status"] not in {"queued", "running"}:
            assert result["status"] == "completed", result
            return result
        assert monotonic() < deadline, f"Job did not complete: {path}"
        sleep(0.01)


def test_all_prd_endpoints_are_implemented(client):
    paths = ok(client.get("/openapi.json"))["paths"]
    normalized = {
        re.sub(r"\{[^}]+\}", "{param}", path): set(spec)
        for path, spec in paths.items()
    }
    missing = []
    for path, methods in API_CATALOGUE.items():
        key = re.sub(r"\{[^}]+\}", "{param}", BASE + path)
        absent = {method.lower() for method in methods} - normalized.get(key, set())
        missing.extend(f"{method.upper()} {BASE}{path}" for method in sorted(absent))
    assert not missing, "Missing required PRD endpoints:\n" + "\n".join(missing)


def test_health_readiness_and_persisted_dashboard(client, roles, seeded):
    assert ok(client.get(f"{BASE}/health"))["status"] == "ok"
    assert ok(client.get(f"{BASE}/ready"))["status"] == "ready"
    incidents = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))
    resources = items(client.get(f"{BASE}/resources", headers=roles["viewer"]))
    assert len(incidents) >= 3 and len(resources) >= 3
    summary = ok(client.get(f"{BASE}/dashboard/summary", headers=roles["viewer"]))
    assert summary["incident_total"] == len(incidents)
    assert summary["available_resources"] + summary["assigned_resources"] == len(resources)
    assert items(client.get(f"{BASE}/dashboard/activity", headers=roles["viewer"]))


def test_coordinate_validation_and_unknown_values(client, roles):
    for coordinates in ({"lat": 91, "lng": 88}, {"lat": 22, "lng": -181}, {"lat": "bad", "lng": 88}):
        response = client.post(f"{BASE}/incidents", json=incident_payload(coordinates=coordinates), headers=roles["analyst"])
        assert response.status_code == 422, response.text
    incident = ok(client.post(
        f"{BASE}/incidents",
        json=incident_payload(people_at_risk=None, damage_severity=None, response_time_minutes=None),
        headers=roles["analyst"],
    ), 201)
    persisted = ok(client.get(f"{BASE}/incidents/{incident['id']}", headers=roles["viewer"]))
    assert persisted["people_at_risk"] is None
    assert persisted["damage_severity"] is None
    assert persisted["response_time_minutes"] is None


def test_create_analysis_ranking_evidence_and_history(client, roles, seeded):
    incident = ok(client.post(f"{BASE}/incidents", json=incident_payload(), headers=roles["analyst"]), 201)
    iid = incident["id"]
    runs = items(client.get(f"{BASE}/agents/runs", params={"incident_id": iid}, headers=roles["viewer"]))
    assert {run["agent_id"] for run in runs} >= AGENT_IDS
    assert all(run["status"] == "completed" for run in runs)
    assert all(run.get("input_snapshot") and run.get("result") for run in runs)
    assert all(run.get("started_at") and run.get("completed_at") for run in runs)
    persisted = ok(client.get(f"{BASE}/incidents/{iid}", headers=roles["viewer"]))
    assert 0 <= persisted["priority_score"] <= 100
    assert persisted["priority_band"] in {"critical", "high", "medium", "low"}
    ordered = items(client.get(f"{BASE}/incidents", params={"sort": "priority_score", "order": "desc"}, headers=roles["viewer"]))
    scores = [row["priority_score"] for row in ordered]
    assert scores == sorted(scores, reverse=True)
    assert items(client.get(f"{BASE}/incidents/{iid}/evidence", headers=roles["viewer"]))
    assert items(client.get(f"{BASE}/incidents/{iid}/history", headers=roles["viewer"]))
    analysis = ok(client.post(f"{BASE}/incidents/{iid}/analyze", json={}, headers=roles["analyst"]), 202)
    assert {run["agent_id"] for run in analysis["runs"]} >= AGENT_IDS
    assert analysis["status"] == "queued" and analysis["mission"] is None
    assert all(run["status"] == "queued" and run["result"] is None for run in analysis["runs"])
    final_runs = [completed(client, f"/agents/runs/{run['id']}", roles) for run in analysis["runs"]]
    coordinator = next(run for run in final_runs if run["agent_id"] == "coordinator")
    mission = ok(client.get(f"{BASE}/missions/{coordinator['result']['mission_id']}", headers=roles["viewer"]))
    assert mission["input_versions"]


def test_incident_search_filters_pagination_and_optimistic_edit(client, roles, seeded):
    incident = ok(client.post(f"{BASE}/incidents", json=incident_payload(title="Unique monsoon marker"), headers=roles["analyst"]), 201)
    result = ok(client.get(f"{BASE}/incidents", params={"search": "Unique monsoon marker", "category": "flood", "page_size": 1}, headers=roles["viewer"]))
    assert result["total"] == 1
    assert result["items"][0]["id"] == incident["id"]
    iid = incident["id"]
    current = ok(client.get(f"{BASE}/incidents/{iid}", headers=roles["viewer"]))
    updated = ok(client.patch(f"{BASE}/incidents/{iid}", json={"expected_version": current["version"], "title": "Revised report", "damage_severity": 9.5}, headers=roles["analyst"]))
    assert updated["version"] > current["version"]
    assert updated["title"] == "Revised report"
    stale = client.patch(f"{BASE}/incidents/{iid}", json={"expected_version": current["version"], "title": "Lost update"}, headers=roles["analyst"])
    assert stale.status_code == 409
    assert ok(client.get(f"{BASE}/incidents/{iid}", headers=roles["viewer"]))["title"] == "Revised report"


def test_event_idempotency(client, roles, seeded):
    headers = {**roles["analyst"], "Idempotency-Key": "integration-identical-event"}
    first = ok(client.post(f"{BASE}/simulator/incidents", json=incident_payload(title="Deduplicated incident"), headers=headers), 201)
    second_response = client.post(f"{BASE}/simulator/incidents", json=incident_payload(title="Deduplicated incident"), headers=headers)
    assert second_response.status_code in (200, 201), second_response.text
    assert second_response.json() == first
    found = items(client.get(f"{BASE}/incidents", params={"search": "Deduplicated incident"}, headers=roles["viewer"]))
    assert len(found) == 1


@pytest.mark.parametrize("path,body", [
    ("/incidents", incident_payload()),
    ("/resources", {"name": "Unauthorized truck", "type": "rescue", "capacity": 20, "coordinates": {"lat": 22, "lng": 88}}),
    ("/missions/generate", {}),
    ("/simulator/pause", {}),
    ("/agents/runs", {}),
])
def test_viewer_cannot_mutate(client, roles, path, body):
    assert client.post(BASE + path, json=body, headers=roles["viewer"]).status_code == 403


def test_unauthenticated_mutation_is_rejected(client):
    assert client.post(f"{BASE}/incidents", json=incident_payload()).status_code == 401


def test_analyst_cannot_approve_or_reset(client, roles, seeded):
    mission = generate(client, roles)
    mid = mission["id"]
    for action, fields in (("approve", {}), ("reject", {"reason": "Test rejection"}), ("request-revision", {"comment": "Check constraints"})):
        response = client.post(f"{BASE}/missions/{mid}/{action}", json={"expected_version": mission["proposal_version"], **fields}, headers=roles["analyst"])
        assert response.status_code == 403, response.text
    assert client.post(f"{BASE}/simulator/reset", json={"scenario_id": "kolkata-flood", "confirmed": True}, headers=roles["analyst"]).status_code == 403
    assert client.patch(f"{BASE}/settings", json={"expected_version": 1}, headers=roles["analyst"]).status_code == 403


def test_agent_registry_job_execution_and_retry_boundary(client, roles, seeded):
    registry = items(client.get(f"{BASE}/agents", headers=roles["viewer"]))
    assert {agent["id"] for agent in registry} == AGENT_IDS
    for agent in registry:
        detail = ok(client.get(f"{BASE}/agents/{agent['id']}", headers=roles["viewer"]))
        assert detail["id"] == agent["id"]
    incident = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))[0]
    run = ok(client.post(f"{BASE}/agents/runs", json={"agent_id": "vision", "incident_id": incident["id"]}, headers=roles["analyst"]), 202)
    assert run["status"] == "queued" and run["result"] is None
    detail = completed(client, f"/agents/runs/{run['id']}", roles)
    assert detail["agent_id"] == "vision" and detail["status"] == "completed"
    assert detail["result"] and detail["confidence"] is not None
    assert client.post(f"{BASE}/agents/runs/{run['id']}/retry", json={}, headers=roles["analyst"]).status_code == 409
    assert client.get(f"{BASE}/agents/nonexistent", headers=roles["viewer"]).status_code == 404
    assert client.get(f"{BASE}/agents/runs/nonexistent", headers=roles["viewer"]).status_code == 404


def test_resources_inventory_availability_and_optimistic_updates(client, roles, seeded):
    resource = ok(client.post(f"{BASE}/resources", json={
        "name": "Synthetic extra rescue boat", "type": "rescue", "capacity": 80,
        "coordinates": {"lat": 22.58, "lng": 88.37}, "estimated_response_time": 20,
    }, headers=roles["analyst"]), 201)
    rid = resource["id"]
    stored = ok(client.get(f"{BASE}/resources/{rid}", headers=roles["viewer"]))
    assert stored["capacity"] == 80
    assert stored["available_capacity"] == 80
    filtered = items(client.get(f"{BASE}/resources", params={"type": "rescue", "status": "available"}, headers=roles["viewer"]))
    assert rid in {row["id"] for row in filtered}
    assert items(client.get(f"{BASE}/resources/{rid}/assignments", headers=roles["viewer"])) == []
    availability = items(client.get(f"{BASE}/resources/availability", headers=roles["viewer"]))
    assert rid in {row["id"] for row in availability}
    disabled = ok(client.patch(f"{BASE}/resources/{rid}", json={"expected_version": stored["version"], "status": "unavailable"}, headers=roles["analyst"]))
    assert disabled["status"] == "unavailable" and disabled["version"] > stored["version"]
    assert client.patch(f"{BASE}/resources/{rid}", json={"expected_version": stored["version"], "status": "available"}, headers=roles["analyst"]).status_code == 409


def test_reject_revision_and_audit_reasons(client, roles, seeded):
    original = generate(client, roles)
    revised = ok(client.post(f"{BASE}/missions/{original['id']}/request-revision", json={
        "expected_version": original["proposal_version"], "comment": "Prioritize fastest feasible evacuation",
    }, headers=roles["commander"]), 201)
    assert revised["proposal_version"] > original["proposal_version"]
    rejection = ok(client.post(f"{BASE}/missions/{revised['id']}/reject", json={
        "expected_version": revised["proposal_version"], "reason": "Wait for an updated synthetic report",
    }, headers=roles["commander"]))
    assert rejection["status"] == "rejected"
    detail = ok(client.get(f"{BASE}/missions/{revised['id']}", headers=roles["viewer"]))
    assert detail["status"] == "rejected"
    history = items(client.get(f"{BASE}/missions/{revised['id']}/history", headers=roles["viewer"]))
    assert any(row["action"] == "mission.rejected" and row["reason"] == "Wait for an updated synthetic report" for row in history)
    audits = items(client.get(f"{BASE}/audit", params={"search": "Wait for an updated synthetic report"}, headers=roles["viewer"]))
    assert any(row["entity_id"] == revised["id"] for row in audits)
    assert client.post(f"{BASE}/missions/{revised['id']}/reject", json={
        "expected_version": revised["proposal_version"], "reason": "Repeat decision",
    }, headers=roles["commander"]).status_code == 409


def test_approval_is_persisted_and_capacity_safe(client, roles, seeded):
    proposal = generate(client, roles)
    assert proposal["assignments"] and proposal["input_versions"]
    approved = ok(client.post(f"{BASE}/missions/{proposal['id']}/approve", json={
        "expected_version": proposal["proposal_version"],
    }, headers=roles["commander"]))
    assert approved["status"] == "approved"
    resources = items(client.get(f"{BASE}/resources", headers=roles["viewer"]))
    assert all(0 <= resource["available_capacity"] <= resource["capacity"] for resource in resources)
    for assignment in approved["assignments"]:
        rows = items(client.get(f"{BASE}/resources/{assignment['resource_id']}/assignments", headers=roles["viewer"]))
        assert any(row["mission_id"] == approved["id"] for row in rows)
    audit = items(client.get(f"{BASE}/audit", params={"entity_id": approved["id"]}, headers=roles["viewer"]))
    decisions = [row for row in audit if row["action"] == "mission.approved"]
    assert len(decisions) == 1
    assert decisions[0]["actor_id"] and decisions[0]["timestamp"]
    assert client.post(f"{BASE}/missions/{approved['id']}/approve", json={
        "expected_version": proposal["proposal_version"],
    }, headers=roles["commander"]).status_code == 409


def test_material_resource_change_replans_and_stale_approval_fails(client, roles, seeded):
    original = generate(client, roles)
    rid = original["assignments"][0]["resource_id"]
    resource = ok(client.get(f"{BASE}/resources/{rid}", headers=roles["viewer"]))
    changed = client.post(f"{BASE}/simulator/resources", json={
        "resource_id": rid, "expected_version": resource["version"], "status": "unavailable",
    }, headers=roles["analyst"])
    assert changed.status_code in (200, 201), changed.text
    stale = client.post(f"{BASE}/missions/{original['id']}/approve", json={
        "expected_version": original["proposal_version"],
    }, headers=roles["commander"])
    assert stale.status_code == 409, stale.text
    missions = items(client.get(f"{BASE}/missions", headers=roles["viewer"]))
    newer = [row for row in missions if row["proposal_version"] > original["proposal_version"]]
    assert newer, "Material input must produce a new persisted proposal"
    assert all(a["resource_id"] != rid for row in newer for a in row["assignments"])
    regenerated = ok(client.post(f"{BASE}/missions/{original['id']}/regenerate", json={}, headers=roles["analyst"]), 201)
    assert regenerated["proposal_version"] > original["proposal_version"]
    assert items(client.get(f"{BASE}/missions/{original['id']}/conflicts", headers=roles["viewer"]))


def test_weather_constraint_reports_infeasible_and_replans(client, roles, seeded):
    original = generate(client, roles)
    response = client.post(f"{BASE}/simulator/weather", json={"hazard_risk": 1, "access_blocked": True}, headers=roles["analyst"])
    assert response.status_code == 200, response.text
    missions = items(client.get(f"{BASE}/missions", headers=roles["viewer"]))
    latest = max(missions, key=lambda row: row["proposal_version"])
    assert latest["proposal_version"] > original["proposal_version"]
    assert latest["status"] == "infeasible"
    assert latest["conflicts"]
    assert not latest["assignments"]
    assert client.post(f"{BASE}/missions/{latest['id']}/approve", json={
        "expected_version": latest["proposal_version"],
    }, headers=roles["commander"]).status_code == 409
    cleared = client.post(f"{BASE}/simulator/weather", json={"hazard_risk": 0.1, "access_blocked": False}, headers=roles["analyst"])
    assert cleared.status_code == 200, cleared.text
    restored = generate(client, roles)
    assert restored["assignments"] and restored["status"] != "infeasible"


def test_simultaneous_approval_commits_exactly_once(client, roles, seeded):
    proposal = generate(client, roles)
    def approve(_):
        return client.post(f"{BASE}/missions/{proposal['id']}/approve", json={
            "expected_version": proposal["proposal_version"],
        }, headers=roles["commander"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(approve, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    audit = items(client.get(f"{BASE}/audit", params={"entity_id": proposal["id"]}, headers=roles["viewer"]))
    assert len([row for row in audit if row["action"] == "mission.approved"]) == 1
    assert all(row["available_capacity"] >= 0 for row in items(client.get(f"{BASE}/resources", headers=roles["viewer"])))


def test_feasible_alternatives_are_distinct_and_can_be_approved(client, roles, seeded):
    proposal = generate(client, roles)
    incidents = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))
    resources = items(client.get(f"{BASE}/resources", headers=roles["viewer"]))
    assert_plan_invariants(proposal["assignments"], incidents, resources)
    assert proposal["alternatives"], "Seeded scenario must demonstrate comparison of feasible alternatives"
    for alternative in proposal["alternatives"]:
        assert alternative["status"] == "feasible"
        assert alternative["assignments"] != proposal["assignments"]
        assert alternative["trade_off"]
        assert_plan_invariants(alternative["assignments"], incidents, resources)
    chosen = proposal["alternatives"][0]
    approved = ok(client.post(f"{BASE}/missions/{proposal['id']}/approve", json={
        "expected_version": proposal["proposal_version"], "alternative_id": chosen["id"],
    }, headers=roles["commander"]))
    assert approved["assignments"] == chosen["assignments"]
    assert approved["chosen_alternative_id"] == chosen["id"]


def test_controlled_conflict_produces_explanation_and_replan(client, roles, seeded):
    before = items(client.get(f"{BASE}/missions", headers=roles["viewer"]))
    response = client.post(f"{BASE}/simulator/conflicts", json={}, headers=roles["analyst"])
    assert response.status_code == 201, response.text
    after = items(client.get(f"{BASE}/missions", headers=roles["viewer"]))
    assert max(row["proposal_version"] for row in after) > max(row["proposal_version"] for row in before)
    latest = max(after, key=lambda row: row["proposal_version"])
    assert latest["conflicts"] and latest["status"] == "infeasible"
    conflicts = items(client.get(f"{BASE}/missions/{latest['id']}/conflicts", headers=roles["viewer"]))
    assert conflicts and all(row["type"] and row["message"] for row in conflicts)
    assert not latest["alternatives"] or all(row["status"] == "feasible" for row in latest["alternatives"])


def test_pause_resume_changes_generator_and_preserves_history(client, roles, seeded):
    before = ok(client.get(f"{BASE}/state", headers=roles["viewer"]))
    paused = ok(client.post(f"{BASE}/simulator/pause", json={}, headers=roles["analyst"]))
    assert paused["paused"] is True
    service = client.app.state.service
    service.tick()
    after = ok(client.get(f"{BASE}/state", headers=roles["viewer"]))
    assert after["simulation"]["event_counter"] == before["simulation"]["event_counter"]
    assert {row["id"] for row in after["incidents"]} == {row["id"] for row in before["incidents"]}
    resumed = ok(client.post(f"{BASE}/simulator/resume", json={}, headers=roles["analyst"]))
    assert resumed["paused"] is False
    service.tick()
    ticked = ok(client.get(f"{BASE}/state", headers=roles["viewer"]))
    assert ticked["simulation"]["event_counter"] == before["simulation"]["event_counter"] + 1
    assert ticked["simulation"]["weather"]["version"] > before["simulation"]["weather"]["version"]
    assert len(ticked["missions"]) > len(before["missions"])
    ok(client.post(f"{BASE}/simulator/pause", json={}, headers=roles["analyst"]))


def _stored_scope(client, scenario_id):
    with sqlite3.connect(client.test_database_path) as database:
        rows = database.execute("SELECT kind,id,data FROM entities WHERE scenario_id=? ORDER BY kind,id", (scenario_id,)).fetchall()
    return rows


def test_reset_requires_confirmation_is_scoped_and_preserves_audit(client, roles, seeded):
    scenarios = items(client.get(f"{BASE}/simulator/scenarios", headers=roles["viewer"]))
    assert {row["id"] for row in scenarios} == {"kolkata-flood", "industrial-fire"}
    ok(client.post(f"{BASE}/simulator/scenarios/industrial-fire/load", json={"confirmed": True}, headers=roles["analyst"]))
    unaffected = _stored_scope(client, "industrial-fire")
    assert unaffected
    audit_before = items(client.get(f"{BASE}/audit", headers=roles["viewer"]))
    response = client.post(f"{BASE}/simulator/reset", json={"scenario_id": "kolkata-flood", "confirmed": False}, headers=roles["administrator"])
    assert response.status_code == 422, response.text
    ok(client.post(f"{BASE}/simulator/reset", json={"scenario_id": "kolkata-flood", "confirmed": True}, headers=roles["administrator"]))
    assert _stored_scope(client, "industrial-fire") == unaffected
    audit_after = {row["id"]: row for row in items(client.get(f"{BASE}/audit", headers=roles["viewer"]))}
    assert all(audit_after.get(row["id"]) == row for row in audit_before)
    assert any(row["action"] == "simulation.reset" and row["entity_id"] == "kolkata-flood" for row in audit_after.values())


def test_settings_validate_and_material_changes_replan(client, roles, seeded):
    settings = ok(client.get(f"{BASE}/settings", headers=roles["viewer"]))
    proposal = generate(client, roles)
    changed = ok(client.patch(f"{BASE}/settings", json={
        "expected_version": settings["version"], "event_interval_seconds": 30,
        "weights": {"people": 1, "damage": 0, "response": 0, "conflict": 0, "friction": 0},
    }, headers=roles["administrator"]))
    assert changed["version"] > settings["version"]
    assert changed["event_interval_seconds"] == 30
    assert changed["dispatch_enabled"] is False
    assert client.patch(f"{BASE}/settings", json={"expected_version": settings["version"], "event_interval_seconds": 40}, headers=roles["administrator"]).status_code == 409
    assert client.patch(f"{BASE}/settings", json={"expected_version": changed["version"], "event_interval_seconds": 1}, headers=roles["administrator"]).status_code == 422
    incidents = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))
    for row in incidents:
        assert row["priority_score"] == pytest.approx(min(row["people_at_risk"] / 500, 1) * 100)
    assert client.post(f"{BASE}/missions/{proposal['id']}/approve", json={"expected_version": proposal["proposal_version"]}, headers=roles["commander"]).status_code == 409


def test_stress_metrics_are_persisted_and_do_not_claim_unmeasured_accuracy(client, roles, seeded):
    before = ok(client.get(f"{BASE}/state", headers=roles["viewer"]))
    result = ok(client.post(f"{BASE}/simulator/stress-tests", json={"event_count": 20}, headers=roles["analyst"]), 202)
    assert result["status"] == "queued" and result["metrics"] is None
    result = completed(client, f"/simulator/stress-tests/{result['id']}", roles)
    persisted = ok(client.get(f"{BASE}/simulator/stress-tests/{result['id']}", headers=roles["viewer"]))
    assert persisted == result
    assert result["status"] == "completed"
    metrics = result["metrics"]
    assert metrics["sample_count"] == 20 and metrics["invalid_assignment_count"] == 0
    assert 0 <= metrics["recommendation_ms_p50"] <= metrics["recommendation_ms_p95"] <= metrics["recommendation_ms_max"]
    assert metrics["ranking_accuracy"] is None
    assert metrics["conflict_precision"] is None and metrics["conflict_recall"] is None
    after = ok(client.get(f"{BASE}/state", headers=roles["viewer"]))
    assert after["incidents"] == before["incidents"] and after["resources"] == before["resources"]
    assert after["missions"] == before["missions"]


def _parse_sse(text):
    messages = []
    for block in text.strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, _, value = line.partition(":")
            fields[key] = value.strip()
        if "id" in fields and "data" in fields:
            envelope = json.loads(fields["data"])
            assert envelope["id"] == fields["id"] and envelope["type"] == fields.get("event")
            messages.append(envelope)
    return messages


def test_sse_replays_committed_events_and_resumes_by_last_id(client, roles, seeded):
    before = client.app.state.service.store.events_after(0)
    last_id = before[-1]["id"]
    created = ok(client.post(f"{BASE}/simulator/incidents", json=incident_payload(title="SSE persisted event"), headers=roles["analyst"]), 201)
    response = client.get(f"{BASE}/events/stream", params={"once": "true"}, headers={**roles["viewer"], "Last-Event-ID": last_id})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    messages = _parse_sse(response.text)
    assert messages and all(int(row["id"]) > int(last_id) for row in messages)
    committed = client.app.state.service.store.events_after(int(last_id))
    assert messages == committed
    assert any(row["type"] == "incident.created" and row["data"]["entity_id"] == created["id"] for row in messages)
    assert any(row["type"] == "mission.generated" for row in messages)
    persisted = ok(client.get(f"{BASE}/incidents/{created['id']}", headers=roles["viewer"]))
    assert persisted["title"] == "SSE persisted event"
    resumed = client.get(f"{BASE}/events/stream", params={"once": "true"}, headers={**roles["viewer"], "Last-Event-ID": messages[-1]["id"]})
    assert _parse_sse(resumed.text) == []


def test_subset_mission_approves_only_its_selected_incidents(client, roles, seeded):
    selected = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))[0]
    proposal = generate(client, roles, incident_ids=[selected["id"]])
    assert proposal["incident_ids"] == [selected["id"]]
    assert {row["incident_id"] for row in proposal["assignments"]} == {selected["id"]}
    approved = ok(client.post(f"{BASE}/missions/{proposal['id']}/approve", json={"expected_version": proposal["proposal_version"]}, headers=roles["commander"]))
    assert approved["status"] == "approved"
    assignments = [row for resource in items(client.get(f"{BASE}/resources", headers=roles["viewer"]))
                   for row in items(client.get(f"{BASE}/resources/{resource['id']}/assignments", headers=roles["viewer"]))]
    assert {row["incident_id"] for row in assignments} == {selected["id"]}


@pytest.mark.parametrize("field", ["title", "description", "category", "coordinates", "source_reliability", "status"])
def test_incident_patch_rejects_null_required_fields(client, roles, seeded, field):
    current = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))[0]
    response = client.patch(f"{BASE}/incidents/{current['id']}", json={"expected_version": current["version"], field: None}, headers=roles["analyst"])
    assert response.status_code == 422, response.text
    unchanged = ok(client.get(f"{BASE}/incidents/{current['id']}", headers=roles["viewer"]))
    assert unchanged["version"] == current["version"] and unchanged[field] == current[field]


@pytest.mark.parametrize("field", ["name", "type", "coordinates", "capacity", "status", "estimated_response_time"])
def test_resource_patch_rejects_null_required_fields(client, roles, seeded, field):
    current = items(client.get(f"{BASE}/resources", headers=roles["viewer"]))[0]
    response = client.patch(f"{BASE}/resources/{current['id']}", json={"expected_version": current["version"], field: None}, headers=roles["analyst"])
    assert response.status_code == 422, response.text
    unchanged = ok(client.get(f"{BASE}/resources/{current['id']}", headers=roles["viewer"]))
    assert unchanged["version"] == current["version"] and unchanged[field] == current[field]


def test_unknown_measurements_can_be_cleared_explicitly(client, roles, seeded):
    current = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))[0]
    updated = ok(client.patch(f"{BASE}/incidents/{current['id']}", json={
        "expected_version": current["version"], "people_at_risk": None,
        "damage_severity": None, "response_time_minutes": None,
    }, headers=roles["analyst"]))
    assert updated["people_at_risk"] is None and updated["damage_severity"] is None
    assert updated["response_time_minutes"] is None
    assert any(row["unknown"] for row in updated["priority_factors"])


def test_existing_approved_mission_flags_new_conflicts(client, roles, seeded):
    proposal = generate(client, roles)
    approved = ok(client.post(f"{BASE}/missions/{proposal['id']}/approve", json={"expected_version": proposal["proposal_version"]}, headers=roles["commander"]))
    resource_id = approved["assignments"][0]["resource_id"]
    resource = ok(client.get(f"{BASE}/resources/{resource_id}", headers=roles["viewer"]))
    ok(client.patch(f"{BASE}/resources/{resource_id}", json={"expected_version": resource["version"], "status": "unavailable"}, headers=roles["analyst"]))
    current = ok(client.get(f"{BASE}/missions/{approved['id']}", headers=roles["viewer"]))
    assert current["status"] == "approved" and current["requires_review"] is True
    conflicts = items(client.get(f"{BASE}/missions/{approved['id']}/conflicts", headers=roles["viewer"]))
    assert any(row["type"] == "unavailable" and row["resource_id"] == resource_id for row in conflicts)


def test_idempotency_key_cannot_be_reused_for_different_input(client, roles, seeded):
    headers = {**roles["analyst"], "Idempotency-Key": "integration-conflicting-key"}
    first = ok(client.post(f"{BASE}/simulator/incidents", json=incident_payload(title="First key payload"), headers=headers), 201)
    response = client.post(f"{BASE}/simulator/incidents", json=incident_payload(title="Different key payload"), headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"
    assert not items(client.get(f"{BASE}/incidents", params={"search": "Different key payload"}, headers=roles["viewer"]))
    assert ok(client.get(f"{BASE}/incidents/{first['id']}", headers=roles["viewer"]))["title"] == "First key payload"


def test_failed_agent_run_can_be_retried_without_erasing_failure(client, roles, seeded):
    run = items(client.get(f"{BASE}/agents/runs", params={"agent_id": "vision"}, headers=roles["viewer"]))[0]
    service = client.app.state.service
    # A persisted failed-run fixture represents an unavailable optional provider.
    with service.store.transaction() as database:
        failed = service.store.get(database, "run", run["id"])
        failed.update(status="failed", result=None, error_message="Synthetic provider failure fixture")
        service.store.put(database, "run", failed)
    failed_visible = ok(client.get(f"{BASE}/agents/runs/{run['id']}", headers=roles["viewer"]))
    assert failed_visible["status"] == "failed" and failed_visible["error_message"]
    assert ok(client.get(f"{BASE}/dashboard/summary", headers=roles["viewer"]))["healthy_agents"] == 5
    retry = ok(client.post(f"{BASE}/agents/runs/{run['id']}/retry", json={}, headers=roles["analyst"]), 202)
    assert retry["status"] == "queued"
    retry = completed(client, f"/agents/runs/{retry['id']}", roles)
    assert retry["id"] != run["id"] and retry["status"] == "completed"
    assert retry["retry_of"] == run["id"]
    assert ok(client.get(f"{BASE}/agents/runs/{run['id']}", headers=roles["viewer"]))["status"] == "failed"


def test_sqlite_state_and_audit_survive_app_restart(client, roles, seeded):
    from backend.app import create_app
    from fastapi.testclient import TestClient

    created = ok(client.post(f"{BASE}/incidents", json=incident_payload(title="Persistent across application restart"), headers=roles["analyst"]), 201)
    mission = generate(client, roles)
    approved = ok(client.post(f"{BASE}/missions/{mission['id']}/approve", json={"expected_version": mission["proposal_version"]}, headers=roles["commander"]))
    with TestClient(create_app(database_path=str(client.test_database_path))) as restarted:
        stored = ok(restarted.get(f"{BASE}/incidents/{created['id']}", headers=roles["viewer"]))
        assert stored["title"] == created["title"] and stored["version"] == created["version"]
        assert ok(restarted.get(f"{BASE}/missions/{approved['id']}", headers=roles["viewer"]))["status"] == "approved"
        history = items(restarted.get(f"{BASE}/missions/{approved['id']}/history", headers=roles["viewer"]))
        assert any(row["action"] == "mission.approved" for row in history)


def test_errors_are_structured_and_role_headers_cannot_escalate(client, roles, seeded):
    responses = [
        client.get(f"{BASE}/incidents/nonexistent"),
        client.get(f"{BASE}/resources/availability", params={"at": "2026-10-11T12:00:00"}),
        client.get(f"{BASE}/incidents", params={"page": "invalid"}),
        client.post(f"{BASE}/incidents", json=incident_payload(coordinates={"lat": 100, "lng": 88}), headers=roles["analyst"]),
        client.post(f"{BASE}/incidents", json=incident_payload(), headers={**roles["viewer"], "X-Role": "administrator"}),
    ]
    assert [row.status_code for row in responses] == [404, 422, 422, 422, 403]
    for response in responses:
        error = response.json()["error"]
        assert error["code"] and error["message"]
        assert "Traceback" not in response.text


def test_two_competing_proposals_cannot_both_reserve_resources(client, roles, seeded):
    first = generate(client, roles)
    second = generate(client, roles)
    assert first["id"] != second["id"]
    assert {row["resource_id"] for row in first["assignments"]} & {row["resource_id"] for row in second["assignments"]}
    def approve(proposal):
        return client.post(f"{BASE}/missions/{proposal['id']}/approve", json={"expected_version": proposal["proposal_version"]}, headers=roles["commander"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(approve, [first, second]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    approved = responses[0].json() if responses[0].status_code == 200 else responses[1].json()
    missions = items(client.get(f"{BASE}/missions", headers=roles["viewer"]))
    assert len([row for row in missions if row["status"] == "approved"]) == 1
    resources = items(client.get(f"{BASE}/resources", headers=roles["viewer"]))
    assert all(row["available_capacity"] >= 0 for row in resources)
    assignments = [row for resource in resources for row in items(client.get(f"{BASE}/resources/{resource['id']}/assignments", headers=roles["viewer"]))]
    assert {row["mission_id"] for row in assignments} == {approved["id"]}


def test_async_job_replay_keeps_ids_and_does_not_duplicate_execution(client, roles, seeded):
    incident = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))[0]
    headers = {**roles["analyst"], "Idempotency-Key": "queued-job-repeat"}
    payload = {"agent_id": "risk", "incident_id": incident["id"]}
    queued = ok(client.post(f"{BASE}/agents/runs", json=payload, headers=headers), 202)
    assert queued["status"] == "queued" and queued["result"] is None
    final = completed(client, f"/agents/runs/{queued['id']}", roles)
    assert final["id"] == queued["id"] and final["input_snapshot"]
    before = items(client.get(f"{BASE}/missions", headers=roles["viewer"]))
    replay = ok(client.post(f"{BASE}/agents/runs", json=payload, headers=headers), 202)
    assert replay == queued
    assert completed(client, f"/agents/runs/{queued['id']}", roles) == final
    after = items(client.get(f"{BASE}/missions", headers=roles["viewer"]))
    assert after == before


def test_readiness_reports_dependency_failure_without_exposing_details(client, monkeypatch):
    def unavailable():
        raise sqlite3.OperationalError("private simulated database diagnostic")
    with monkeypatch.context() as context:
        context.setattr(client.app.state.service.store, "transaction", unavailable)
        response = client.get(f"{BASE}/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_unavailable"
        assert "private simulated" not in response.text
        assert ok(client.get(f"{BASE}/health"))["status"] == "ok"


def test_queued_analysis_revalidates_inputs_changed_before_execution(client, roles, seeded, monkeypatch):
    selected = items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))[0]
    service = client.app.state.service
    execute = service.execute_analysis
    pending_calls = []
    with monkeypatch.context() as context:
        context.setattr(service, "execute_analysis", lambda *args, **kwargs: pending_calls.append((args, kwargs)))
        queued = ok(client.post(f"{BASE}/incidents/{selected['id']}/analyze", json={}, headers=roles["analyst"]), 202)
    assert queued["status"] == "queued" and len(pending_calls) == 1
    original_version = queued["runs"][0]["input_snapshot"]["incidents"][selected["id"]]
    updated = ok(client.patch(f"{BASE}/incidents/{selected['id']}", json={
        "expected_version": selected["version"], "people_at_risk": 250, "damage_severity": 9,
    }, headers=roles["analyst"]))
    assert updated["version"] > original_version
    args, kwargs = pending_calls[0]
    execute(*args, **kwargs)
    finished = [completed(client, f"/agents/runs/{row['id']}", roles) for row in queued["runs"]]
    for run in finished:
        assert run["initial_input_snapshot"]["incidents"][selected["id"]] == original_version
        assert run["input_snapshot"]["incidents"][selected["id"]] == updated["version"]
    coordinator = next(row for row in finished if row["agent_id"] == "coordinator")
    mission = ok(client.get(f"{BASE}/missions/{coordinator['result']['mission_id']}", headers=roles["viewer"]))
    assert mission["input_versions"]["incidents"][selected["id"]] == updated["version"]
    assert ok(client.get(f"{BASE}/incidents/{selected['id']}", headers=roles["viewer"]))["people_at_risk"] == 250


def test_scenario_switch_preserves_each_scope_material_state(client, roles, seeded):
    created = ok(client.post(f"{BASE}/incidents", json=incident_payload(title="Scope survives scenario switch"), headers=roles["analyst"]), 201)
    weather = ok(client.post(f"{BASE}/simulator/weather", json={"hazard_risk": 0.9, "access_blocked": True}, headers=roles["analyst"]))["weather"]
    ok(client.post(f"{BASE}/simulator/scenarios/industrial-fire/load", json={"confirmed": True}, headers=roles["analyst"]))
    industrial_ids = {row["id"] for row in items(client.get(f"{BASE}/incidents", headers=roles["viewer"]))}
    assert created["id"] not in industrial_ids
    ok(client.post(f"{BASE}/simulator/scenarios/kolkata-flood/load", json={"confirmed": True}, headers=roles["analyst"]))
    state = ok(client.get(f"{BASE}/state", headers=roles["viewer"]))
    assert created["id"] in {row["id"] for row in state["incidents"]}
    assert state["simulation"]["weather"]["hazard_risk"] == weather["hazard_risk"]
    assert state["simulation"]["weather"]["access_blocked"] is True
    assert state["simulation"]["weather"]["version"] == weather["version"]
    assert state["missions"][0]["status"] == "infeasible"


def test_simulator_add_resource_and_weather_version_conflict(client, roles, seeded):
    resource = ok(client.post(f"{BASE}/simulator/resources", json={
        "name": "Simulator added synthetic rescue team", "type": "rescue", "capacity": 4,
        "coordinates": {"lat": 22.59, "lng": 88.38},
    }, headers=roles["analyst"]), 201)
    assert ok(client.get(f"{BASE}/resources/{resource['id']}", headers=roles["viewer"]))["capacity"] == 4
    before = ok(client.get(f"{BASE}/state", headers=roles["viewer"]))["simulation"]["weather"]
    first = ok(client.post(f"{BASE}/simulator/weather", json={
        "expected_version": before["version"], "hazard_risk": 0.7, "access_blocked": False,
    }, headers=roles["analyst"]))
    assert first["weather"]["version"] > before["version"]
    stale = client.post(f"{BASE}/simulator/weather", json={
        "expected_version": before["version"], "hazard_risk": 0, "access_blocked": True,
    }, headers=roles["analyst"])
    assert stale.status_code == 409
    current = ok(client.get(f"{BASE}/state", headers=roles["viewer"]))["simulation"]["weather"]
    assert current == first["weather"]


def test_wrong_proposal_version_is_rejected_without_reservations(client, roles, seeded):
    proposal = generate(client, roles)
    response = client.post(f"{BASE}/missions/{proposal['id']}/approve", json={
        "expected_version": proposal["proposal_version"] + 1,
    }, headers=roles["commander"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "version_conflict"
    assert ok(client.get(f"{BASE}/missions/{proposal['id']}", headers=roles["viewer"]))["status"] == "pending_review"
    assert all(row["status"] == "available" for row in items(client.get(f"{BASE}/resources", headers=roles["viewer"])))
