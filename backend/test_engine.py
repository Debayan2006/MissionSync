"""Labeled constraint and normalization cases for the deterministic coordinator."""

from copy import deepcopy
import unittest

from backend.engine import detect_constraints, plan, score_incident


START = "2026-10-11T12:00:00Z"
END = "2026-10-11T13:00:00Z"
WEATHER = {"access_blocked": False, "planning_start_at": START}


def incident(identifier="flood-1", **changes):
    return {"id": identifier, "title": "Synthetic flood", "category": "flood", "people_at_risk": 200, "damage_severity": 8, "response_time_minutes": 60, "status": "open", **changes}


def resource(identifier="rescue-1", **changes):
    return {"id": identifier, "type": "rescue", "capacity": 6, "available_capacity": 6, "status": "available", "estimated_response_time": 20, **changes}


def assignment(incident_id="flood-1", resource_id="rescue-1", **changes):
    return {"incident_id": incident_id, "resource_id": resource_id, "capacity": 2, "start_at": START, "end_at": END, **changes}


def factor(result, key):
    return next(value for value in result["priority_factors"] if value["key"] == key)


class RiskTests(unittest.TestCase):
    def test_full_normalization_and_penalty_direction(self):
        full = incident(people_at_risk=500, damage_severity=10, response_time_minutes=120, resource_conflict_factor=0, reassignment_friction=0)
        result = score_incident(full, [resource()], [], {})
        self.assertEqual(result["priority_score"], 100)
        self.assertEqual(result["priority_band"], "critical")
        penalized = score_incident({**full, "resource_conflict_factor": 1, "reassignment_friction": 1}, [resource()], [], {})
        self.assertEqual(penalized["priority_score"], 75)
        self.assertLess(penalized["priority_score"], result["priority_score"])

    def test_longer_response_delay_increases_priority(self):
        short = score_incident(incident(response_time_minutes=10), [resource()], [], {})
        long = score_incident(incident(response_time_minutes=100), [resource()], [], {})
        self.assertGreater(long["priority_score"], short["priority_score"])
        self.assertEqual(factor(long, "response")["units"], "minutes; longer means more urgent")

    def test_unknown_data_stays_unknown_and_has_lower_completeness(self):
        incomplete = incident(people_at_risk=None, damage_severity=None, response_time_minutes=None)
        result = score_incident(incomplete, [], [], {})
        self.assertIsNone(result["people_at_risk"])
        self.assertIsNone(factor(result, "people")["normalized"])
        self.assertIsNone(factor(result, "people")["contribution"])
        self.assertLess(result["confidence"], 1)
        self.assertTrue(any("omitted" in warning for warning in result["warnings"]))

    def test_resource_estimate_is_explicit_and_does_not_rewrite_observation(self):
        result = score_incident(incident(response_time_minutes=None), [resource(estimated_response_time=35)], [], {})
        self.assertIsNone(result["response_time_minutes"])
        self.assertEqual(factor(result, "response")["raw"], 35)
        self.assertTrue(any("declared estimate" in warning for warning in result["warnings"]))

    def test_configurable_weights_and_clamping(self):
        result = score_incident(incident(people_at_risk=250), [resource()], [], {"people": 1, "damage": 0, "response": 0, "conflict": 0, "friction": 0})
        self.assertEqual(result["priority_score"], 50)
        capped = score_incident(incident(people_at_risk=50000), [resource()], [], {"people": 1, "damage": 0, "response": 0, "conflict": 0, "friction": 0})
        self.assertEqual(capped["priority_score"], 100)

    def test_reservations_create_unmet_capacity_and_friction(self):
        result = score_incident(incident(), [resource()], [assignment()], {})
        self.assertEqual(factor(result, "conflict")["normalized"], 1)
        self.assertEqual(factor(result, "friction")["normalized"], 1)

    def test_assigned_inventory_zero_available_capacity_retains_friction(self):
        assigned = resource(status="assigned", available_capacity=0)
        result = score_incident(incident(), [assigned], [assignment()], {})
        self.assertEqual(factor(result, "friction")["normalized"], 1)
        self.assertEqual(factor(result, "conflict")["normalized"], 1)
        mixed = score_incident(incident(), [assigned, resource("rescue-2")], [assignment()], {})
        self.assertEqual(factor(mixed, "friction")["normalized"], 0.5)
        self.assertEqual(factor(mixed, "conflict")["normalized"], 0)


