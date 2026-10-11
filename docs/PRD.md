SYNAPSE 1.0
MissionSync
FINAL PRODUCT REQUIREMENTS DOCUMENT
Multi-Agent Coordination Platform for Defence & Emergency Response
Team: Synaptic Surge
Institute: Institute of Engineering and Management (IEM), Kolkata
Problem Statement: PS-11
Version: 1.0 | Status: Final implementation specification | Date: 11 October 2026

Document Control
Item
Definition
Product
SYNAPSE 1.0 — MissionSync
Primary users
Incident commanders, operations analysts, resource coordinators, demonstrators/evaluators
Product type
Interactive, simulation-based decision-support application
Primary outcome
A shared operational picture and conflict-aware, human-approved simulated response plan
Scope boundary
No autonomous real-world dispatch, drone control, weapon control, or emergency-service command

1. Executive Summary
MissionSync coordinates fragmented emergency-response information by combining synthetic or configured data streams, specialized analytical agents, a shared operational state, a deterministic coordination engine, and a human approval workflow. It ranks incidents, checks resource feasibility, detects competing assignments, generates alternatives, and updates the dashboard when new events arrive. The prototype must be an end-to-end working application—not a static dashboard or a collection of independent AI demos.
1.1 Product principles
Shared state: all agents and the planner use a consistent, versioned operational state.
Event-driven updates: relevant analyses and planning are triggered when incidents, evidence, weather, or resources change.
Constraint-first planning: hard constraints are validated deterministically; AI-generated text cannot override them.
Explainability: show factors, evidence references, confidence, warnings, and reasons for changes.
Human control: every mission is a proposal until a permitted user approves it.
Resilience: synthetic data and deterministic fallbacks keep the core demo usable without paid external services.
Truthful status: distinguish synthetic data, externally sourced data, model inference, and unavailable information.
2. Problem and Proposed Solution
Emergency coordination can break down when drone or satellite imagery, ground reports, weather information, terrain constraints, and resource inventories are fragmented. Standalone dashboards display information without necessarily reconciling competing resource demands; report-analysis tools may not maintain current resource assignments; and fixed rules may not handle conflicting or incomplete evidence.
MissionSync implements the closed loop: Ingest → Analyze → Prioritize → Detect Conflicts → Recommend → Human Review/Approval → Monitor. A new incident or resource change must update persisted state, trigger affected analyses, re-evaluate rankings and assignments, and publish a revised proposal.
3. Goals, Non-Goals, and Success Definition
3.1 Goals
Provide one operational dashboard for incidents, resources, agent runs, mission proposals, and audit activity.
Support incident ingestion, search, filtering, detail inspection, evidence review, and map visualization.
Implement six modular logical agents: Vision, Incident, Weather/Terrain, Resource, Risk/Priority, and Mission Coordinator.
Detect resource conflicts and generate feasible alternatives or explicitly report that no feasible plan was found.
Support live simulation, event-driven updates, and human approval/rejection.
Make every visible landing-page and application control perform its documented action, including error and loading states.
Measure latency and model quality with reproducible tests; do not claim targets are achieved until verified.
3.2 Non-goals
Autonomous dispatch or real-world emergency-service orders.
Direct control of real drones, vehicles, weapons, or field equipment.
Guaranteeing operational safety or replacing trained incident command personnel.
Treating synthetic values as real observations.
Requiring external LLM, weather, or GPU services for the core demonstration.
4. Users and Permissions
Role
Capabilities
Viewer
Read dashboard, map, incidents, resources, missions, and audit records.
Analyst
Viewer capabilities plus create/update permitted synthetic data and trigger analyses.
Commander
Analyst capabilities plus approve, reject, or request revision of simulated mission proposals.
Administrator
Manage users/configuration and reset simulation according to deployment policy.

