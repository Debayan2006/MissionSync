"""Labeled synthetic constraint/ranking cases and independent plan invariants."""

from copy import deepcopy
from datetime import datetime
from itertools import combinations

import pytest

from backend.engine import DEFAULT_WEIGHTS, detect_constraints, plan, score_incident


WEATHER = {"access_blocked": False, "hazard_risk": 0.2, "planning_start_at": "2026-10-11T12:00:00Z"}


def incident(iid="incident-a", **overrides):
    return {
        "id": iid, "title": iid, "category": "flood", "status": "open", "version": 1,
        "people_at_risk": 200, "damage_severity": 7, "response_time_minutes": 60,
        "source_reliability": 0.8, **overrides,
    }


def resource(rid="resource-a", **overrides):
    return {
        "id": rid, "type": "rescue", "capacity": 3, "available_capacity": 3,
        "status": "available", "estimated_response_time": 20, "version": 1, **overrides,
    }


def assignment(iid="incident-a", rid="resource-a", **overrides):
    return {
        "incident_id": iid, "resource_id": rid, "capacity": 2,
        "start_at": "2026-10-11T12:00:00Z", "end_at": "2026-10-11T13:00:00Z", **overrides,
    }


def assert_plan_invariants(assignments, incidents, resources):
    """Oracle independent of detect_constraints: capacities, capability and windows."""
    lookup = {row["id"]: row for row in resources}
    incidents_by_id = {row["id"]: row for row in incidents}
    allowed = {"flood": {"rescue"}, "fire": {"fire"}, "medical": {"medical"}, "infrastructure": {"rescue", "logistics"}}
    for row in assignments:
        assert isinstance(row["capacity"], int) and row["capacity"] > 0
        allocated = lookup[row["resource_id"]]
        assert allocated["status"] == "available"
        assert row["capacity"] <= allocated["available_capacity"] <= allocated["capacity"]
        assert allocated["type"] in allowed[incidents_by_id[row["incident_id"]]["category"]]
        assert datetime.fromisoformat(row["start_at"]) < datetime.fromisoformat(row["end_at"])
    for first, second in combinations(assignments, 2):
        if first["resource_id"] == second["resource_id"]:
            assert first["end_at"] <= second["start_at"] or second["end_at"] <= first["start_at"]
    for row in incidents:
        if row["status"] == "open":
            supplied = sum(a["capacity"] for a in assignments if a["incident_id"] == row["id"])
            assert supplied >= (row["people_at_risk"] + 99) // 100


def test_priority_has_documented_units_weights_and_direction():
    case = incident(people_at_risk=250, damage_severity=5, response_time_minutes=60,
                    resource_conflict_factor=0, reassignment_friction=0)
    result = score_incident(case, [resource()], [])
    factors = {factor["key"]: factor for factor in result["priority_factors"]}
    # Three positive factors at 0.5 with weights .35 + .25 + .20, denominator .8.
    assert result["priority_score"] == 50
    assert factors["people"]["raw"] == 250
    assert factors["people"]["normalized"] == 0.5
    assert factors["damage"]["contribution"] == 15.625
    assert factors["response"]["contribution"] == 12.5
    for field, new_value in (("people_at_risk", 500), ("damage_severity", 10), ("response_time_minutes", 120)):
        assert score_incident({**case, field: new_value}, [resource()], [])["priority_score"] > 50
    for field in ("resource_conflict_factor", "reassignment_friction"):
        assert score_incident({**case, field: 1}, [resource()], [])["priority_score"] < 50


@pytest.mark.parametrize("score,band", [(0, "low"), (30, "medium"), (55, "high"), (75, "critical"), (100, "critical")])
def test_priority_band_boundaries(score, band):
    case = incident(people_at_risk=score * 5, damage_severity=score / 10, response_time_minutes=score * 1.2,
                    resource_conflict_factor=0, reassignment_friction=0)
    result = score_incident(case, [resource()], [])
    assert result["priority_score"] == score
    assert result["priority_band"] == band


def test_unknown_measurements_remain_explicit_and_reduce_confidence():
    case = incident(people_at_risk=None, damage_severity=None, response_time_minutes=None)
    result = score_incident(case, [], [])
    factors = {factor["key"]: factor for factor in result["priority_factors"]}
    for factor in ("people", "damage", "response", "conflict"):
        assert factors[factor]["normalized"] is None
        assert factors[factor]["contribution"] is None
    assert result["people_at_risk"] is None and result["damage_severity"] is None
    assert result["confidence"] < score_incident(incident(), [resource()], [])["confidence"]
    assert any("unknown" in warning.lower() for warning in result["warnings"])
    infeasible = plan([case], [resource()], [], WEATHER)
    assert infeasible["status"] == "infeasible"
    assert any(row["type"] == "missing_inputs" for row in infeasible["conflicts"])


