import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  ArrowRight,
  Activity as ActivityIcon,
  Radar,
  ShieldCheck,
  Workflow,
  Radio,
  Bot,
  Boxes,
  Route,
  RefreshCw,
  Play,
  Pause,
  RotateCcw,
  Menu,
  X,
  GitBranch,
  CircleDot,
} from "lucide-react";
import { useStore, label, time, sortNewest } from "./state";
import {
  Activity,
  Badge,
  Button,
  DetailLink,
  Dialog,
  Empty,
  PageHeading,
  Panel,
} from "./ui";
import { Brand } from "./App";
import MapView from "./MapView";

export function Landing() {
  const { act, busy } = useStore(),
    navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const run = () =>
    act(
      "/simulator/scenarios/kolkata-flood/load",
      { confirmed: true },
      "POST",
      "Kolkata flood scenario loaded",
    )
      .then(() => navigate("/simulator"))
      .catch(() => {});
  const features = [
    [
      "A common operating picture",
      "Incidents, evidence and resources stay connected in one versioned operational state.",
      Radar,
    ],
    [
      "Six agents. One coordinated plan.",
      "Specialized agents analyze conditions while deterministic rules validate every proposal.",
      Bot,
    ],
    [
      "Human judgment comes first",
      "Inspect the rationale, compare alternatives, and approve simulated missions with a full audit trail.",
      ShieldCheck,
    ],
  ] as const;
  return (
    <>
      <header className="landing-header">
        <Brand />
        <nav className={menu ? "open" : ""} aria-label="Landing navigation">
          <a href="#features" onClick={() => setMenu(false)}>
            Features
          </a>
          <a href="#architecture" onClick={() => setMenu(false)}>
            Architecture
          </a>
          <Link to="/incidents">Incidents</Link>
          <Link to="/missions">Mission planner</Link>
        </nav>
        <div>
          <Link className="button landing-launch" to="/dashboard">
            Launch workspace <ArrowUpRight size={16} />
          </Link>
          <button
            className="icon-button mobile-toggle"
            aria-label="Toggle mobile menu"
            onClick={() => setMenu(!menu)}
          >
            {menu ? <X size={21} /> : <Menu size={21} />}
          </button>
        </div>
      </header>
      <section className="hero">
        <div className="hero-copy">
          <div className="pill">
            <span className="status-dot" /> SYNAPSE 1.0 · COORDINATION PLATFORM
          </div>
          <h1>
            When every second
            <br />
            matters,
            <br />
            <em>connect the response.</em>
          </h1>
          <p>
            A shared picture. Coordinated resources. Clear decisions.
            <br />
            MissionSync brings multi-agent intelligence and human command
            together for emergency response simulation.
          </p>
          <div className="hero-actions">
            <Link className="button primary" to="/dashboard">
              Launch Dashboard <ArrowUpRight size={18} />
            </Link>
            <Button className="button secondary" busy={busy} onClick={run}>
              <Play size={16} />
              Run Live Demo
            </Button>
          </div>
          <div className="hero-note">
            <ShieldCheck size={16} />
            <span>
              Synthetic scenarios. Explainable plans. Human-approved decisions.
            </span>
          </div>
        </div>
        <div
          className="hero-visual"
          aria-label="Illustration of six analytical agents connected to human command"
        >
          <div className="visual-grid" />
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="center-core">
            <ActivityIcon size={39} />
            <strong>MISSION SYNC</strong>
            <span>SHARED OPERATIONAL STATE</span>
          </div>
          {[
            ["Vision", "01", "vision"],
            ["Incident", "02", "incident"],
            ["Weather / Terrain", "03", "weather"],
            ["Resource", "04", "resource"],
            ["Risk / Priority", "05", "risk"],
            ["Coordinator", "06", "coordinator"],
          ].map(([name, id, pos]) => (
            <div key={id} className={`orbit-node ${pos}`}>
              <span>{id}</span>
              <strong>{name}</strong>
              <i />
            </div>
          ))}
          <div className="visual-caption">
            <span className="status-dot" />
            INTELLIGENCE → COORDINATION → HUMAN REVIEW
          </div>
        </div>
      </section>
      <div className="landing-strip">
        <span>BUILT FOR THE COMPLETE RESPONSE LOOP</span>
        <div>
          <Radio size={17} />
          Ingest
        </div>
        <ArrowRight size={15} />
        <div>
          <Radar size={17} />
          Analyze
        </div>
        <ArrowRight size={15} />
        <div>
          <Route size={17} />
          Coordinate
        </div>
        <ArrowRight size={15} />
        <div>
          <ShieldCheck size={17} />
          Human review
        </div>
      </div>
      <section className="landing-section" id="features">
        <div className="section-title">
          <div>
            <div className="eyebrow">COORDINATION, CONNECTED</div>
            <h2>
              From fragmented signals
              <br />
              to a shared decision.
            </h2>
          </div>
          <a className="text-link" href="#architecture">
            Explore the architecture <ArrowUpRight size={16} />
          </a>
        </div>
        <div className="feature-grid">
          {features.map(([title, description, Icon], i) => (
            <article key={title}>
              <span className="feature-number">0{i + 1}</span>
              <Icon size={29} />
              <h3>{title}</h3>
              <p>{description}</p>
              <Link
                className="text-link"
                to={["/map", "/agents", "/missions"][i]}
              >
                Explore {["the map", "agents", "mission planning"][i]}{" "}
                <ArrowUpRight size={15} />
              </Link>
            </article>
          ))}
        </div>
      </section>
      <section
        id="architecture"
        className="landing-section architecture-section"
      >
        <div className="eyebrow">THE SYSTEM BEHIND THE DECISION</div>
        <h2>
          One state. Six perspectives.
          <br />A traceable response.
        </h2>
        <p>
          Every material change triggers analysis, priority scoring and
          constraint checks.
          <br />
          Proposals remain subject to human review and server-side validation.
        </p>
        <div className="architecture-flow">
          {[
            ["01", "Synthetic inputs", "Reports · imagery · weather", Radio],
            ["02", "Agent analysis", "Evidence · confidence · risk", Bot],
            [
              "03",
              "Shared state & planner",
              "Versions · capacity · conflicts",
              GitBranch,
            ],
            [
              "04",
              "Human review",
              "Alternatives · decisions · audit",
              ShieldCheck,
            ],
          ].map(([step, title, description, Icon]: any) => (
            <div key={step}>
              <Icon size={25} />
              <small>{step}</small>
              <h3>{title}</h3>
              <p>{description}</p>
            </div>
          ))}
        </div>
        <div className="architecture-note">
          <CircleDot size={16} />
          Deterministic constraints are authoritative. Optional AI providers are
          not required for the core demo.
        </div>
      </section>
      <section className="landing-cta">
        <div>
          <div className="eyebrow">YOUR OPERATING PICTURE STARTS HERE</div>
          <h2>See the coordination loop in action.</h2>
          <p>
            Load the Kolkata flood scenario and follow an incident from analysis
            to review.
          </p>
        </div>
        <Button className="primary" busy={busy} onClick={run}>
          Run Live Demo <ArrowUpRight size={18} />
        </Button>
      </section>
      <footer className="landing-footer">
        <Brand />
        <span>Built by Synaptic Surge · IEM Kolkata</span>
        <span>Decision-support simulation · No real dispatch</span>
      </footer>
    </>
  );
}