For a local prototype, roles may be simulated. Any deployed environment must enforce authentication and authorization server-side.
5. Information Architecture and Routes
Page
Route
Required purpose
Landing
/
Product introduction, features, architecture, entry points
Dashboard
/dashboard
KPIs, current state, activity, agent health, pending reviews
Incident map
/map
Geospatial incidents/resources and filters
Incident center
/incidents
Search, filter, sort, create and inspect incidents
Incident detail
/incidents/:id
Evidence, factors, agent outputs, history
Agent center
/agents
Agent status, runs, results, warnings and retries
Resource center
/resources
Inventory, availability, capacity and assignments
Mission planner
/missions
Proposals, conflicts, alternatives and statuses
Mission detail
/missions/:id
Rationale, input versions, validation and decisions
Simulator
/simulator
Load scenario, inject events, change conditions, stress-test
Audit log
/audit
Searchable record of material actions and decisions
Settings
/settings
Supported simulation and application configuration

6. Functional Requirements
6.1 Landing page: all controls must work
Control
Required behavior
Launch Dashboard
Navigate to /dashboard and load persisted state.
Explore Features
Scroll to the feature section or open its defined route.
View Architecture
Navigate to the architecture section/page.
Run Live Demo
Load a documented synthetic scenario and open the simulator/dashboard.
View Incidents
Navigate to /incidents.
Mission Planner
Navigate to /missions.
Navigation links
Open the correct route and preserve expected application state.
Mobile menu
Open/close and remain keyboard accessible.
Theme control, if included
Switch the theme consistently across routes.

No inert buttons, empty handlers, placeholder links, hard-coded success alerts, or controls that only change appearance are allowed. Every control must have a defined destination/action, visible feedback, and a test.
6.2 Dashboard
Show incident totals, high-priority incidents, available/assigned resources, pending approvals, simulated active missions, agent status, recent activity, and live connection state.
Fetch all metrics from backend state; do not hard-code operational figures.
Refresh retrieves current state; time-range selection updates supported statistics; metric cards navigate to filtered views.
Run Analysis starts eligible analysis jobs and shows queued/running/completed/failed states.
Pause/Resume affects the simulator event generator, not historical state.
Reset Demo requires confirmation and resets only the selected simulation scope.
Show notifications/activity, connection loss, reconnection, loading, empty, and error states.
6.3 Incident management and map
Incidents include unique ID, title, description, category, coordinates, timestamps, risk factors, evidence sources, confidence, priority, status, assignments, and related proposals.
Support search, category/priority/status filters, sorting, pagination, detail view, create/edit/save/cancel, evidence view, map focus, and analysis trigger.
Unknown values remain unknown; they must not be silently converted to zero.
Map supports pan/zoom, incident selection, marker popups, filters, resource visibility, fit-to-filtered-incidents, and map focus from detail pages.
Validate coordinates and handle map-provider/tile failures with a clear fallback state.
6.4 Six logical agents
Agent
Responsibility and outputs
Vision Agent
Analyze uploaded/static or simulated imagery; return damage categories, evidence references, confidence, processing state. Do not claim a live drone feed unless integrated.
Incident Agent
Convert reports into structured fields: category, location when supported, severity, affected people when reported, evidence, uncertainty, extraction confidence.
Weather/Terrain Agent
Assess synthetic/configured weather hazards and access constraints; report freshness, evidence and confidence.
Resource Agent
Check eligibility, availability, capacity, assignments, conflicts, and feasible alternatives.
Risk/Priority Agent
Calculate normalized priority, priority band, factor contributions, uncertainty and reasons for ranking changes.
Mission Coordinator
Combine validated agent outputs and current state into a versioned proposal with assignments, conflicts, alternatives, rationale and warnings.

