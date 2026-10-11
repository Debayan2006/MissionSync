import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Play,
  Pause,
  RotateCcw,
  Plus,
  CloudRain,
  TriangleAlert,
  FlaskConical,
  Zap,
  Save,
  ShieldCheck,
  Activity as ActivityIcon,
  Eye,
  Boxes,
} from "lucide-react";
import { useStore, label, Row, time, shortId, sortNewest } from "./state";
import {
  Activity,
  Badge,
  Button,
  Dialog,
  Empty,
  KeyValue,
  PageHeading,
  Panel,
  Pagination,
  SearchBox,
} from "./ui";
import { IncidentForm, ResourceForm } from "./IncidentsResources";

export function Simulator() {
  const { data, act, request, busy, role } = useStore();
  const [scenarios, setScenarios] = useState<Row[]>([]),
    [scenario, setScenario] = useState("kolkata-flood"),
    [confirm, setConfirm] = useState<"load" | "reset" | null>(null),
    [inject, setInject] = useState(false),
    [resource, setResource] = useState(false),
    [incidentId, setIncidentId] = useState(""),
    [severity, setSeverity] = useState("8"),
    [resourceId, setResourceId] = useState(""),
    [hazard, setHazard] = useState(
      String(data.simulation.weather?.hazard_risk ?? 0.35),
    ),
    [blocked, setBlocked] = useState(
      data.simulation.weather?.access_blocked || false,
    ),
    [stressCount, setStressCount] = useState("20"),
    [stress, setStress] = useState<Row | null>(null);
  useEffect(() => {
    request("/simulator/scenarios")
      .then((s) => setScenarios(s.items || s))
      .catch(() => {});
  }, [request]);
  useEffect(() => {
    setHazard(String(data.simulation.weather?.hazard_risk ?? 0.35));
    setBlocked(data.simulation.weather?.access_blocked || false);
  }, [data.simulation.weather?.version]);
  useEffect(() => {
    if (!stress || ["completed", "failed"].includes(stress.status)) return;
    const poll = setInterval(
      () =>
        request(`/simulator/stress-tests/${stress.id}`)
          .then(setStress)
          .catch(() => {}),
      1000,
    );
    return () => clearInterval(poll);
  }, [stress?.id, stress?.status, request]);
  const canEdit = role !== "viewer";
  const applySeverity = (e: React.FormEvent) => {
    e.preventDefault();
    const incident = data.incidents.find((i) => i.id === incidentId);
    if (!incident) return;
    act(
      `/incidents/${incidentId}`,
      { damage_severity: Number(severity), expected_version: incident.version },
      "PATCH",
      "Severity changed; priorities and proposals recalculated",
    ).catch(() => {});
  };
  return (
    <>
      <PageHeading
        eyebrow="CONTROLLED, REPRODUCIBLE EVENTS"
        title="Simulation lab"
        description="Change the operating picture and watch the coordination loop respond."
        actions={
          <Button
            className="secondary"
            disabled={!canEdit}
            busy={busy}
            onClick={() =>
              act(
                `/simulator/${data.simulation.paused ? "resume" : "pause"}`,
                {},
                "POST",
                data.simulation.paused
                  ? "Scheduled synthetic events resumed"
                  : "Scheduled synthetic events paused",
              ).catch(() => {})
            }
          >
            {data.simulation.paused ? <Play size={16} /> : <Pause size={16} />}{" "}
            {data.simulation.paused ? "Resume simulation" : "Pause simulation"}
          </Button>
        }
      />
      <div className="simulation-banner">
        <div>
          <FlaskConical size={26} />
          <span>
            <small>CURRENT SIMULATION</small>
            <strong>
              {label(data.simulation.scenario_id || "No scenario")}
            </strong>
          </span>
        </div>
        <div>
          <Badge value={data.simulation.paused ? "paused" : "running"} />
          <span className="synthetic-label">SYNTHETIC ONLY</span>
        </div>
        <div>
          <span>Shared state revision</span>
          <strong>{data.simulation.state_revision ?? "—"}</strong>
        </div>
      </div>
      <div className="simulator-grid">
        <Panel
          title="01 / Load a scenario"
          description="Deterministic starting points for your demonstration"
        >
          <label className="select-label">
            Scenario
            <select
              aria-label="Scenario"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
            >
              {(scenarios.length
                ? scenarios
                : [
                    { id: "kolkata-flood", name: "Kolkata flood" },
                    { id: "industrial-fire", name: "Industrial fire" },
                  ]
              ).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name || label(s.id)}
                </option>
              ))}
            </select>
          </label>
          <p className="muted">
            {scenarios.find((s) => s.id === scenario)?.description ||
              "Multiple incidents and a synthetic resource inventory; no external services required."}
          </p>
          <div className="flex-actions">
            <Button
              className="primary"
              disabled={!canEdit}
              onClick={() => setConfirm("load")}
            >
              <Play size={16} />
              Load Scenario
            </Button>
            <Button
              className="secondary"
              disabled={role !== "administrator"}
              onClick={() => setConfirm("reset")}
            >
              <RotateCcw size={16} />
              Reset Scenario
            </Button>
          </div>
        </Panel>
        <Panel
          title="02 / Inject an incident"
          description="Persist a new report and trigger dependency-aware analysis"
        >
          <div className="sim-icon">
            <Plus size={28} />
          </div>
          <p className="muted">
            Create a synthetic report with a location, people at risk, damage
            and source reliability. Unknown risk inputs remain unknown.
          </p>
          <Button
            className="secondary"
            disabled={!canEdit}
            onClick={() => setInject(true)}
          >
            <Plus size={16} />
            Inject Incident
          </Button>
        </Panel>
        <Panel
          title="03 / Change severity"
          description="A material update invalidates affected proposals"
        >
          <form className="form" onSubmit={applySeverity}>
            <label>
              Incident
              <select
                aria-label="Severity incident"
                required
                value={incidentId}
                onChange={(e) => setIncidentId(e.target.value)}
              >
                <option value="">Select an incident</option>
                {data.incidents.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              New damage severity (0–10)
              <input
                aria-label="New damage severity"
                type="number"
                required
                min={0}
                max={10}
                step="0.1"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              />
            </label>
            <Button
              type="submit"
              className="secondary"
              disabled={!canEdit || !incidentId}
              busy={busy}
            >
              Apply severity change
            </Button>
          </form>
        </Panel>
        <Panel
          title="04 / Weather & access"
          description="Synthetic conditions, not live weather observations"
        >
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              act(
                "/simulator/weather",
                {
                  hazard_risk: Number(hazard),
                  access_blocked: blocked,
                  expected_version: data.simulation.weather?.version,
                },
                "POST",
                "Weather changed; affected proposals re-evaluated",
              ).catch(() => {});
            }}
          >
            <label>
              Hazard risk (0–1)
              <input
                aria-label="Hazard risk"
                type="number"
                min={0}
                max={1}
                step="0.01"
                value={hazard}
                onChange={(e) => setHazard(e.target.value)}
              />
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={blocked}
                onChange={(e) => setBlocked(e.target.checked)}
              />
              Access route blocked
            </label>
            <Button
              type="submit"
              className="secondary"
              disabled={!canEdit}
              busy={busy}
            >
              <CloudRain size={16} />
              Change Weather
            </Button>
          </form>
        </Panel>
        <Panel
          title="05 / Resource availability"
          description="Re-evaluate capacity and conflicting assignments"
        >
          <label className="select-label">
            Resource
            <select
              aria-label="Simulation resource"
              value={resourceId}
              onChange={(e) => setResourceId(e.target.value)}
            >
              <option value="">Select resource</option>
              {data.resources.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} · {label(r.status)}
                </option>
              ))}
            </select>
          </label>
          <div className="flex-actions">
            <Button
              className="secondary"
              disabled={!canEdit || !resourceId}
              busy={busy}
              onClick={() => {
                const r = data.resources.find((r) => r.id === resourceId)!;
                act(
                  "/simulator/resources",
                  {
                    resource_id: r.id,
                    status:
                      r.status === "unavailable" ? "available" : "unavailable",
                    expected_version: r.version,
                  },
                  "POST",
                  "Resource availability changed; feasibility checked",
                ).catch(() => {});
              }}
            >
              <Boxes size={16} />
              {data.resources.find((r) => r.id === resourceId)?.status ===
              "unavailable"
                ? "Enable Resource"
                : "Disable Resource"}
            </Button>
            <Button
              className="secondary"
              disabled={!canEdit}
              onClick={() => setResource(true)}
            >
              <Plus size={16} />
              Add Resource
            </Button>
          </div>
        </Panel>
        <Panel
          title="06 / Conflict & stress test"
          description="Controlled test cases and measured local results"
        >
          <p className="muted">
            Trigger a reproducible contention case or measure repeated planner
            evaluations. Planner samples use in-memory synthetic variations; the
            stress test does not inject live simulation events.
          </p>
          <Button
            className="danger-outline"
            disabled={!canEdit}
            busy={busy}
            onClick={() =>
              act(
                "/simulator/conflicts",
                {},
                "POST",
                "Controlled conflict created; inspect the new proposal",
              ).catch(() => {})
            }
          >
            <TriangleAlert size={16} />
            Trigger Conflict
          </Button>
          <form
            className="stress-form"
            onSubmit={(e) => {
              e.preventDefault();
              act(
                "/simulator/stress-tests",
                { event_count: Number(stressCount) },
                "POST",
                "Stress test submitted",
              )
                .then(setStress)
                .catch(() => {});
            }}
          >
            <label>
              Planner samples
              <input
                aria-label="Stress test event count"
                type="number"
                required
                min={1}
                max={250}
                value={stressCount}
                onChange={(e) => setStressCount(e.target.value)}
              />
            </label>
            <Button
              type="submit"
              className="secondary"
              disabled={!canEdit}
              busy={busy}
            >
              <Zap size={16} />
              Run Stress Test
            </Button>
          </form>
        </Panel>
      </div>
      {stress && (
        <Panel
          title={`Stress-test ${shortId(stress.id)}`}
          description="Persisted timing results for this local synthetic run"
          action={<Badge value={stress.status} />}
        >
          <pre>
            {JSON.stringify(stress.result || stress.metrics || stress, null, 2)}
          </pre>
          <p className="muted">
            These measurements apply to this run and environment. Ranking
            accuracy and conflict precision require labeled evaluation data.
          </p>
        </Panel>
      )}
      <Panel
        title="The coordination loop"
        description="Every accepted material event changes persisted state before live updates are published"
      >
        <div className="coordination-steps">
          {[
            "Persist event",
            "Run relevant agents",
            "Recalculate priorities",
            "Validate constraints",
            "Generate proposal",
            "Human review",
          ].map((step, i) => (
            <div key={step}>
              <span>{String(i + 1).padStart(2, "0")}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
        <Link className="text-link" to="/missions">
          Inspect current mission proposals →
        </Link>
      </Panel>
      {confirm && (
        <Dialog
          title={
            confirm === "load"
              ? "Load a synthetic scenario?"
              : "Reset selected scenario?"
          }
          onClose={() => setConfirm(null)}
        >
          <p>
            {confirm === "load"
              ? `Load ${label(scenario)} as the active deterministic simulation. Existing inputs in this scenario are retained; a new scenario starts from deterministic seed data. The audit records the switch.`
              : `Restore ${label(data.simulation.scenario_id)} to its initial synthetic state. This reset is scoped to the selected simulation.`}
          </p>
          <div className="dialog-actions">
            <Button className="secondary" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button
              className={confirm === "reset" ? "danger" : "primary"}
              busy={busy}
              onClick={() =>
                act(
                  confirm === "load"
                    ? `/simulator/scenarios/${scenario}/load`
                    : "/simulator/reset",
                  confirm === "load"
                    ? { confirmed: true }
                    : {
                        scenario_id: data.simulation.scenario_id,
                        confirmed: true,
                      },
                  "POST",
                  confirm === "load"
                    ? "Synthetic scenario loaded"
                    : "Selected scenario reset",
                )
                  .then(() => setConfirm(null))
                  .catch(() => {})
              }
            >
              {confirm === "load" ? "Confirm load" : "Confirm reset"}
            </Button>
          </div>
        </Dialog>
      )}
      {inject && <IncidentForm inject onClose={() => setInject(false)} />}{" "}
      {resource && <ResourceForm onClose={() => setResource(false)} />}
    </>
  );
}

export function Audit() {
  const { data, request } = useStore();
  const [search, setSearch] = useState(""),
    [entity, setEntity] = useState("all"),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState<Row | null>(null),
    [rows, setRows] = useState<Row[]>([]),
    [total, setTotal] = useState(0),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    const timer = setTimeout(() => {
      const query = new URLSearchParams({
        search,
        entity_type: entity,
        page: String(page),
        page_size: "10",
        sort: "-timestamp",
      });
      request(`/audit?${query}`)
        .then((result) => {
          if (active) {
            setRows(result.items);
            setTotal(result.total);
            setError("");
          }
        })
        .catch((failure) => {
          if (active) setError(failure.message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 150);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [search, entity, page, request, data.audit[0]?.id, reload]);
  return (
    <>
      <PageHeading
        eyebrow="TRACEABILITY & HUMAN DECISIONS"
        title="Audit log"
        description="A persistent record of material changes, recommendations and approvals."
      />
      <div className="page-stat-strip">
        <span>
          <ShieldCheck size={17} />
          <strong>{total}</strong>{" "}
          {search || entity !== "all" ? "matching actions" : "recorded actions"}
        </span>
        <span>Append-only operational history</span>
        <span className="synthetic-label">SIMULATION AUDIT</span>
      </div>
      <Panel>
        <div className="filter-bar">
          <SearchBox
            value={search}
            onChange={(v) => {
              setSearch(v);
              setPage(1);
            }}
            placeholder="Search audit events"
          />
          <select
            aria-label="Audit entity filter"
            value={entity}
            onChange={(e) => {
              setEntity(e.target.value);
              setPage(1);
            }}
          >
            <option value="all">All entity types</option>
            {Array.from(
              new Set([
                "incident",
                "resource",
                "mission",
                "simulation",
                "settings",
                "agent_run",
                ...data.audit.map((a) => a.entity_type),
              ]),
            ).map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        </div>
        {error ? (
          <div className="error-banner" role="alert">
            <span>Unable to load audit records: {error}</span>
            <Button onClick={() => setReload(reload + 1)}>
              Retry audit request
            </Button>
          </div>
        ) : loading ? (
          <div className="empty" aria-live="polite">
            Loading persisted audit records…
          </div>
        ) : rows.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Entity</th>
                  <th>Actor</th>
                  <th>Time</th>
                  <th>Reason</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <button
                        className="row-title text-button"
                        onClick={() => setSelected(a)}
                      >
                        {label(a.action)}
                      </button>
                    </td>
                    <td>
                      {label(a.entity_type)}
                      <span className="row-sub">{shortId(a.entity_id)}</span>
                    </td>
                    <td>{a.actor_id || "System"}</td>
                    <td>{time(a.timestamp)}</td>
                    <td className="reason-cell">{a.reason || "—"}</td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`Inspect audit ${a.id}`}
                        onClick={() => setSelected(a)}
                      >
                        <Eye size={17} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No matching audit events" />
        )}
        <Pagination page={page} setPage={setPage} total={total} size={10} />
      </Panel>
      {selected && (
        <Dialog
          title={label(selected.action)}
          onClose={() => setSelected(null)}
        >
          <KeyValue label="Actor" value={selected.actor_id} />
          <KeyValue label="Timestamp" value={time(selected.timestamp)} />
          <KeyValue
            label="Entity"
            value={`${selected.entity_type} / ${selected.entity_id}`}
          />
          {selected.reason && (
            <p>
              <strong>Reason:</strong> {selected.reason}
            </p>
          )}
          <h3>Before state</h3>
          <pre>{JSON.stringify(selected.before_state, null, 2)}</pre>
          <h3>After state</h3>
          <pre>{JSON.stringify(selected.after_state, null, 2)}</pre>
        </Dialog>
      )}
    </>
  );
}

export function SettingsPage() {
  const { data, act, busy, role } = useStore();
  const [weights, setWeights] = useState<Row>({ ...data.settings.weights }),
    [interval, setInterval] = useState(
      String(data.settings.event_interval_seconds ?? 30),
    );
  useEffect(() => {
    setWeights({ ...data.settings.weights });
    setInterval(String(data.settings.event_interval_seconds ?? 30));
  }, [data.settings.version]);
  const save = (e: React.FormEvent) => {
    e.preventDefault();
    act(
      "/settings",
      {
        weights,
        event_interval_seconds: Number(interval),
        expected_version: data.settings.version,
      },
      "PATCH",
      "Configuration saved; priorities and proposals recalculated",
    ).catch(() => {});
  };
  const defaults: Row = {
    people: 0.35,
    damage: 0.25,
    response: 0.2,
    conflict: -0.1,
    friction: -0.1,
  };
  return (
    <>
      <PageHeading
        eyebrow="SUPPORTED APPLICATION CONFIGURATION"
        title="Settings"
        description="Configure the synthetic coordination engine with explicit, auditable changes."
      />
      <div className="two-columns settings-grid">
        <Panel
          title="Priority model"
          description="Active weights are applied to normalized factors"
        >
          <form className="form" onSubmit={save}>
            {Object.entries(defaults).map(([key, value]) => (
              <label className="weight-row" key={key}>
                <span>
                  {label(key)}
                  <small>
                    {["conflict", "friction"].includes(key)
                      ? "Plan suitability penalty"
                      : "Incident urgency factor"}
                  </small>
                </span>
                <input
                  aria-label={`${label(key)} weight`}
                  type="number"
                  required
                  min={["conflict", "friction"].includes(key) ? -1 : 0}
                  max={["conflict", "friction"].includes(key) ? 0 : 1}
                  step="0.01"
                  value={weights[key] ?? value}
                  onChange={(e) =>
                    setWeights({ ...weights, [key]: Number(e.target.value) })
                  }
                />
              </label>
            ))}
            <label>
              Scheduled event interval (seconds)
              <input
                aria-label="Event interval seconds"
                type="number"
                required
                min={5}
                max={300}
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
              />
            </label>
            <div className="flex-actions">
              <Button
                className="primary"
                disabled={role !== "administrator"}
                busy={busy}
                type="submit"
              >
                <Save size={16} />
                Save settings
              </Button>
              <Button
                className="secondary"
                type="button"
                onClick={() => {
                  setWeights({ ...data.settings.weights });
                  setInterval(
                    String(data.settings.event_interval_seconds ?? 30),
                  );
                }}
              >
                Discard changes
              </Button>
            </div>
            {role !== "administrator" && (
              <p className="warning-note">
                Administrator role is required to save configuration.
              </p>
            )}
          </form>
        </Panel>
        <div>
          <Panel title="Normalization & direction">
            <div className="normalization-list">
              <KeyValue label="People at risk" value="min(people / 500, 1)" />
              <KeyValue label="Damage severity" value="severity / 10" />
              <KeyValue label="Response delay" value="min(minutes / 120, 1)" />
              <KeyValue
                label="Resource conflict"
                value="0–1 conflict fraction"
              />
              <KeyValue
                label="Reassignment friction"
                value="0–1 friction fraction"
              />
            </div>
            <p className="muted">
              Larger response delay means greater urgency. Positive weighted
              contributions are divided by the sum of positive weights; the
              final score is clamped to 0–100. Missing inputs remain unknown and
              emit warnings.
            </p>
            <div className="formula-note">
              <code>P = Σ(weight × normalized factor)</code>
              <p>
                Default weights: 0.35 people + 0.25 damage + 0.20 response −
                0.10 conflict − 0.10 friction.
              </p>
            </div>
            <p className="muted">
              Priority bands: Critical ≥75 · High ≥55 · Medium ≥30 · Low
              below30.
            </p>
          </Panel>
          <Panel title="Environment & permissions">
            <KeyValue label="Data providers" value="Synthetic adapters" />
            <KeyValue label="Database" value="Persisted server state" />
            <KeyValue label="Current demo role" value={label(role)} />
            <KeyValue
              label="Configuration version"
              value={data.settings.version ?? "—"}
            />
            <p className="muted">
              Roles are simulated for this local prototype and enforced by the
              API. Optional external integrations are not configured. Production
              deployment requires secure authentication and HTTPS.
            </p>
          </Panel>
        </div>
      </div>
    </>
  );
}
