import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Plus,
  ArrowUpRight,
  Pencil,
  MapPin,
  Activity as ActivityIcon,
  Radio,
  ShieldCheck,
  Boxes,
  Filter,
  Save,
  Image,
  FileText,
} from "lucide-react";
import { useStore, label, Row, time, shortId, sortNewest } from "./state";
import {
  Activity,
  Badge,
  Button,
  DetailLink,
  Dialog,
  Empty,
  KeyValue,
  PageHeading,
  Panel,
  Pagination,
  SearchBox,
} from "./ui";

const nullable = (value: FormDataEntryValue | null) =>
  value === null || value === "" ? null : Number(value);
export function IncidentForm({
  incident,
  onClose,
  inject = false,
}: {
  incident?: Row;
  onClose: () => void;
  inject?: boolean;
}) {
  const { act, busy } = useStore();
  const save = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body = {
      title: form.get("title"),
      description: form.get("description"),
      category: form.get("category"),
      coordinates: {
        lat: Number(form.get("lat")),
        lng: Number(form.get("lng")),
      },
      people_at_risk: nullable(form.get("people_at_risk")),
      damage_severity: nullable(form.get("damage_severity")),
      response_time_minutes: nullable(form.get("response_time_minutes")),
      source_reliability: Number(form.get("source_reliability")),
      ...(incident
        ? { expected_version: incident.version, status: form.get("status") }
        : {}),
    };
    act(
      incident
        ? `/incidents/${incident.id}`
        : inject
          ? "/simulator/incidents"
          : "/incidents",
      body,
      incident ? "PATCH" : "POST",
      incident
        ? "Incident updated and re-analysis triggered"
        : "Synthetic incident created; coordination updated",
    )
      .then(onClose)
      .catch(() => {});
  };
  return (
    <Dialog
      title={
        incident
          ? "Edit incident"
          : inject
            ? "Inject synthetic incident"
            : "Create synthetic incident"
      }
      onClose={onClose}
    >
      <form onSubmit={save} className="form">
        <p className="form-notice">
          Synthetic input only. Leave unknown risk values empty; they are not
          interpreted as zero.
        </p>
        <label>
          Incident title
          <input
            name="title"
            required
            minLength={3}
            maxLength={160}
            defaultValue={incident?.title}
            placeholder="e.g. Flooding near riverside clinic"
            autoFocus
          />
        </label>
        <label>
          Description
          <textarea
            name="description"
            required
            rows={3}
            maxLength={4000}
            defaultValue={incident?.description}
            placeholder="Report observed conditions, uncertainty and affected people."
          />
        </label>
        <div className="form-grid">
          <label>
            Category
            <select
              name="category"
              aria-label="Category"
              defaultValue={incident?.category || "flood"}
            >
              {["flood", "fire", "medical", "infrastructure"].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          {incident && (
            <label>
              Status
              <select
                name="status"
                aria-label="Status"
                defaultValue={incident.status}
              >
                {["open", "monitoring", "resolved"].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
          )}
          <label>
            Latitude
            <input
              name="lat"
              type="number"
              required
              min={-90}
              max={90}
              step="any"
              defaultValue={incident?.coordinates?.lat ?? 22.5726}
            />
          </label>
          <label>
            Longitude
            <input
              name="lng"
              type="number"
              required
              min={-180}
              max={180}
              step="any"
              defaultValue={incident?.coordinates?.lng ?? 88.3639}
            />
          </label>
          <label>
            People at risk
            <input
              name="people_at_risk"
              type="number"
              min={0}
              max={1000000}
              step={1}
              defaultValue={incident?.people_at_risk ?? ""}
              placeholder="Unknown"
            />
          </label>
          <label>
            Damage severity (0–10)
            <input
              name="damage_severity"
              type="number"
              min={0}
              max={10}
              step="0.1"
              defaultValue={incident?.damage_severity ?? ""}
              placeholder="Unknown"
            />
          </label>
          <label>
            Response delay (minutes)
            <input
              name="response_time_minutes"
              type="number"
              min={0}
              max={1440}
              step="1"
              defaultValue={incident?.response_time_minutes ?? ""}
              placeholder="Unknown"
            />
          </label>
          <label>
            Source reliability (0–1)
            <input
              name="source_reliability"
              required
              type="number"
              min={0}
              max={1}
              step="0.01"
              defaultValue={incident?.source_reliability ?? 0.8}
            />
          </label>
        </div>
        <div className="dialog-actions">
          <Button type="button" className="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" className="primary" busy={busy}>
            <Save size={16} />
            {incident ? "Save changes" : "Create incident"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function Incidents() {
  const { data, role } = useStore();
  const [params] = useSearchParams();
  const [search, setSearch] = useState(""),
    [category, setCategory] = useState("all"),
    [priority, setPriority] = useState(params.get("priority") || "all"),
    [status, setStatus] = useState("all"),
    [sort, setSort] = useState("priority"),
    [page, setPage] = useState(1),
    [create, setCreate] = useState(false);
  useEffect(() => setPage(1), [search, category, priority, status, sort]);
  const filtered = data.incidents
    .filter(
      (i) =>
        `${i.title} ${i.description} ${i.id}`
          .toLowerCase()
          .includes(search.toLowerCase()) &&
        (category === "all" || i.category === category) &&
        (priority === "all" || i.priority_band === priority) &&
        (status === "all" || i.status === status),
    )
    .sort((a, b) =>
      sort === "priority"
        ? b.priority_score - a.priority_score
        : sort === "recent"
          ? String(b.updated_at).localeCompare(String(a.updated_at))
          : a.title.localeCompare(b.title),
    );
  return (
    <>
      <PageHeading
        eyebrow="INCIDENT INTELLIGENCE"
        title="Incident center"
        description="Validate the evidence, understand the risk, and track every change."
        actions={
          <Button
            className="primary"
            disabled={role === "viewer"}
            onClick={() => setCreate(true)}
          >
            <Plus size={17} />
            Create incident
          </Button>
        }
      />
      <div className="page-stat-strip">
        <span>
          <Radio size={17} />
          <strong>{data.incidents.length}</strong> total incidents
        </span>
        <span>
          <strong>
            {data.incidents.filter((i) => i.status === "open").length}
          </strong>{" "}
          open
        </span>
        <span>
          <strong>
            {
              data.incidents.filter((i) => i.priority_band === "critical")
                .length
            }
          </strong>{" "}
          critical
        </span>
        <span className="synthetic-label">SYNTHETIC DATA</span>
      </div>
      <Panel>
        <div className="filter-bar">
          <SearchBox
            value={search}
            onChange={setSearch}
            placeholder="Search incidents"
          />
          <select
            aria-label="Category filter"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="all">All categories</option>
            {["flood", "fire", "medical", "infrastructure"].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
          <select
            aria-label="Priority filter"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="all">All priorities</option>
            {["critical", "high", "medium", "low"].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
          <select
            aria-label="Status filter"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All statuses</option>
            {["open", "monitoring", "resolved"].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
          <select
            aria-label="Sort incidents"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="priority">Highest priority</option>
            <option value="recent">Recently updated</option>
            <option value="title">Title A–Z</option>
          </select>
        </div>
        {filtered.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Incident / category</th>
                  <th>Priority</th>
                  <th>People at risk</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.slice((page - 1) * 8, page * 8).map((i) => (
                  <tr key={i.id}>
                    <td>
                      <Link className="row-title" to={`/incidents/${i.id}`}>
                        {i.title}
                      </Link>
                      <span className="row-sub">
                        {label(i.category)} · {shortId(i.id)} · v{i.version}
                      </span>
                    </td>
                    <td>
                      <Badge value={i.priority_band} />
                      <span className="row-sub">
                        {Number(i.priority_score).toFixed(1)} / 100
                      </span>
                    </td>
                    <td>{i.people_at_risk ?? "Unknown"}</td>
                    <td>
                      <Badge value={i.status} />
                    </td>
                    <td>{time(i.updated_at)}</td>
                    <td>
                      <Link
                        className="icon-button"
                        to={`/incidents/${i.id}`}
                        aria-label={`View ${i.title}`}
                      >
                        <ArrowUpRight size={18} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No matching incidents" />
        )}
        <Pagination page={page} setPage={setPage} total={filtered.length} />
      </Panel>
      {create && <IncidentForm onClose={() => setCreate(false)} />}
    </>
  );
}

export function IncidentDetail() {
  const { id } = useParams();
  const { data, act, busy, role, request } = useStore();
  const [edit, setEdit] = useState(false),
    [evidence, setEvidence] = useState<Row[]>([]),
    [history, setHistory] = useState<Row[]>([]);
  const incident = data.incidents.find((i) => i.id === id);
  useEffect(() => {
    if (!id) return;
    request(`/incidents/${id}/evidence`)
      .then((value) => setEvidence(value.items || value.evidence || value))
      .catch(() => {});
    request(`/incidents/${id}/history`)
      .then((value) => setHistory(value.items || value.history || value))
      .catch(() => {});
  }, [id, incident?.version, request]);
  if (!incident) return <Empty title="Incident not found" />;
  const rawFactors = incident.priority_factors || incident.factors || [];
  const factors = Array.isArray(rawFactors)
    ? rawFactors
    : Object.entries(rawFactors).map(([key, value]: any) => ({
        ...value,
        key,
        value: value.raw,
        unknown: !value.known,
      }));
  const runs = data.agent_runs
    .filter(
      (run) => run.incident_id === id || (run.entity_ids || []).includes(id),
    )
    .slice(0, 6);
  return (
    <>
      <Link className="back-link" to="/incidents">
        ← Incident center
      </Link>
      <PageHeading
        eyebrow={`${label(incident.category).toUpperCase()} / ${shortId(incident.id).toUpperCase()} / VERSION ${incident.version}`}
        title={incident.title}
        description={incident.description}
        actions={
          <>
            <Link
              className="button secondary"
              to={`/map?incident=${incident.id}`}
            >
              <MapPin size={16} />
              Focus on map
            </Link>
            <Button
              className="secondary"
              disabled={role === "viewer"}
              onClick={() => setEdit(true)}
            >
              <Pencil size={16} />
              Edit incident
            </Button>
            <Button
              className="primary"
              disabled={role === "viewer"}
              busy={busy}
              onClick={() =>
                act(
                  `/incidents/${id}/analyze`,
                  {},
                  "POST",
                  "Incident analysis submitted",
                ).catch(() => {})
              }
            >
              <ActivityIcon size={16} />
              Analyze incident
            </Button>
          </>
        }
      />
      <div className="detail-top-strip">
        <Badge value={incident.priority_band} />
        <Badge value={incident.status} />
        <span className="synthetic-label">SYNTHETIC REPORT</span>
        <span>Reported {time(incident.reported_at)}</span>
        <span>Updated {time(incident.updated_at)}</span>
      </div>
      <div className="detail-grid">
        <Panel
          title="Risk & priority"
          description="Normalized factors · configurable weights"
        >
          <div className="score-block">
            <strong>
              {Number(incident.priority_score).toFixed(1)}
              <small>/100</small>
            </strong>
            <div>
              <Badge value={incident.priority_band} />
              <p>Calculated decision-support score</p>
            </div>
          </div>
          <div className="factors">
            {factors.length ? (
              factors.map((factor: Row) => (
                <div key={factor.key}>
                  <div>
                    <strong>{factor.label || label(factor.key)}</strong>
                    <span>
                      {factor.unknown || factor.normalized == null
                        ? "Unknown"
                        : `${factor.value ?? "Unknown"} · weight ${Number(factor.weight).toFixed(2)}`}
                    </span>
                  </div>
                  <div className="factor-track">
                    <i
                      style={{
                        width: `${Math.min(100, Math.abs(Number(factor.normalized || 0)) * 100)}%`,
                      }}
                    />
                  </div>
                  <strong>
                    {factor.unknown || factor.contribution == null
                      ? "—"
                      : `${Number(factor.contribution) >= 0 ? "+" : ""}${Number(factor.contribution).toFixed(2)} pts`}
                  </strong>
                </div>
              ))
            ) : (
              <Empty title="Priority factors not available" />
            )}
          </div>
          <div className="formula-note">
            <strong>How to read this score</strong>
            <p>
              People at risk, damage and response delay increase urgency.
              Conflict and reassignment friction reduce plan suitability. Larger
              response delay means greater urgency; unknown inputs remain
              explicit.
            </p>
            <code>P = 0.35Rₚ + 0.25Dₛ + 0.20Tᵣ − 0.10Cᵣ − 0.10Fₚ</code>
            <p>
              Default weights shown above; active weights and normalization are
              available in <Link to="/settings">Settings</Link>.
            </p>
          </div>
          {(incident.warnings || []).map((warning: string) => (
            <p key={warning} className="warning-note">
              {warning}
            </p>
          ))}
        </Panel>
        <div>
          <Panel title="Incident profile">
            <KeyValue
              label="People at risk"
              value={incident.people_at_risk ?? "Unknown"}
            />
            <KeyValue
              label="Damage severity"
              value={
                incident.damage_severity === null
                  ? "Unknown"
                  : `${incident.damage_severity ?? "Unknown"} / 10`
              }
            />
            <KeyValue
              label="Response delay"
              value={
                incident.response_time_minutes == null
                  ? "Unknown"
                  : `${incident.response_time_minutes} minutes`
              }
            />
            <KeyValue
              label="Source reliability"
              value={`${Math.round(incident.source_reliability * 100)}%`}
            />
            <KeyValue
              label="Location"
              value={`${incident.coordinates.lat.toFixed(4)}, ${incident.coordinates.lng.toFixed(4)}`}
            />
            <KeyValue
              label="Hazard risk"
              value={
                incident.hazard_risk == null
                  ? "Unknown"
                  : `${Math.round(incident.hazard_risk * 100)}%`
              }
            />
          </Panel>
          <Panel title="Related proposals">
            <div className="simple-list">
              {data.missions
                .filter((m) => m.incident_ids?.includes(id))
                .slice(0, 5)
                .map((m) => (
                  <Link key={m.id} to={`/missions/${m.id}`}>
                    <span>
                      Proposal {shortId(m.id)} · v{m.proposal_version}
                    </span>
                    <Badge value={m.status} />
                  </Link>
                ))}
            </div>
          </Panel>
        </div>
      </div>
      <div className="two-columns">
        <Panel
          title="Evidence & sources"
          description="Synthetic evidence references; no live imagery claims"
        >
          {evidence.length ? (
            evidence.map((e) => (
              <div className="evidence-card" key={e.id}>
                {e.type?.includes("image") ? (
                  <Image size={21} />
                ) : (
                  <FileText size={21} />
                )}
                <div>
                  <strong>{e.label || label(e.type)}</strong>
                  <p>{e.description || e.source}</p>
                  <small>
                    {e.source} ·{" "}
                    {e.confidence == null
                      ? "Unknown confidence"
                      : `${Math.round(e.confidence * 100)}% confidence`}
                  </small>
                </div>
                <Badge value="synthetic" />
              </div>
            ))
          ) : (
            <Empty
              title="No attached evidence"
              description="The report remains the current synthetic input."
            />
          )}
        </Panel>
        <Panel
          title="Analysis outputs"
          description="Recorded run states and deterministic results"
        >
          <div className="simple-list">
            {runs.map((run) => (
              <Link to={`/agents?run=${run.id}`} key={run.id}>
                <div>
                  <strong>{label(run.agent_id)}</strong>
                  <span className="row-sub">
                    {time(run.completed_at || run.started_at)}
                  </span>
                </div>
                <Badge value={run.status} />
              </Link>
            ))}
          </div>
          {!runs.length && <Empty title="No agent runs yet" />}
        </Panel>
      </div>
      <Panel
        title="Incident history"
        description="Persisted evidence of updates and decisions"
      >
        <Activity rows={sortNewest(history).slice(0, 10)} />
      </Panel>
      {edit && (
        <IncidentForm incident={incident} onClose={() => setEdit(false)} />
      )}
    </>
  );
}

export function ResourceForm({
  resource,
  onClose,
}: {
  resource?: Row;
  onClose: () => void;
}) {
  const { act, busy } = useStore();
  const save = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body = {
      name: form.get("name"),
      type: form.get("type"),
      capacity: Number(form.get("capacity")),
      status: form.get("status"),
      estimated_response_time: Number(form.get("response")),
      coordinates: {
        lat: Number(form.get("lat")),
        lng: Number(form.get("lng")),
      },
      ...(resource ? { expected_version: resource.version } : {}),
    };
    act(
      resource ? `/resources/${resource.id}` : "/resources",
      body,
      resource ? "PATCH" : "POST",
      "Resource inventory updated; feasibility rechecked",
    )
      .then(onClose)
      .catch(() => {});
  };
  return (
    <Dialog
      title={resource ? "Edit resource" : "Add synthetic resource"}
      onClose={onClose}
    >
      <form className="form" onSubmit={save}>
        <label>
          Resource name
          <input
            name="name"
            required
            minLength={3}
            maxLength={120}
            defaultValue={resource?.name}
            autoFocus
          />
        </label>
        <div className="form-grid">
          <label>
            Resource type
            <select
              name="type"
              aria-label="Resource type"
              defaultValue={resource?.type || "rescue"}
            >
              {["rescue", "medical", "fire", "logistics"].map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Status
            <select
              name="status"
              aria-label="Status"
              defaultValue={resource?.status || "available"}
            >
              {["available", "unavailable", "assigned"].map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Capacity
            <input
              name="capacity"
              type="number"
              min={1}
              max={10000}
              step={1}
              required
              defaultValue={resource?.capacity || 20}
            />
          </label>
          <label>
            Response time (minutes)
            <input
              name="response"
              type="number"
              min={0}
              max={1440}
              required
              defaultValue={resource?.estimated_response_time ?? 15}
            />
          </label>
          <label>
            Latitude
            <input
              name="lat"
              type="number"
              min={-90}
              max={90}
              step="any"
              required
              defaultValue={resource?.coordinates?.lat ?? 22.57}
            />
          </label>
          <label>
            Longitude
            <input
              name="lng"
              type="number"
              min={-180}
              max={180}
              step="any"
              required
              defaultValue={resource?.coordinates?.lng ?? 88.36}
            />
          </label>
        </div>
        <p className="form-notice">
          Capacity and existing assignments are validated server-side. Changes
          may invalidate proposals.
        </p>
        <div className="dialog-actions">
          <Button type="button" className="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button className="primary" busy={busy} type="submit">
            <Save size={16} />
            Save resource
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
export function Resources() {
  const { data, role } = useStore();
  const [params] = useSearchParams(),
    [search, setSearch] = useState(""),
    [type, setType] = useState("all"),
    [status, setStatus] = useState(params.get("status") || "all"),
    [edit, setEdit] = useState<Row | null | undefined>(undefined),
    [selected, setSelected] = useState<Row | null>(null),
    [page, setPage] = useState(1);
  useEffect(() => setPage(1), [search, type, status]);
  const rows = data.resources.filter(
    (r) =>
      `${r.name} ${r.id}`.toLowerCase().includes(search.toLowerCase()) &&
      (type === "all" || r.type === type) &&
      (status === "all" || r.status === status),
  );
  const assignments = selected
    ? data.missions
        .filter((m) => m.status === "approved")
        .flatMap(
          (m) =>
            m.assignments
              ?.filter((a: Row) => a.resource_id === selected.id)
              .map((a: Row) => ({ ...a, mission_id: m.id })) || [],
        )
    : [];
  return (
    <>
      <PageHeading
        eyebrow="RESOURCE COORDINATION"
        title="Resource inventory"
        description="Availability, capacity and assignments from the authoritative shared state."
        actions={
          <Button
            className="primary"
            disabled={role === "viewer"}
            onClick={() => setEdit(null)}
          >
            <Plus size={17} />
            Add resource
          </Button>
        }
      />
      <div className="page-stat-strip">
        <span>
          <Boxes size={17} />
          <strong>{data.resources.length}</strong> resources
        </span>
        <span>
          <strong>
            {data.resources.filter((r) => r.status === "available").length}
          </strong>{" "}
          available
        </span>
        <span>
          <strong>
            {data.resources.reduce(
              (sum, r) => sum + (r.available_capacity || 0),
              0,
            )}
          </strong>{" "}
          available capacity
        </span>
        <span className="synthetic-label">SYNTHETIC INVENTORY</span>
      </div>
      <Panel>
        <div className="filter-bar">
          <SearchBox
            value={search}
            onChange={setSearch}
            placeholder="Search resources"
          />
          <select
            aria-label="Resource type filter"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="all">All resource types</option>
            {["rescue", "medical", "fire", "logistics"].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
          <select
            aria-label="Resource status filter"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All statuses</option>
            {["available", "assigned", "unavailable"].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Resource</th>
                <th>Availability</th>
                <th>Capacity</th>
                <th>Response time</th>
                <th>Coordinates</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice((page - 1) * 8, page * 8).map((r) => (
                <tr key={r.id}>
                  <td>
                    <button
                      className="row-title text-button"
                      onClick={() => setSelected(r)}
                    >
                      {r.name}
                    </button>
                    <span className="row-sub">
                      {label(r.type)} · v{r.version}
                    </span>
                  </td>
                  <td>
                    <Badge value={r.status} />
                  </td>
                  <td>
                    <strong>{r.available_capacity}</strong>
                    <span className="muted"> / {r.capacity}</span>
                    <div className="capacity-bar">
                      <i
                        style={{
                          width: `${(r.available_capacity / r.capacity) * 100}%`,
                        }}
                      />
                    </div>
                  </td>
                  <td>{r.estimated_response_time} min</td>
                  <td>
                    {r.coordinates.lat.toFixed(3)},{" "}
                    {r.coordinates.lng.toFixed(3)}
                  </td>
                  <td>
                    <Button
                      className="secondary small"
                      disabled={role === "viewer"}
                      onClick={() => setEdit(r)}
                    >
                      <Pencil size={14} />
                      Edit
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty />}
        </div>
        <Pagination page={page} setPage={setPage} total={rows.length} />
      </Panel>
      {edit !== undefined && (
        <ResourceForm
          resource={edit || undefined}
          onClose={() => setEdit(undefined)}
        />
      )}{" "}
      {selected && (
        <Dialog title={selected.name} onClose={() => setSelected(null)}>
          <Badge value={selected.status} />
          <p className="muted">
            {label(selected.type)} · version {selected.version}
          </p>
          <KeyValue
            label="Available capacity"
            value={`${selected.available_capacity} / ${selected.capacity}`}
          />
          <KeyValue
            label="Response time"
            value={`${selected.estimated_response_time} min`}
          />
          <h3>Approved mission assignments</h3>
          {assignments.length ? (
            assignments.map((a: Row, i: number) => (
              <div className="assignment-card" key={i}>
                <Link
                  to={`/missions/${a.mission_id}`}
                  onClick={() => setSelected(null)}
                >
                  Mission {shortId(a.mission_id)}
                </Link>
                <p>
                  {data.incidents.find((x) => x.id === a.incident_id)?.title ||
                    a.incident_id}{" "}
                  · capacity {a.capacity}
                </p>
                <small>
                  {time(a.start_at)} → {time(a.end_at)}
                </small>
              </div>
            ))
          ) : (
            <Empty
              title="No approved assignments"
              description="Proposed assignments do not dispatch or reserve real resources."
            />
          )}
        </Dialog>
      )}
    </>
  );
}
