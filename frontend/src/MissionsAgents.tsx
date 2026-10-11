import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  Plus,
  ArrowUpRight,
  RefreshCw,
  Check,
  X,
  GitBranch,
  ShieldCheck,
  Bot,
  Play,
  Eye,
  TriangleAlert,
  Route as RouteIcon,
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

export function Missions() {
  const { data, act, busy, role } = useStore(),
    navigate = useNavigate();
  const [params] = useSearchParams(),
    [status, setStatus] = useState(params.get("status") || "all"),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(1);
  const rows = sortNewest(data.missions).filter(
    (m) =>
      (status === "all" || m.status === status) &&
      `${m.id} ${m.rationale}`.toLowerCase().includes(search.toLowerCase()),
  );
  const generate = () =>
    act("/missions/generate", {}, "POST", "Mission proposal generated")
      .then((m) => navigate(`/missions/${m.id}`))
      .catch(() => {});
  return (
    <>
      <PageHeading
        eyebrow="HUMAN-APPROVED COORDINATION"
        title="Mission planner"
        description="Constraint-aware proposals. Explainable alternatives. Decisions that remain yours."
        actions={
          <Button
            className="primary"
            disabled={role === "viewer"}
            busy={busy}
            onClick={generate}
          >
            <Plus size={17} />
            Generate Plan
          </Button>
        }
      />
      <div className="notice">
        <ShieldCheck size={19} />
        <div>
          <strong>Every mission is a simulated proposal until approved.</strong>
          <p>
            Server-side validation checks current input versions, capacity and
            resource exclusivity. Approval does not dispatch real resources.
          </p>
        </div>
      </div>
      <div className="page-stat-strip">
        <span>
          <RouteIcon size={17} />
          <strong>{data.missions.length}</strong> proposals
        </span>
        <span>
          <strong>
            {data.missions.filter((m) => m.status === "pending_review").length}
          </strong>{" "}
          pending review
        </span>
        <span>
          <strong>
            {data.missions.filter((m) => m.status === "approved").length}
          </strong>{" "}
          approved
        </span>
        <span>
          <strong>
            {data.missions.filter((m) => m.status === "stale").length}
          </strong>{" "}
          stale
        </span>
      </div>
      <Panel>
        <div className="filter-bar">
          <SearchBox
            value={search}
            onChange={(v) => {
              setSearch(v);
              setPage(1);
            }}
            placeholder="Search proposals"
          />
          <select
            aria-label="Mission status filter"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="all">All statuses</option>
            {[
              "pending_review",
              "approved",
              "rejected",
              "stale",
              "infeasible",
            ].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        </div>
        {rows.length ? (
          <div className="mission-grid">
            {rows.slice((page - 1) * 6, page * 6).map((m) => (
              <Link
                key={m.id}
                className="mission-card"
                to={`/missions/${m.id}`}
              >
                <div>
                  <span>PROPOSAL {shortId(m.id).toUpperCase()}</span>
                  <Badge value={m.status} />
                </div>
                <h3>
                  Coordinated response <span>v{m.proposal_version}</span>
                </h3>
                <p>{m.rationale}</p>
                <div className="mission-meta">
                  <span>{m.incident_ids?.length || 0} incidents</span>
                  <span>{m.assignments?.length || 0} assignments</span>
                  <span>{m.conflicts?.length || 0} conflicts</span>
                </div>
                <footer>
                  <time>{time(m.created_at)}</time>
                  <span>
                    Review proposal <ArrowUpRight size={15} />
                  </span>
                </footer>
              </Link>
            ))}
          </div>
        ) : (
          <Empty
            title="No matching proposals"
            description="Generate a plan from the current shared operational state."
          />
        )}
        <Pagination
          page={page}
          setPage={setPage}
          total={rows.length}
          size={6}
        />
      </Panel>
    </>
  );
}

export function MissionDetail() {
  const { id } = useParams(),
    navigate = useNavigate();
  const { data, act, busy, role, request } = useStore();
  const [decision, setDecision] = useState<"reject" | "revision" | null>(null),
    [alternative, setAlternative] = useState(""),
    [tab, setTab] = useState("rationale"),
    [history, setHistory] = useState<Row[]>([]),
    [historyTotal, setHistoryTotal] = useState(0),
    [historyPage, setHistoryPage] = useState(1),
    [historyLoading, setHistoryLoading] = useState(true),
    [historyError, setHistoryError] = useState(""),
    [historyReload, setHistoryReload] = useState(0);
  useEffect(() => {
    setHistoryPage(1);
    setAlternative("");
  }, [id]);
  useEffect(() => {
    if (!id) return;
    let active = true;
    setHistoryLoading(true);
    request(
      `/missions/${id}/history?page=${historyPage}&page_size=10&sort=-timestamp`,
    )
      .then((result) => {
        if (active) {
          setHistory(result.items);
          setHistoryTotal(result.total);
          setHistoryError("");
        }
      })
      .catch((failure) => {
        if (active) setHistoryError(failure.message);
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id, historyPage, request, data.audit[0]?.id, historyReload]);
  const mission = data.missions.find((m) => m.id === id);
  if (!mission) return <Empty title="Proposal not found" />;
  const currentConflicts = mission.current_conflicts ?? mission.conflicts ?? [];
  const isCommander = ["commander", "administrator"].includes(role);
  const alternatives: Row[] = mission.alternatives || [];
  const selected = alternatives.find((a) => a.id === alternative);
  const canApprove =
    isCommander &&
    mission.status === "pending_review" &&
    !currentConflicts.length &&
    (!selected || selected.status !== "infeasible") &&
    (!selected || selected.assignments?.length > 0);
  const assignments = selected?.assignments || mission.assignments || [];
  const regenerate = () =>
    act(
      `/missions/${id}/regenerate`,
      {},
      "POST",
      "Current-state proposal generated",
    )
      .then((m) => navigate(`/missions/${m.id}`))
      .catch(() => {});
  const submitDecision = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const text = new FormData(e.currentTarget).get("reason");
    act(
      `/missions/${id}/${decision === "reject" ? "reject" : "request-revision"}`,
      {
        expected_version: mission.proposal_version,
        ...(decision === "reject" ? { reason: text } : { comment: text }),
      },
      "POST",
      decision === "reject"
        ? "Proposal rejected with recorded reason"
        : "Revision requested and new version generated",
    )
      .then((m) => {
        setDecision(null);
        if (decision === "revision" && m.id) navigate(`/missions/${m.id}`);
      })
      .catch(() => {});
  };
  return (
    <>
      <Link className="back-link" to="/missions">
        ← Mission planner
      </Link>
      <PageHeading
        eyebrow={`PROPOSAL ${shortId(mission.id).toUpperCase()} / VERSION ${mission.proposal_version}`}
        title="Coordinated response plan"
        description="Review the evidence, constraints and trade-offs before making a simulated decision."
        actions={
          <Button
            className="secondary"
            disabled={role === "viewer"}
            busy={busy}
            onClick={regenerate}
          >
            <RefreshCw size={16} />
            Regenerate Plan
          </Button>
        }
      />
      <div className="detail-top-strip">
        <Badge value={mission.status} />
        <span className="synthetic-label">SIMULATED MISSION</span>
        <span>Created {time(mission.created_at)}</span>
        <span>
          {mission.incident_ids?.length || 0} incidents ·{" "}
          {mission.assignments?.length || 0} assignments
        </span>
      </div>
      {mission.status === "stale" && (
        <div className="warning-banner">
          <TriangleAlert size={19} />
          <div>
            <strong>This proposal has stale inputs.</strong>
            <p>
              Operational state has changed. Regenerate to review a current
              proposal; approval is blocked.
            </p>
          </div>
        </div>
      )}
      {mission.status === "infeasible" && (
        <div className="warning-banner">
          <TriangleAlert size={19} />
          <div>
            <strong>No feasible plan was found.</strong>
            <p>
              Review constraints and inventory before regenerating. No resources
              have been fabricated.
            </p>
          </div>
        </div>
      )}
      <div className="mission-detail-grid">
        <div>
          <Panel
            title="Proposed assignments"
            description="Exclusive time windows · validated capacity"
            action={
              <Badge value={assignments.length ? "proposed" : "infeasible"} />
            }
          >
            {assignments.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Incident</th>
                      <th>Resource</th>
                      <th>Capacity</th>
                      <th>Window</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assignments.map((a: Row, index: number) => (
                      <tr key={index}>
                        <td>
                          <Link
                            className="row-title"
                            to={`/incidents/${a.incident_id}`}
                          >
                            {data.incidents.find((i) => i.id === a.incident_id)
                              ?.title || shortId(a.incident_id)}
                          </Link>
                        </td>
                        <td>
                          {data.resources.find((r) => r.id === a.resource_id)
                            ?.name || shortId(a.resource_id)}
                        </td>
                        <td>{a.capacity}</td>
                        <td>
                          {time(a.start_at)}
                          <span className="row-sub">
                            until {time(a.end_at)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="No feasible assignments"
                description="Inspect the conflicts and warnings below."
              />
            )}
          </Panel>
          <Panel
            title="Conflicts & validation"
            description="Deterministic hard constraints remain authoritative"
          >
            {currentConflicts.length ? (
              currentConflicts.map((c: Row, i: number) => (
                <div className="conflict-card" key={i}>
                  <TriangleAlert size={19} />
                  <div>
                    <strong>{label(c.type)}</strong>
                    <p>{c.message}</p>
                    {c.resource_id && (
                      <small>
                        Resource:{" "}
                        {data.resources.find((r) => r.id === c.resource_id)
                          ?.name || c.resource_id}
                      </small>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="validation-ok">
                <ShieldCheck size={22} />
                <div>
                  <strong>No conflicts in this proposal</strong>
                  <p>
                    Approval performs a fresh transaction-safe validation
                    against current state.
                  </p>
                </div>
              </div>
            )}
            {(mission.warnings || []).map((warning: string, index: number) => (
              <p className="warning-note" key={index}>
                {warning}
              </p>
            ))}
          </Panel>
          <Panel>
            <div
              className="tabs"
              role="tablist"
              aria-label="Proposal explanation"
            >
              {[
                ["rationale", "Rationale"],
                ["versions", "Input versions"],
                ["history", "Decision history"],
              ].map(([key, title]) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                >
                  {title}
                </button>
              ))}
            </div>
            <div className="tab-content">
              {tab === "rationale" ? (
                <>
                  <h3>Why this plan?</h3>
                  <p>{mission.rationale}</p>
                  <p className="muted">
                    Resource capacity uses deterministic rules and synthetic
                    evidence. Unknown source values are retained with explicit
                    warnings. This is a decision-support recommendation.
                  </p>
                  {mission.incident_ids?.map((incidentId: string) => {
                    const incident = data.incidents.find(
                      (i) => i.id === incidentId,
                    );
                    return incident ? (
                      <div className="key-value" key={incidentId}>
                        <Link to={`/incidents/${incident.id}`}>
                          {incident.title}
                        </Link>
                        <Badge value={incident.priority_band} />
                      </div>
                    ) : null;
                  })}
                </>
              ) : tab === "versions" ? (
                <>
                  <h3>Reproducible input references</h3>
                  <pre>{JSON.stringify(mission.input_versions, null, 2)}</pre>
                  <p className="muted">
                    Material input changes invalidate pending proposals. The
                    server compares these versions again at approval.
                  </p>
                </>
              ) : (
                <>
                  {historyError ? (
                    <div className="error-banner" role="alert">
                      <span>
                        Unable to load decision history: {historyError}
                      </span>
                      <Button
                        onClick={() => setHistoryReload(historyReload + 1)}
                      >
                        Retry history
                      </Button>
                    </div>
                  ) : historyLoading ? (
                    <p className="muted" aria-live="polite">
                      Loading persisted decisions…
                    </p>
                  ) : (
                    <Activity rows={history} />
                  )}
                  {historyTotal > 10 && (
                    <Pagination
                      page={historyPage}
                      setPage={setHistoryPage}
                      total={historyTotal}
                      size={10}
                    />
                  )}
                </>
              )}
            </div>
          </Panel>
        </div>
        <div>
          <Panel
            title="Compare Alternatives"
            description="Distinct assignments and their trade-offs"
          >
            <label className="select-label">
              Plan to inspect
              <select
                aria-label="Compare alternatives"
                value={alternative}
                onChange={(e) => setAlternative(e.target.value)}
              >
                <option value="">Recommended proposal</option>
                {alternatives.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </select>
            </label>
            {selected ? (
              <>
                <h3>{selected.label}</h3>
                <p>{selected.trade_off || selected.rationale}</p>
                <Badge value={selected.status || "feasible"} />
              </>
            ) : (
              <p className="muted">
                The recommended proposal prioritizes current risk while
                respecting available resources.
              </p>
            )}
            {!alternatives.length && (
              <p className="warning-note">
                No distinct feasible alternative is available for this state.
              </p>
            )}
          </Panel>
          <Panel
            title="Human review"
            description="Commander or administrator approval required"
          >
            <KeyValue
              label="Proposal version"
              value={`v${mission.proposal_version}`}
            />
            <KeyValue label="Status" value={<Badge value={mission.status} />} />
            {mission.approver && (
              <KeyValue label="Approved by" value={mission.approver} />
            )}
            <div className="decision-actions">
              <Button
                className="primary"
                disabled={!canApprove}
                busy={busy}
                onClick={() =>
                  act(
                    `/missions/${id}/approve`,
                    {
                      expected_version: mission.proposal_version,
                      ...(alternative ? { alternative_id: alternative } : {}),
                    },
                    "POST",
                    "Simulated proposal approved; audit recorded",
                  ).catch(() => {})
                }
              >
                <Check size={17} />
                Approve proposal
              </Button>
              <Button
                className="secondary"
                disabled={!isCommander || mission.status !== "pending_review"}
                onClick={() => setDecision("revision")}
              >
                <GitBranch size={17} />
                Request revision
              </Button>
              <Button
                className="danger-outline"
                disabled={!isCommander || mission.status !== "pending_review"}
                onClick={() => setDecision("reject")}
              >
                <X size={17} />
                Reject proposal
              </Button>
            </div>
            <p className="muted small-text">
              Approval never triggers a real-world deployment. Stale, invalid or
              infeasible proposals cannot be approved.
            </p>
            {!isCommander && (
              <p className="warning-note">
                Your {role} role cannot make proposal decisions.
              </p>
            )}
          </Panel>
        </div>
      </div>
      {decision && (
        <Dialog
          title={
            decision === "reject"
              ? "Reject proposal"
              : "Request a revised proposal"
          }
          onClose={() => setDecision(null)}
        >
          <form className="form" onSubmit={submitDecision}>
            <label>
              {decision === "reject" ? "Rejection reason" : "Revision comment"}
              <textarea
                name="reason"
                aria-label={
                  decision === "reject"
                    ? "Rejection reason"
                    : "Revision comment"
                }
                required
                minLength={3}
                maxLength={1000}
                rows={4}
                placeholder="Explain your decision for the audit record."
                autoFocus
              />
            </label>
            <div className="dialog-actions">
              <Button
                className="secondary"
                type="button"
                onClick={() => setDecision(null)}
              >
                Cancel
              </Button>
              <Button
                className={decision === "reject" ? "danger" : "primary"}
                type="submit"
                busy={busy}
              >
                {decision === "reject"
                  ? "Confirm rejection"
                  : "Request revision"}
              </Button>
            </div>
          </form>
        </Dialog>
      )}
    </>
  );
}

const agentIcons: Record<string, string> = {
  vision: "Imagery assessment",
  incident: "Report extraction",
  weather: "Weather & terrain",
  resource: "Capacity & availability",
  risk: "Normalized risk scoring",
  coordinator: "Validated proposal generation",
};
export function Agents() {
  const { data, act, busy, role } = useStore();
  const [params] = useSearchParams(),
    [selected, setSelected] = useState<string | null>(params.get("agent")),
    [runId, setRunId] = useState<string | null>(params.get("run")),
    [filter, setFilter] = useState("all"),
    [page, setPage] = useState(1);
  const runs = sortNewest(data.agent_runs).filter(
    (run) =>
      (!selected || run.agent_id === selected) &&
      (filter === "all" || run.status === filter),
  );
  const run = data.agent_runs.find((r) => r.id === runId);
  const active = data.agents.find((a) => a.id === selected);
  return (
    <>
      <PageHeading
        eyebrow="MULTI-AGENT INTELLIGENCE"
        title="Agent center"
        description="Six specialized perspectives connected through one shared operational state."
        actions={
          <Button
            className="primary"
            disabled={role === "viewer"}
            busy={busy}
            onClick={() =>
              act(
                "/agents/runs",
                {},
                "POST",
                "Full analysis cycle submitted",
              ).catch(() => {})
            }
          >
            <Play size={16} />
            Run all agents
          </Button>
        }
      />
      <div className="agent-grid">
        {data.agents.map((agent) => (
          <button
            className={`agent-card ${selected === agent.id ? "selected" : ""}`}
            key={agent.id}
            onClick={() => {
              setSelected(selected === agent.id ? null : agent.id);
              setPage(1);
            }}
          >
            <div className="agent-card-top">
              <span className="agent-icon">
                <Bot size={24} />
              </span>
              <Badge value={agent.status || "ready"} />
            </div>
            <h3>{agent.name || label(agent.id)}</h3>
            <p>{agent.description || agentIcons[agent.id]}</p>
            <div>
              <span>Deterministic / synthetic</span>
              <ArrowUpRight size={16} />
            </div>
          </button>
        ))}
      </div>
      {active && (
        <Panel
          title={active.name || label(active.id)}
          description={active.description || agentIcons[active.id]}
          action={
            <Button
              className="secondary"
              disabled={role === "viewer"}
              busy={busy}
              onClick={() =>
                act(
                  "/agents/runs",
                  { agent_id: active.id },
                  "POST",
                  `${active.name || label(active.id)} run submitted`,
                ).catch(() => {})
              }
            >
              <Play size={15} />
              Run selected agent
            </Button>
          }
        >
          <p className="muted">
            Uses structured inputs from persisted state. Outputs include
            confidence, warnings, input versions and an auditable result;
            deterministic synthetic adapters keep the demo independent of
            external providers.
          </p>
          <Button className="text-button" onClick={() => setSelected(null)}>
            Clear agent filter
          </Button>
        </Panel>
      )}
      <Panel
        title="Execution history"
        description="Inspect inputs, outputs, warnings and eligible retries"
        action={
          <select
            aria-label="Agent run status filter"
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="all">All run statuses</option>
            {["queued", "running", "completed", "failed"].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        }
      >
        {runs.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Agent / run</th>
                  <th>State</th>
                  <th>Confidence</th>
                  <th>Started</th>
                  <th>Warnings</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.slice((page - 1) * 8, page * 8).map((r) => (
                  <tr key={r.id}>
                    <td>
                      <button
                        className="row-title text-button"
                        onClick={() => setRunId(r.id)}
                      >
                        {data.agents.find((a) => a.id === r.agent_id)?.name ||
                          label(r.agent_id)}
                      </button>
                      <span className="row-sub">{shortId(r.id)}</span>
                    </td>
                    <td>
                      <Badge value={r.status} />
                    </td>
                    <td>
                      {r.confidence == null
                        ? "Unknown"
                        : `${Math.round(r.confidence * 100)}%`}
                    </td>
                    <td>{time(r.started_at)}</td>
                    <td>{r.warnings?.length || 0}</td>
                    <td>
                      <Button
                        className="secondary small"
                        onClick={() => setRunId(r.id)}
                      >
                        <Eye size={14} />
                        Inspect run
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No matching agent runs" />
        )}
        <Pagination page={page} setPage={setPage} total={runs.length} />
      </Panel>
      {run && (
        <Dialog
          title={`${label(run.agent_id)} · run ${shortId(run.id)}`}
          onClose={() => setRunId(null)}
        >
          <div className="detail-top-strip">
            <Badge value={run.status} />
            <span>
              {run.confidence == null
                ? "Unknown confidence"
                : `${Math.round(run.confidence * 100)}% confidence`}
            </span>
          </div>
          <KeyValue label="Started" value={time(run.started_at)} />
          <KeyValue label="Completed" value={time(run.completed_at)} />
          {run.incident_id && (
            <DetailLink to={`/incidents/${run.incident_id}`}>
              Related incident
            </DetailLink>
          )}
          {run.error_message && (
            <p className="warning-note">{run.error_message}</p>
          )}
          {(run.warnings || []).map((warning: string, i: number) => (
            <p key={i} className="warning-note">
              {warning}
            </p>
          ))}
          <h3>Structured result</h3>
          <pre>{JSON.stringify(run.result, null, 2)}</pre>
          <details>
            <summary>Input snapshot & references</summary>
            <pre>{JSON.stringify(run.input_snapshot, null, 2)}</pre>
          </details>
          {run.status === "failed" && (
            <Button
              className="primary"
              disabled={role === "viewer"}
              busy={busy}
              onClick={() =>
                act(
                  `/agents/runs/${run.id}/retry`,
                  {},
                  "POST",
                  "Failed run retried",
                )
                  .then((r) => setRunId(r.id))
                  .catch(() => {})
              }
            >
              <RefreshCw size={16} />
              Retry failed run
            </Button>
          )}
        </Dialog>
      )}
    </>
  );
}