These may be logical modules coordinated by one backend service; six separately deployed services are not required. Every agent uses a structured input/output contract. Record run ID, entity IDs, status, input references, result, confidence, warnings, timestamps, and error details.
6.5 Coordination engine: core requirement
Real coordination is defined as shared-state, event-driven re-planning—not agents merely returning separate answers. The system must persist incoming events, trigger relevant analyses, validate results, re-read current state, recalculate affected priorities, re-evaluate resource feasibility, detect conflicts, generate a versioned proposal, persist it, and publish an update.
Shared operational state is the authoritative source for incidents, evidence, resources, assignments, agent outputs and proposal versions.
Relevant changes trigger dependency-aware re-analysis and re-planning.
Use idempotency keys or event IDs to prevent duplicate event processing.
Use entity versions/optimistic concurrency checks to prevent stale writes and stale proposals.
If inputs change during planning, revalidate or discard the stale result.
Hard constraints are deterministic and cannot be overridden by an LLM.
If no feasible plan exists, return an explicit infeasible status and reasons rather than fabricating a solution.
Publish live updates only after the relevant state has been persisted.
6.6 Risk and priority formula
The source presentation proposes: P = 0.35Rₚ + 0.25Dₛ + 0.20Tᵣ − 0.10Cᵣ − 0.10Fₚ.
Rₚ = people at risk; Dₛ = damage severity; Tᵣ = response-time factor; Cᵣ = resource-conflict factor; Fₚ = reassignment-friction factor. Before implementation, define normalization and units for every term. The direction of each term must be documented—for example, whether a larger Tᵣ means longer delay and therefore greater urgency. Do not mix raw counts, minutes, and ordinal scores directly. Keep weights configurable and show factor contributions in the UI.
6.7 Mission planner and conflicts
Generate Plan creates a persisted proposal; Regenerate Plan uses current state.
Detect exclusive resource double-booking over overlapping time windows, capacity overruns, unavailable resources, access constraints, and missing required inputs.
Compare Alternatives shows distinct feasible plans and their trade-offs.
View Rationale shows factors, source evidence, confidence, assumptions, and warnings.
Approval is disabled for invalid or stale proposals and is revalidated on the server.
Rejection records a reason; request revision records a comment and produces a new version.
Changes to material inputs invalidate or flag affected proposals for review.
6.8 Human approval workflow
Draft → Proposed → Pending Review → Approved or Rejected. A separate simulated monitoring/execution state may be implemented, but approval never triggers a real-world deployment.
Only authorized users can approve/reject.
The backend validates permissions, proposal version, resource capacity, conflicts, and hard constraints in a transaction.
Record approver, timestamp, proposal version, decision and reason in the audit log.
A stale proposal must return a conflict response and require revalidation.
6.9 Simulator and stress tests
Control/scenario
Expected behavior
Load Scenario
Load a named, deterministic synthetic starting state.
Inject Incident
Persist a synthetic incident and trigger the coordination loop.
Change Severity
Update incident version and recalculate affected priorities/plans.
Change Weather
Update synthetic hazard state and re-evaluate affected proposals.
Disable/Add Resource
Persist availability/inventory changes and check affected assignments.
Trigger Conflict
Create a controlled, reproducible conflict case.
Run Stress Test
Execute a scenario and persist metrics/results.
Pause/Resume
Pause or resume scheduled synthetic events.
Reset Scenario
Require confirmation; restore selected scenario state without changing unrelated data.