export function Dashboard() {
  const { data, act, busy, refresh, role } = useStore();
  const [reset, setReset] = useState(false),
    [range, setRange] = useState("all");
  const summary = data.summary;
  const metrics = [
    [
      "Active incidents",
      summary.incident_total ?? data.incidents.length,
      "/incidents",
      Radio,
      "All reported incidents",
    ],
    [
      "Critical priority",
      summary.critical_incidents ?? 0,
      "/incidents?priority=critical",
      Radar,
      "Immediate review recommended",
    ],
    [
      "Resources available",
      summary.available_resources ?? 0,
      "/resources?status=available",
      Boxes,
      `${summary.assigned_resources ?? 0} currently assigned`,
    ],
    [
      "Pending review",
      summary.pending_approvals ?? 0,
      "/missions?status=pending_review",
      ShieldCheck,
      `${summary.active_missions ?? 0} approved simulated missions`,
    ],
  ] as const;
  const ranked = [...data.incidents]
    .filter((i) => i.status !== "resolved")
    .sort((a, b) => b.priority_score - a.priority_score)
    .slice(0, 5);
  const audit = sortNewest(data.audit).filter(
    (row) =>
      range === "all" ||
      Date.now() - new Date(row.timestamp).getTime() <= Number(range) * 3600000,
  );
  const counts = ["critical", "high", "medium", "low"].map((band) => ({
    band,
    count: data.incidents.filter((i) => i.priority_band === band).length,
  }));
  return (
    <>
      <PageHeading
        eyebrow="OPERATIONAL OVERVIEW"
        title="Command dashboard"
        description="A connected view of incidents, resources and decisions in your simulation."
        actions={
          <>
            <Button
              className="secondary"
              aria-label="Refresh dashboard"
              onClick={() => refresh().catch(() => {})}
            >
              <RefreshCw size={16} />
            </Button>
            <Button
              className="secondary"
              busy={busy}
              disabled={role === "viewer"}
              onClick={() =>
                act(
                  "/agents/runs",
                  {},
                  "POST",
                  "Analysis jobs submitted",
                ).catch(() => {})
              }
            >
              <ActivityIcon size={16} />
              Run Analysis
            </Button>
          </>
        }
      />
      <div className="context-strip">
        <span>
          <span className="status-dot" />
          SYNTHETIC SCENARIO
        </span>
        <strong>
          {label(data.simulation.scenario_id || "No scenario loaded")}
        </strong>
        <div>
          <Badge value={data.simulation.paused ? "paused" : "running"} />
          <button
            disabled={role === "viewer" || busy}
            onClick={() =>
              act(
                `/simulator/${data.simulation.paused ? "resume" : "pause"}`,
                {},
                "POST",
                data.simulation.paused
                  ? "Simulation resumed"
                  : "Simulation paused",
              ).catch(() => {})
            }
          >
            {data.simulation.paused ? <Play size={14} /> : <Pause size={14} />}{" "}
            {data.simulation.paused ? "Resume" : "Pause"}
          </button>
          <button
            disabled={role !== "administrator"}
            onClick={() => setReset(true)}
            title={
              role !== "administrator"
                ? "Administrator role required"
                : "Reset simulation"
            }
          >
            <RotateCcw size={14} />
            Reset
          </button>
        </div>
      </div>
      <div className="metrics-grid">
        {metrics.map(([name, value, path, Icon, note]) => (
          <Link className="metric-card" to={path} key={name}>
            <div>
              <span>{name}</span>
              <Icon size={19} />
            </div>
            <strong>{value}</strong>
            <p>
              {note}
              <ArrowUpRight size={15} />
            </p>
          </Link>
        ))}
      </div>
      <div className="dashboard-columns">
        <Panel
          title="Operational picture"
          description="Incidents and resources · geographic coordinates"
          action={<DetailLink to="/map">Open map</DetailLink>}
        >
          <MapView
            incidents={data.incidents}
            resources={data.resources}
            compact
          />
        </Panel>
        <Panel
          title="Priority queue"
          description="Ranked by normalized risk factors"
          action={<DetailLink to="/incidents">View all</DetailLink>}
        >
          {ranked.length ? (
            <div className="priority-list">
              {ranked.map((incident, i) => (
                <Link to={`/incidents/${incident.id}`} key={incident.id}>
                  <span className="rank">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <strong>{incident.title}</strong>
                    <p>
                      {label(incident.category)} ·{" "}
                      {incident.people_at_risk ?? "Unknown"} people at risk
                    </p>
                  </div>
                  <div>
                    <Badge value={incident.priority_band} />
                    <small>
                      {Number(incident.priority_score).toFixed(1)} score
                    </small>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <Empty />
          )}
        </Panel>
      </div>
      <div className="dashboard-bottom">
        <Panel
          title="Priority distribution"
          description="Current incident bands"
        >
          <div className="distribution">
            {counts.map(({ band, count }) => (
              <div key={band}>
                <span>{label(band)}</span>
                <div className="bar-track">
                  <i
                    className={band}
                    style={{
                      width: `${(count / Math.max(1, data.incidents.length)) * 100}%`,
                    }}
                  />
                </div>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
          <p className="muted panel-note">
            Scores reflect configurable, normalized risk factors. Unknown inputs
            remain explicit.
          </p>
        </Panel>
        <Panel
          title="Agent health"
          description="Six logical agents · deterministic synthetic adapters"
          action={<DetailLink to="/agents">Inspect</DetailLink>}
        >
          <div className="agent-mini">
            {data.agents.map((agent) => (
              <Link to={`/agents?agent=${agent.id}`} key={agent.id}>
                <Bot size={17} />
                <span>{agent.name || label(agent.id)}</span>
                <Badge value={agent.status || "ready"} />
              </Link>
            ))}
          </div>
        </Panel>
        <Panel
          title="Recent activity"
          description="Persisted actions and human decisions"
          action={
            <select
              aria-label="Activity time range"
              value={range}
              onChange={(e) => setRange(e.target.value)}
            >
              <option value="all">All time</option>
              <option value="1">Last hour</option>
              <option value="24">Last 24 hours</option>
            </select>
          }
        >
          <Activity rows={audit.slice(0, 4)} />
          <DetailLink to="/audit">Open audit log</DetailLink>
        </Panel>
      </div>
      {reset && (
        <Dialog
          title="Reset synthetic scenario?"
          onClose={() => setReset(false)}
        >
          <p>
            This restores the selected simulation's incidents, resources and
            proposals. Previous audit actions remain recorded.
          </p>
          <div className="dialog-actions">
            <Button className="secondary" onClick={() => setReset(false)}>
              Cancel
            </Button>
            <Button
              className="danger"
              busy={busy}
              onClick={() =>
                act(
                  "/simulator/reset",
                  { scenario_id: data.simulation.scenario_id, confirmed: true },
                  "POST",
                  "Scenario reset",
                )
                  .then(() => setReset(false))
                  .catch(() => {})
              }
            >
              Confirm reset
            </Button>
          </div>
        </Dialog>
      )}
    </>
  );
}
