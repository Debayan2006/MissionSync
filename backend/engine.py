"""Deterministic, provider-independent coordination for the synthetic prototype.

People are normalized against 500 people, damage is a 0..10 scale, and delay is
normalized against 120 minutes (a longer delay increases urgency). Conflict and
reassignment friction are 0..1 penalties. Scores use the sum of positive weights
as their fixed denominator; missing measurements contribute nothing and remain
explicitly unknown. One resource capacity unit supports 100 people during one
60-minute response window. Resources are exclusive during overlapping windows.

The caller supplies ``weather.planning_start_at`` to make a live planning snapshot
reproducible. Without a timestamp the fixed synthetic epoch is used, never a hidden
wall-clock dependency. No function mutates its inputs or dispatches a resource.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil, isfinite
from typing import Any


DEFAULT_WEIGHTS = {"people": 0.35, "damage": 0.25, "response": 0.20, "conflict": -0.10, "friction": -0.10}
CLOSED_STATUSES = {"resolved", "closed", "cancelled", "dismissed"}
CATEGORY_TYPES = {
    "flood": {"rescue"}, "rescue": {"rescue"}, "fire": {"fire"},
    "medical": {"medical"}, "infrastructure": {"logistics", "rescue"},
    "earthquake": {"rescue"}, "storm": {"rescue", "logistics"},
}
SYNTHETIC_EPOCH = "2026-10-11T12:00:00Z"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if isfinite(value) else None


def _unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Timezone-less assignments are ambiguous and must fail validation.
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _window(assignment: dict) -> tuple[datetime, datetime] | None:
    start, end = _parse_time(assignment.get("start_at")), _parse_time(assignment.get("end_at"))
    return (start, end) if start is not None and end is not None and start < end else None


def _overlaps(a: dict, b: dict) -> bool:
    first, second = _window(a), _window(b)
    # Invalid existing reservations fail closed rather than making a resource free.
    return first is None or second is None or (first[0] < second[1] and second[0] < first[1])


def _eligible(incident: dict, resource: dict) -> bool:
    types = CATEGORY_TYPES.get(str(incident.get("category", "")).lower(), set())
    capabilities = resource.get("capabilities") or [resource.get("type")]
    return bool(types.intersection(str(value).lower() for value in capabilities))


def _capacity(resource: dict) -> float | None:
    total = _number(resource.get("capacity"))
    available = _number(resource.get("available_capacity", resource.get("capacity")))
    if total is None or available is None or total < 0 or available < 0:
        return None
    return min(total, available)


def _demand(incident: dict) -> int | None:
    people = _number(incident.get("people_at_risk"))
    return ceil(people / 100) if people is not None and people >= 0 else None


def _response(incident: dict, resources: list[dict]) -> float | None:
    value = _number(incident.get("response_time_minutes", incident.get("estimated_response_time")))
    if value is not None and value >= 0:
        return value
    # A resource estimate is a declared estimate, not a replacement observation.
    eligible_delays = [
        delay for resource in resources
        if _eligible(incident, resource) and resource.get("status") == "available"
        and (delay := _number(resource.get("estimated_response_time"))) is not None and delay >= 0
    ]
    return min(eligible_delays) if eligible_delays else None


def _active(incidents: list[dict]) -> list[dict]:
    return [incident for incident in incidents if incident.get("status", "open") not in CLOSED_STATUSES]


def score_incident(incident: dict, resources: list[dict], assignments: list[dict], weights: dict | None = None) -> dict:
    """Return an enriched copy with normalized factors, contributions and uncertainty."""
    configured = dict(DEFAULT_WEIGHTS)
    warnings = []
    for name, value in (weights or {}).items():
        if name in configured:
            valid = _number(value)
            if valid is None:
                warnings.append(f"Invalid {name} weight; the documented default was retained.")
            else:
                configured[name] = valid
    denominator = sum(max(0.0, weight) for weight in configured.values())
    if denominator <= 0:
        denominator = 1.0
        warnings.append("No positive scoring weights; ranking cannot represent urgency.")

    people = _number(incident.get("people_at_risk"))
    damage = _number(incident.get("damage_severity"))
    response = _response(incident, resources)
    eligible = [resource for resource in resources if _eligible(incident, resource)]
    demand = _demand(incident)
    known_capacity = all(_capacity(resource) is not None and resource.get("status") in {"available", "assigned", "unavailable", "maintenance", "offline", "reserved"} for resource in eligible)
    conflict = _number(incident.get("resource_conflict_factor"))
    if conflict is None and demand is not None and known_capacity:
        reserved = {assignment.get("resource_id") for assignment in assignments}
        free_supply = sum(_capacity(resource) or 0 for resource in eligible if resource.get("status") == "available" and resource.get("id") not in reserved)
        conflict = _unit((demand - free_supply) / demand) if demand else 0.0
    friction = _number(incident.get("reassignment_friction"))
    if friction is None and known_capacity:
        reserved = {assignment.get("resource_id") for assignment in assignments}
        total_capacity = sum(_number(resource.get("capacity")) or 0 for resource in eligible)
        occupied = sum(_number(resource.get("capacity")) or 0 for resource in eligible if resource.get("id") in reserved or resource.get("status") in {"assigned", "reserved"})
        friction = _unit(occupied / total_capacity) if total_capacity > 0 else 0.0

    definitions = {
        "people": ("People at risk", people if people is not None and people >= 0 else None, 500.0, "people"),
        "damage": ("Damage severity", damage if damage is not None and 0 <= damage <= 10 else None, 10.0, "0–10 severity"),
        "response": ("Response delay", response, 120.0, "minutes; longer means more urgent"),
        "conflict": ("Unmet capacity", conflict if conflict is not None and 0 <= conflict <= 1 else None, 1.0, "fraction of required capacity"),
        "friction": ("Reassignment friction", friction if friction is not None and 0 <= friction <= 1 else None, 1.0, "fraction of relevant resources reserved"),
    }
    factors = {}
    contribution_total = 0.0
    for name, (label, raw, scale, units) in definitions.items():
        normalized = _unit(raw / scale) if raw is not None else None
        contribution = normalized * configured[name] / denominator * 100 if normalized is not None else None
        if contribution is None:
            warnings.append(f"Unknown {label.lower()}; this contribution is omitted, not assumed zero.")
        else:
            contribution_total += contribution
        factors[name] = {"label": label, "raw": raw, "normalized": normalized, "weight": configured[name], "contribution": round(contribution, 3) if contribution is not None else None, "units": units, "known": raw is not None}
    known_weight = sum(abs(configured[name]) for name, factor in factors.items() if factor["known"])
    total_weight = sum(abs(weight) for weight in configured.values())
    confidence = known_weight / total_weight if total_weight else 0.0
    reliability = _number(incident.get("source_reliability"))
    if reliability is not None and 0 <= reliability <= 1:
        confidence *= reliability
    if _number(incident.get("response_time_minutes", incident.get("estimated_response_time"))) is None and response is not None:
        warnings.append("Response factor uses an eligible resource's declared estimate; no incident response observation was supplied.")
    score = round(max(0.0, min(100.0, contribution_total)), 2)
    band = "critical" if score >= 75 else "high" if score >= 55 else "medium" if score >= 30 else "low"
    factor_array = [{"key": name, **factor, "value": factor["raw"], "unknown": not factor["known"]} for name, factor in factors.items()]
    return {**incident, "priority_score": score, "priority_band": band, "priority_factors": factor_array, "warnings": warnings, "confidence": round(confidence, 3), "confidence_basis": "Known weighted factors, multiplied by source reliability when supplied"}


def _access_known(weather: dict) -> bool:
    return isinstance(weather.get("access_blocked"), bool) or weather.get("access") in {"open", "restricted", "blocked", "closed"}


def _access_blocked(incident: dict, resource: dict | None, weather: dict) -> bool:
    if weather.get("access_blocked") is True or weather.get("access") in {"blocked", "closed"}:
        return True
    if incident.get("access_blocked") is True or incident.get("id") in (weather.get("blocked_incident_ids") or []):
        return True
    return resource is not None and resource.get("type") in (weather.get("blocked_resource_types") or [])


def _missing_inputs(incident: dict, resources: list[dict], weather: dict) -> list[str]:
    missing = []
    if _demand(incident) is None:
        missing.append("people_at_risk")
    damage = _number(incident.get("damage_severity"))
    if damage is None or not 0 <= damage <= 10:
        missing.append("damage_severity")
    if _response(incident, resources) is None:
        missing.append("response_time_minutes or eligible resource response estimate")
    if not _access_known(weather):
        missing.append("weather access state")
    if str(incident.get("category", "")).lower() not in CATEGORY_TYPES:
        missing.append("supported incident category")
    return missing


def detect_constraints(assignments: list[dict], incidents: list[dict], resources: list[dict], existing_assignments: list[dict] | None = None, weather: dict | None = None) -> list[dict]:
    """Validate candidate assignments against current capacity and reservation state.

    Intervals are half-open: a resource can start a new task exactly when another
    ends. Missing, malformed, or timezone-less reservation windows fail closed.
    """
    existing_assignments, weather = existing_assignments or [], weather or {}
    incidents_by_id = {incident.get("id"): incident for incident in incidents}
    resources_by_id = {resource.get("id"): resource for resource in resources}
    conflicts: list[dict] = []

    def add(kind: str, message: str, **fields: Any) -> None:
        entry = {"type": kind, "message": message, **fields}
        if entry not in conflicts:
            conflicts.append(entry)

    for incident in _active(incidents):
        missing = _missing_inputs(incident, resources, weather)
        if missing:
            add("missing_inputs", f"{incident.get('title', incident.get('id'))}: required planning inputs are unknown.", incident_id=incident.get("id"), fields=missing)
        if _access_blocked(incident, None, weather):
            add("access", "Current weather/terrain blocks access to this incident.", incident_id=incident.get("id"))

    for index, assignment in enumerate(assignments):
        resource_id, incident_id = assignment.get("resource_id"), assignment.get("incident_id")
        resource, incident = resources_by_id.get(resource_id), incidents_by_id.get(incident_id)
        amount = _number(assignment.get("capacity"))
        if resource is None or incident is None:
            add("missing_inputs", "Assignment references an unknown incident or resource.", incident_id=incident_id, resource_id=resource_id)
            continue
        if _window(assignment) is None:
            add("missing_inputs", "Assignment requires ordered timezone-aware start_at/end_at timestamps.", incident_id=incident_id, resource_id=resource_id)
        capacity = _capacity(resource)
        if capacity is None:
            add("missing_inputs", "Resource capacity is unknown.", resource_id=resource_id)
        elif amount is None or amount <= 0 or not amount.is_integer() or amount > capacity:
            add("capacity", "Assignment exceeds known available capacity or has an invalid capacity quantity.", incident_id=incident_id, resource_id=resource_id, required=amount, available=capacity)
        if resource.get("status") != "available":
            add("unavailable", "Resource is not available for a new proposal.", resource_id=resource_id, status=resource.get("status"))
        if not _eligible(incident, resource):
            add("eligibility", "Resource capabilities do not match the incident category.", incident_id=incident_id, resource_id=resource_id)
        if _access_blocked(incident, resource, weather):
            add("access", "Weather/terrain constraints prevent this assignment.", incident_id=incident_id, resource_id=resource_id)
        for other in assignments[index + 1:] + existing_assignments:
            if other.get("resource_id") == resource_id and _overlaps(assignment, other):
                add("exclusive", "Exclusive resource is double-booked during overlapping response windows.", resource_id=resource_id, incident_ids=sorted({str(incident_id), str(other.get("incident_id"))}), existing_mission_id=other.get("mission_id"))

    for incident in _active(incidents):
        demand = _demand(incident)
        provided = sum(_number(assignment.get("capacity")) or 0 for assignment in assignments if assignment.get("incident_id") == incident.get("id"))
        if demand is not None and provided < demand:
            add("capacity", "Incident has unmet required response capacity.", incident_id=incident.get("id"), required=demand, assigned=provided)
    return conflicts


def _build(incidents: list[dict], resources: list[dict], existing: list[dict], weather: dict, start: datetime, sequential: bool, reverse_resources: bool = False) -> list[dict]:
    candidates = sorted(resources, key=lambda resource: (resource.get("type") == "rescue", _number(resource.get("estimated_response_time")) if _number(resource.get("estimated_response_time")) is not None else float("inf"), str(resource.get("id"))), reverse=reverse_resources)
    assignments: list[dict] = []
    cursor = start
    for incident in incidents:
        demand = _demand(incident)
        if demand is None or _missing_inputs(incident, resources, weather) or _access_blocked(incident, None, weather):
            continue
        incident_start = cursor if sequential else start
        if sequential:
            eligible_existing = [reservation for reservation in existing if any(resource.get("id") == reservation.get("resource_id") and _eligible(incident, resource) for resource in candidates)]
            for reservation in sorted(eligible_existing, key=lambda item: (_window(item) or (start, start))[0]):
                window = _window(reservation)
                if window is not None and incident_start < window[1] and window[0] < incident_start + timedelta(minutes=60):
                    incident_start = max(incident_start, window[1])
        incident_end = incident_start + timedelta(minutes=60)
        remaining = demand
        for resource in candidates:
            capacity = _capacity(resource)
            if remaining <= 0:
                break
            if resource.get("status") != "available" or capacity is None or capacity < 1 or not _eligible(incident, resource) or _access_blocked(incident, resource, weather):
                continue
            assignment = {"incident_id": incident["id"], "resource_id": resource["id"], "capacity": min(remaining, int(capacity)), "start_at": _iso(incident_start), "end_at": _iso(incident_end)}
            if any(other.get("resource_id") == resource["id"] and _overlaps(assignment, other) for other in assignments + existing):
                continue
            assignments.append(assignment)
            remaining -= assignment["capacity"]
        if sequential:
            cursor = incident_end
    return assignments


def plan(incidents: list[dict], resources: list[dict], existing_assignments: list[dict], weather: dict, weights: dict | None = None) -> dict:
    """Return a validated complete proposal or an explicitly infeasible result.

    Try concurrent response first, then non-overlapping incident windows. A
    sequential plan may delay lower-priority incidents and exposes that trade-off.
    Infrastructure may use rescue capability as a declared fallback; all other
    category capability requirements remain strict.
    """
    ranked = sorted((score_incident(incident, resources, existing_assignments, weights) for incident in _active(incidents)), key=lambda incident: (-incident["priority_score"], str(incident.get("id"))))
    start = _parse_time(weather.get("planning_start_at")) or _parse_time(weather.get("updated_at")) or _parse_time(SYNTHETIC_EPOCH)
    assert start is not None
    possibilities = []
    for sequential, reverse_resources in ((False, False), (False, True), (True, False), (True, True)):
        assignments = _build(ranked, resources, existing_assignments, weather, start, sequential, reverse_resources)
        conflicts = detect_constraints(assignments, ranked, resources, existing_assignments, weather)
        possibilities.append({"assignments": assignments, "conflicts": conflicts, "status": "infeasible" if conflicts else "feasible", "strategy": "sequential" if sequential else "concurrent"})
    chosen = next((candidate for candidate in possibilities if candidate["status"] == "feasible"), possibilities[0])
    warnings = [warning for incident in ranked for warning in incident["warnings"]]
    if chosen["strategy"] == "sequential":
        warnings.append("Simultaneous coverage is unavailable; lower-ranked incidents start in later non-overlapping 60-minute windows.")
    if chosen["status"] == "infeasible":
        warnings.append("No complete feasible plan found. Partial candidate assignments require revision and cannot be approved.")
    if not ranked:
        warnings.append("There are no open incidents requiring a response.")
    if not _parse_time(weather.get("planning_start_at")):
        warnings.append("No planning_start_at supplied; timestamps use weather.updated_at or the fixed synthetic epoch.")

    alternatives = []
    seen = {tuple(sorted((assignment["incident_id"], assignment["resource_id"], assignment["capacity"], assignment["start_at"], assignment["end_at"]) for assignment in chosen["assignments"]))}
    for candidate in possibilities:
        signature = tuple(sorted((assignment["incident_id"], assignment["resource_id"], assignment["capacity"], assignment["start_at"], assignment["end_at"]) for assignment in candidate["assignments"]))
        if candidate["status"] == "feasible" and signature not in seen:
            seen.add(signature)
            alternatives.append({"id": f"alternative-{len(alternatives) + 1}", "label": "Staggered response" if candidate["strategy"] == "sequential" else "Alternate resource allocation", "status": "feasible", "assignments": candidate["assignments"], "conflicts": [], "trade_off": "Resources serve incidents in priority order with later starts." if candidate["strategy"] == "sequential" else "Uses a different eligible resource allocation; response estimates may differ.", "rationale": "Every assignment independently satisfies capacity, eligibility, availability, access and non-overlap constraints."})
    if not alternatives:
        warnings.append("No distinct feasible alternative found. " + ("Additional eligible resources, restored access, or complete input data are needed." if chosen["conflicts"] else "Current inputs provide only one distinct feasible assignment schedule."))

    rationale = {
        "summary": "Incidents ranked by normalized urgency; every assignment checked for eligibility, capacity, availability, access and reservation overlap.",
        "strategy": chosen["strategy"],
        "capacity_rule": "One resource capacity unit per 100 people, rounded up; one exclusive 60-minute response window per incident.",
        "category_fallback": "Infrastructure incidents may use rescue capability when logistics resources are insufficient.",
        "normalization": {"people": "people / 500", "damage": "severity / 10", "response": "delay minutes / 120; longer delay increases urgency", "conflict": "unmet required capacity / required capacity", "friction": "fraction of eligible capacity already reserved"},
        "ranked_incidents": [{"incident_id": incident.get("id"), "priority_score": incident["priority_score"], "priority_band": incident["priority_band"], "confidence": incident["confidence"], "factors": incident["priority_factors"], "evidence": incident.get("evidence", []), "warnings": incident["warnings"]} for incident in ranked],
        "assumptions": ["Synthetic decision support only; assignments are proposals until human approval.", "Response windows are half-open UTC intervals.", "Missing observations remain unknown; no model or external provider is required."],
    }
    narrative = rationale["summary"] + " " + rationale["capacity_rule"]
    if chosen["strategy"] == "sequential":
        narrative += " Lower-priority incidents are served in subsequent response windows to prevent exclusive-resource overlap."
    if chosen["conflicts"]:
        narrative += " This candidate is infeasible; the listed hard constraints must be resolved before approval."
    return {"assignments": chosen["assignments"], "conflicts": chosen["conflicts"], "alternatives": alternatives, "rationale": narrative, "rationale_details": rationale, "warnings": list(dict.fromkeys(warnings)), "status": chosen["status"], "priority_score": max((incident["priority_score"] for incident in ranked), default=0.0)}