7. End-to-End User Flow
Load a synthetic scenario with multiple incidents and resources.
Review dashboard, map, ranked queue, and current resource state.
Open an incident and inspect evidence, confidence, and priority factors.
Generate a mission proposal and inspect assignments and conflicts.
Inject a new high-priority incident or disable a resource.
Verify the event persists and relevant agents run.
Verify priorities and resource feasibility are recalculated.
Verify a revised, versioned proposal appears without a page reload.
Compare alternatives and approve, reject, or request revision.
Verify the decision and its rationale appear in the audit log.
8. API Requirements
All internal APIs are versioned under /api/v1. The endpoint catalogue below is the implementation contract; each endpoint must be implemented and tested or explicitly deferred.
Method
Endpoint
Purpose
GET
/health
Service health
GET
/ready
Database/dependency readiness
GET
/dashboard/summary
Operational metrics
GET
/dashboard/activity
Recent activity
GET
/events/stream
SSE live updates
GET/POST
/incidents
List/filter/paginate; create incident
GET/PATCH
/incidents/{id}
Read/update incident
POST
/incidents/{id}/analyze
Start analysis
GET
/incidents/{id}/evidence
Evidence references
GET
/incidents/{id}/history
Incident history
GET
/agents
List agent registry
GET
/agents/{id}
Agent details
GET
/agents/runs
List executions
GET
/agents/runs/{run_id}
Execution result/status
POST
/agents/runs
Start analysis job
POST
/agents/runs/{run_id}/retry
Retry eligible failed job
GET/POST
/resources
List/filter; add resource
GET/PATCH
/resources/{id}
Read/update resource
GET
/resources/{id}/assignments
Resource assignments
GET
/resources/availability
Availability at requested time
GET
/missions
List proposals
POST
/missions/generate
Generate proposal
GET
/missions/{id}
Proposal details
POST
/missions/{id}/regenerate
Generate revised proposal
GET
/missions/{id}/conflicts
Detected conflicts
POST
/missions/{id}/approve
Validated approval
POST
/missions/{id}/reject
Reject with reason
POST
/missions/{id}/request-revision
Request revision
GET
/missions/{id}/history
Proposal and decision history
GET
/simulator/scenarios
List scenarios
POST
/simulator/scenarios/{id}/load
Load scenario
POST
/simulator/incidents
Inject synthetic incident
POST
/simulator/weather
Update synthetic weather
POST
/simulator/resources
Add/change synthetic resource state
POST
/simulator/conflicts
Create controlled conflict
POST
/simulator/pause
Pause simulation
POST
/simulator/resume
Resume simulation
POST
/simulator/reset
Reset selected scenario
POST
/simulator/stress-tests
Start stress-test run
GET
/simulator/stress-tests/{run_id}
Stress-test status/results
GET
/audit
Search audit events
GET/PATCH
/settings
Read/update permitted settings

Use structured JSON responses and consistent error bodies. Suggested status codes: 200, 201, 202, 400, 401, 403, 404, 409, 422, 429, 500 and 503 as appropriate. Use 202 for asynchronous jobs. Return useful error codes/messages without stack traces or secrets.
8.1 External integrations
Integration
Use
Requirement/fallback
OpenStreetMap-compatible tiles or configured map provider
Map display
Map provider must comply with its terms; show fallback/error state.
LLM API (e.g. OpenAI)
Optional structured report extraction and explanation
Backend only; deterministic/synthetic fallback.
Weather API (e.g. OpenWeather)
Optional external observations
Synthetic weather is sufficient for core demo.
OpenCV + PyTorch model
Image preprocessing and damage assessment
Static images/synthetic results allowed; do not claim live video.
xBD/xView2
Disaster imagery evaluation/training
Verify dataset access, licensing and label definitions.
NASA Disasters resources
Optional disaster context/data
Integrate only data actually available from a verified endpoint.

Secrets must remain server-side in environment variables or a secret manager. Validate provider configuration, quotas, licenses, rate limits, file types and upload sizes. The core demo must not depend on optional external providers.
8.2 Live events
Publish event types such as incident.created, incident.updated, incident.priority_changed, agent.run_started, agent.run_completed, agent.run_failed, resource.status_changed, mission.generated, mission.conflict_detected, mission.approved, mission.rejected and simulation.state_changed. Persist changes before broadcasting. Use SSE for server-to-client updates, reconnect with backoff, and provide polling fallback.
9. Data Model
Entity
Core fields
Incident
id, title, description, category, coordinates, reported_at, updated_at, people_at_risk, damage_severity, hazard_risk, priority_score, priority_band, status, source_reliability, version
Resource
id, name, type, coordinates, capacity, available_capacity, status, estimated_response_time, last_updated_at, version
AgentRun
id, agent_id, incident_id/entity IDs, status, input_snapshot, result, confidence, warnings, started_at, completed_at, error_message
Mission
id, incident_ids, proposal_version, status, priority_score, assignments, conflicts, alternatives, rationale, input_versions, timestamps, approver and decision fields
SimulationEvent
id, scenario_id, event_type, payload, created_at, processed_at, status
AuditEvent
id, actor_id, action, entity_type, entity_id, before_state, after_state, timestamp, reason