CONSTRAINT_CASES = [
    ("valid assignment", {}, {}, {}, {}, None),
    ("capacity overrun", {}, {}, {"capacity": 4}, {}, "capacity"),
    ("zero allocation", {}, {}, {"capacity": 0}, {}, "capacity"),
    ("fractional allocation", {}, {}, {"capacity": 2.5}, {}, "capacity"),
    ("resource unavailable", {}, {"status": "unavailable"}, {}, {}, "unavailable"),
    ("wrong capability", {}, {"type": "medical"}, {}, {}, "eligibility"),
    ("weather access blocked", {}, {}, {}, {"access_blocked": True}, "access"),
    ("incident access blocked", {"access_blocked": True}, {}, {}, {}, "access"),
    ("missing affected people", {"people_at_risk": None}, {}, {}, {}, "missing_inputs"),
    ("missing damage", {"damage_severity": None}, {}, {}, {}, "missing_inputs"),
    ("unmet demand", {"people_at_risk": 400}, {}, {}, {}, "capacity"),
    ("reversed time window", {}, {}, {"end_at": "2026-10-11T11:00:00Z"}, {}, "missing_inputs"),
    ("timezone missing", {}, {}, {"start_at": "2026-10-11T12:00:00"}, {}, "missing_inputs"),
    ("unknown resource capacity", {}, {"capacity": None, "available_capacity": None}, {}, {}, "missing_inputs"),
]


@pytest.mark.parametrize("label,incident_changes,resource_changes,assignment_changes,weather_changes,expected", CONSTRAINT_CASES, ids=[case[0] for case in CONSTRAINT_CASES])
def test_labeled_constraint_cases(label, incident_changes, resource_changes, assignment_changes, weather_changes, expected):
    conflicts = detect_constraints([assignment(**assignment_changes)], [incident(**incident_changes)],
                                   [resource(**resource_changes)], [], {**WEATHER, **weather_changes})
    if expected is None:
        assert conflicts == [], label
    else:
        assert expected in {row["type"] for row in conflicts}, label


def test_exclusive_reservations_overlap_but_allow_half_open_adjacent_windows():
    first = assignment()
    second = assignment(iid="incident-b", start_at="2026-10-11T12:30:00Z", end_at="2026-10-11T13:30:00Z")
    cases = [incident(), incident("incident-b")]
    assert "exclusive" in {row["type"] for row in detect_constraints([first, second], cases, [resource()], [], WEATHER)}
    adjacent = {**second, "start_at": first["end_at"], "end_at": "2026-10-11T14:00:00Z"}
    assert detect_constraints([first, adjacent], cases, [resource()], [], WEATHER) == []
    reservation = {**first, "mission_id": "approved-prior-mission"}
    assert "exclusive" in {row["type"] for row in detect_constraints([second], [cases[1]], [resource()], [reservation], WEATHER)}
    invalid = {**reservation, "end_at": None}
    assert "exclusive" in {row["type"] for row in detect_constraints([adjacent], [cases[1]], [resource()], [invalid], WEATHER)}


def test_labeled_urgency_ranking_and_feasible_alternative_invariants():
    cases = [
        incident("lower", people_at_risk=100, damage_severity=2, response_time_minutes=15),
        incident("highest", people_at_risk=500, damage_severity=10, response_time_minutes=120),
        incident("middle", people_at_risk=300, damage_severity=6, response_time_minutes=60),
    ]
    resources = [resource("rescue-1", capacity=10, available_capacity=10), resource("rescue-2", capacity=10, available_capacity=10), resource("rescue-3", capacity=10, available_capacity=10)]
    result = plan(cases, resources, [], WEATHER)
    assert [row["incident_id"] for row in result["rationale_details"][ "ranked_incidents"]] == ["highest", "middle", "lower"]
    assert result["status"] == "feasible"
    assert_plan_invariants(result["assignments"], cases, resources)
    alternatives = [row for row in result["alternatives"] if row["status"] == "feasible"]
    assert alternatives
    for candidate in alternatives:
        assert candidate["assignments"] != result["assignments"]
        assert candidate["trade_off"]
        assert_plan_invariants(candidate["assignments"], cases, resources)


def test_plan_is_repeatable_does_not_mutate_inputs_and_staggers_scarce_resources():
    cases = [incident("first"), incident("second", people_at_risk=100)]
    resources = [resource()]
    original = deepcopy((cases, resources, WEATHER, DEFAULT_WEIGHTS))
    first = plan(cases, resources, [], WEATHER)
    assert first == plan(cases, resources, [], WEATHER)
    assert (cases, resources, WEATHER, DEFAULT_WEIGHTS) == original
    assert first["status"] == "feasible"
    assert first["rationale_details"][ "strategy"] == "sequential"
    assert_plan_invariants(first["assignments"], cases, resources)


def test_infeasible_resource_shortage_is_not_fabricated():
    case = incident(people_at_risk=500)
    result = plan([case], [resource(capacity=1, available_capacity=1)], [], WEATHER)
    assert result["status"] == "infeasible"
    assert any(row["type"] == "capacity" for row in result["conflicts"])
    assert not any(row["status"] == "feasible" for row in result["alternatives"])