class ConstraintTests(unittest.TestCase):
    def kinds(self, assignments, incidents=None, resources=None, existing=None, weather=None):
        return {conflict["type"] for conflict in detect_constraints(assignments, incidents or [incident()], resources or [resource()], existing or [], WEATHER if weather is None else weather)}

    def test_valid_assignment(self):
        self.assertEqual(self.kinds([assignment()]), set())

    def test_capacity_overrun_and_uncovered_demand(self):
        self.assertIn("capacity", self.kinds([assignment(capacity=7)]))
        self.assertIn("capacity", self.kinds([assignment(capacity=1)]))

    def test_exclusive_overlap_and_half_open_boundaries(self):
        overlap = assignment("other", start_at="2026-10-11T12:30:00Z", end_at="2026-10-11T13:30:00Z")
        self.assertIn("exclusive", self.kinds([assignment()], existing=[overlap]))
        adjacent = assignment("other", start_at=END, end_at="2026-10-11T14:00:00Z")
        self.assertNotIn("exclusive", self.kinds([assignment()], existing=[adjacent]))

    def test_candidate_double_booking(self):
        incidents = [incident(), incident("flood-2")]
        self.assertIn("exclusive", self.kinds([assignment(), assignment("flood-2")], incidents=incidents))

    def test_unavailable_access_missing_and_category_constraints(self):
        self.assertIn("unavailable", self.kinds([assignment()], resources=[resource(status="unavailable")]))
        self.assertIn("access", self.kinds([assignment()], weather={**WEATHER, "access_blocked": True}))
        self.assertIn("missing_inputs", self.kinds([assignment()], incidents=[incident(people_at_risk=None)]))
        self.assertIn("missing_inputs", self.kinds([assignment()], weather={}))
        self.assertIn("eligibility", self.kinds([assignment()], resources=[resource(type="medical")]))

    def test_malformed_reservation_fails_closed(self):
        self.assertIn("exclusive", self.kinds([assignment()], existing=[assignment("old", start_at="unknown")]))
        self.assertIn("missing_inputs", self.kinds([assignment(start_at="2026-10-11T12:00:00")]))


class PlannerTests(unittest.TestCase):
    def test_plan_validates_every_assignment_and_is_repeatable(self):
        incidents = [incident(), incident("medical-1", category="medical", people_at_risk=90)]
        resources = [resource(), resource("ambulance", type="medical", capacity=2, available_capacity=2)]
        original = deepcopy((incidents, resources, WEATHER))
        proposal = plan(incidents, resources, [], WEATHER, {})
        self.assertEqual(proposal["status"], "feasible")
        self.assertEqual(detect_constraints(proposal["assignments"], incidents, resources, [], WEATHER), [])
        self.assertEqual(proposal, plan(incidents, resources, [], WEATHER, {}))
        self.assertEqual((incidents, resources, WEATHER), original)

    def test_sequential_plan_resolves_shared_resource_and_warns_of_delay(self):
        incidents = [incident(), incident("flood-2", people_at_risk=300)]
        resources = [resource()]
        result = plan(incidents, resources, [], WEATHER, {})
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(result["rationale_details"]["strategy"], "sequential")
        self.assertNotEqual(result["assignments"][0]["start_at"], result["assignments"][1]["start_at"])
        self.assertEqual(detect_constraints(result["assignments"], incidents, resources, [], WEATHER), [])
        self.assertTrue(any("lower-ranked" in warning for warning in result["warnings"]))

    def test_insufficient_capacity_is_explicitly_infeasible(self):
        result = plan([incident(people_at_risk=900)], [resource()], [], WEATHER, {})
        self.assertEqual(result["status"], "infeasible")
        self.assertTrue(result["conflicts"])
        self.assertTrue(all(alternative["status"] == "infeasible" for alternative in result["alternatives"]))

    def test_blocked_access_and_unknown_observations_never_get_assigned(self):
        blocked = plan([incident()], [resource()], [], {**WEATHER, "access_blocked": True}, {})
        unknown = plan([incident(people_at_risk=None)], [resource()], [], WEATHER, {})
        for result in [blocked, unknown]:
            self.assertEqual(result["status"], "infeasible")
            self.assertEqual(result["assignments"], [])

    def test_assigned_resource_is_never_reused_in_future_sequence(self):
        result = plan([incident()], [resource(status="assigned", available_capacity=0)], [], WEATHER, {})
        self.assertEqual(result["status"], "infeasible")
        self.assertEqual(result["assignments"], [])

    def test_existing_booking_moves_sequential_plan_after_booking_end(self):
        reservation = assignment("approved-other", start_at="2026-10-11T12:30:00Z", end_at="2026-10-11T14:00:00Z")
        result = plan([incident()], [resource()], [reservation], WEATHER, {})
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(result["assignments"][0]["start_at"], reservation["end_at"])

    def test_alternatives_are_distinct_and_validate(self):
        incidents = [incident(), incident("flood-2")]
        resources = [resource(), resource("rescue-2")]
        result = plan(incidents, resources, [], WEATHER, {})
        primary = {tuple(sorted(value.items())) for value in result["assignments"]}
        feasible = [alternative for alternative in result["alternatives"] if alternative["status"] == "feasible"]
        self.assertTrue(feasible)
        for alternative in feasible:
            self.assertEqual(detect_constraints(alternative["assignments"], incidents, resources, [], WEATHER), [])
            self.assertNotEqual({tuple(sorted(value.items())) for value in alternative["assignments"]}, primary)

    def test_resolved_incidents_do_not_require_resources(self):
        result = plan([incident(status="resolved")], [], [], WEATHER, {})
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(result["assignments"], [])


if __name__ == "__main__":
    unittest.main()