Use unique IDs, validated coordinates, explicit timestamps and enumerated states.
Enforce capacity and assignment constraints in backend logic and, where practical, transaction/database constraints.
Use version fields to detect concurrent edits and stale proposals.
Store enough input-version references to reproduce why a proposal was generated.
Keep simulation reset scoped to the selected scenario.
Do not silently rewrite audit events during ordinary operation.
10. Technical Architecture
Layer
Recommended implementation
Frontend
React + TypeScript; Next.js or Vite; Tailwind CSS; accessible reusable components
API/backend
Python + FastAPI + Pydantic; versioned REST API; OpenAPI docs
Persistence
PostgreSQL/PostGIS for deployed use; SQLite acceptable for a local prototype
Map/charts
Leaflet with compliant tiles; Recharts or equivalent
Vision
OpenCV + PyTorch; compatible pretrained damage-assessment model
Coordination
Python orchestration and deterministic risk/conflict/planning modules; optionally LangGraph
Live updates
Server-Sent Events; WebSockets only if bidirectional streaming is needed
Testing
Pytest for backend; Playwright or equivalent for end-to-end browser tests

Architecture flow: data sources → ingestion/validation → agents → shared operational state → risk/conflict engine → mission coordinator → human review → audit and dashboard. AI outputs must pass schema and policy validation before they affect a proposal.
11. Non-Functional Requirements and Targets
Metric
Target from project concept
Measurement rule
Live update latency
≤ 2 seconds
Accepted event to updated committed state visible to connected client.
Recommendation generation
≤ 5 seconds
Accepted request to validated proposal; state whether external inference is included.
Incident ranking accuracy
≥ 90%
Compare against documented labeled scenarios and ground-truth ranking.
Conflict detection accuracy
≥ 95%
Report precision and recall on labeled conflict cases; do not rely on ambiguous accuracy alone.
Response latency constraint
≤ 5 seconds
Define exact workflow, hardware, data size and included services before measuring.
Resource over-allocation
Zero invalid assignments
All generated and approved proposals pass hard capacity and exclusivity checks.

These are proposed targets, not verified results. Report test environment, dataset size, percentiles and failure cases. Define normalization, thresholds and ground truth before reporting accuracy.
11.1 Reliability, security and accessibility
Isolate agent/provider failures; show partial results and warnings.
Persist accepted events; do not silently drop work.
Validate inputs server-side and enforce authorization on protected endpoints.
Protect against injection and XSS; limit uploads and costly requests; apply rate limits.
Use HTTPS in deployment and avoid logging secrets or unnecessary sensitive report content.
Support keyboard operation, visible focus, accessible labels, and status text not dependent on color alone.
Show loading, empty, error, offline and reconnecting states.
12. Acceptance Criteria
Landing and navigation
☐ Every visible landing-page control navigates or performs its documented action.
☐ Launch Dashboard, Run Live Demo, incident navigation and mission planner entry points work.
☐ No empty click handlers, placeholder links, or hard-coded success states.
Operational state
☐ Dashboard metrics reflect backend state.
☐ Incident create/edit/filter/detail workflows persist and display actual data.
☐ Map markers match stored coordinates and filters.
☐ Resource status and assignments remain consistent.
Agents and coordination
☐ All six logical agents have defined contracts and visible run states.
☐ New incidents and material resource/weather changes trigger relevant re-analysis.
☐ Rankings and plans are recalculated from state rather than cosmetically changed.
☐ Conflicts are detected; alternatives are feasible or the system reports infeasibility.
☐ Proposal versions and input versions are recorded.
Approval and audit
☐ Only authorized users can approve/reject.
☐ Backend blocks stale or invalid approvals.
☐ Rejections record reasons; decisions appear in audit history.
☐ Approval never triggers a real-world action.
Simulation and resilience
☐ Scenario injection works without restarting the app.
☐ Live updates reach the UI or a documented polling fallback works.
☐ Optional API failures do not prevent synthetic simulation.
☐ Reset is confirmed and scoped correctly.
☐ Critical workflows have automated tests.
13. Testing Strategy
Unit tests
Risk normalization and ranking; conflict detection; resource capacity; proposal validation; mission state transitions; schema validation; event idempotency; reset behavior.
Integration tests
Incident creation → agent runs → state update → ranking → planning; resource unavailability → conflict re-evaluation; approval/rejection → persistence and audit; event persistence → SSE delivery.
End-to-end tests
Use Playwright or equivalent for landing navigation, incident creation/filtering, map selection, scenario injection, plan generation, conflict inspection, approval/rejection, and error states.
Performance tests
Measure dashboard latency, event ingestion, ranking recalculation, conflict detection, recommendation generation, and event-to-visible-update latency on a documented dataset and environment.
14. Risks and Mitigations
Risk
Mitigation
Vision inference too slow
Resize images, use lightweight inference, cache eligible results, keep orchestration on CPU.
Free GPU session expires
Persist state; make scoring/orchestration CPU-capable.
Agent disagreement
Confidence/source-aware reconciliation; expose unresolved uncertainty.
LLM/weather API unavailable
Deterministic parsing and synthetic fallback.
Resource over-allocation
Deterministic validation and transaction-safe assignment checks.
Stale plan
Input versioning, concurrency checks, approval-time revalidation.
Live connection failure
Reconnect/backoff, polling fallback, visible connection state.
Misleading accuracy claims
Labeled test cases, documented metrics, honest reporting.
Scope overload
Complete core end-to-end workflow before advanced external integrations.

15. Implementation Roadmap
Phase
Deliverables
Exit condition
1. Foundation
Repo setup, schemas, database, synthetic seed data, landing/navigation, health endpoints
App starts; routes and data contracts work.
2. Operational UI
Dashboard, incidents, resources, map, persistence, filters
User can manage synthetic incidents/resources end-to-end.
3. Coordination core
Risk engine, conflict detector, planner, agent orchestration, proposal versioning
Scenario produces ranked incidents and a valid proposal or explicit infeasibility.
4. Human review/live updates
Approval, rejection, audit, SSE, stale-plan checks
New events update UI without restart; decisions are validated and logged.
5. AI integrations/testing
Vision and optional LLM/weather adapters, fallbacks, stress tests, measured metrics
Critical acceptance tests pass and demo is reproducible.

16. Demonstration Acceptance Scenario
Load a deterministic scenario with several incidents and resources.
Open an incident and inspect its evidence and factor contributions.
Generate a mission proposal and view assignments.
Inject a high-priority synthetic incident or disable a resource.
Observe event persistence, relevant agent runs, priority recalculation and conflict detection.
Observe the revised versioned plan in the UI without a page reload.
Compare alternatives and approve/reject the simulated proposal.
Verify the audit record and show measured latency.
17. Final Definition of Done
MissionSync 1.0 is complete when every required route works; every visible control has a tested behavior; the main workflows use implemented APIs; the shared operational state is persisted and versioned; event-driven coordination re-runs relevant analyses; deterministic validation prevents invalid resource assignments; mission proposals are explainable and require human approval; live updates work without a restart; synthetic fallback supports the core demo; and acceptance/performance results are recorded.
Final product rule: MissionSync must demonstrate real coordination—not merely multiple agent responses. A change in the operational state must cause a validated, traceable change in priorities and/or the proposed plan when the change is material.