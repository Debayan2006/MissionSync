import { useEffect, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useSearchParams,
} from "react-router-dom";
import {
  Activity,
  LayoutDashboard,
  Map,
  Radio,
  Bot,
  Boxes,
  Route as RouteIcon,
  FlaskConical,
  ScrollText,
  Settings,
  Menu,
  X,
  ChevronDown,
  ArrowUpRight,
  TriangleAlert,
  RefreshCw,
} from "lucide-react";
import { Provider, useStore } from "./state";
import { Landing, Dashboard } from "./DashboardLanding";
import { Incidents, IncidentDetail, Resources } from "./IncidentsResources";
import { Missions, MissionDetail, Agents } from "./MissionsAgents";
import { Simulator, Audit, SettingsPage } from "./SimulatorSettings";
import MapView from "./MapView";
import { PageHeading } from "./ui";

const navigation = [
  ["Overview", "/dashboard", LayoutDashboard],
  ["Incident map", "/map", Map],
  ["Incidents", "/incidents", Radio],
  ["Agents", "/agents", Bot],
  ["Resources", "/resources", Boxes],
  ["Mission planner", "/missions", RouteIcon],
  ["Simulator", "/simulator", FlaskConical],
  ["Audit log", "/audit", ScrollText],
  ["Settings", "/settings", Settings],
] as const;
export function Brand() {
  return (
    <Link className="brand" to="/" aria-label="MissionSync home">
      <span className="brand-symbol">
        <Activity size={25} />
      </span>
      <span>
        Mission<span className="brand-accent">Sync</span>
        <small>SYNAPSE / 1.0</small>
      </span>
    </Link>
  );
}
function MapPage() {
  const { data } = useStore();
  const [params] = useSearchParams();
  return (
    <>
      <PageHeading
        eyebrow="GEOSPATIAL INTELLIGENCE"
        title="Incident map"
        description="A shared operational picture. Select a marker to inspect its incident."
      />
      <MapView
        incidents={data.incidents}
        resources={data.resources}
        focusId={params.get("incident") || undefined}
      />
    </>
  );
}
function Shell() {
  const {
    data,
    loading,
    error,
    connection,
    role,
    changeRole,
    refresh,
    notify,
    dismissToast,
    toast,
  } = useStore();
  const [menu, setMenu] = useState(false);
  const mobileClose = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (menu) mobileClose.current?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menu]);
  const location = useLocation();
  const isLanding = location.pathname === "/";
  const pending = data.summary.pending_approvals || 0;
  return (
    <>
      {!isLanding && (
        <>
          <aside className={`sidebar ${menu ? "is-open" : ""}`}>
            <div className="sidebar-brand-row">
              <Brand />
              <button
                ref={mobileClose}
                className="icon-button mobile-toggle"
                aria-label="Close menu"
                onClick={() => setMenu(false)}
              >
                <X size={20} />
              </button>
            </div>
            <div className="workspace-label">
              COMMAND WORKSPACE <span>DEMO</span>
            </div>
            <nav aria-label="Main navigation">
              {navigation.map(([name, path, Icon]) => (
                <NavLink onClick={() => setMenu(false)} key={path} to={path}>
                  <Icon size={18} />
                  <span>{name}</span>
                  {path === "/missions" && pending > 0 && <b>{pending}</b>}
                </NavLink>
              ))}
            </nav>
            <div className="sidebar-foot">
              <span className="tiny-label">OPERATING ENVIRONMENT</span>
              <p>
                <span className="status-dot" />
                Synthetic simulation
              </p>
              <small>
                Human approval required.
                <br />
                No real-world dispatch.
              </small>
              <Link to="/" className="text-link">
                About MissionSync <ArrowUpRight size={14} />
              </Link>
            </div>
          </aside>
          <div
            className="mobile-backdrop"
            hidden={!menu}
            onClick={() => setMenu(false)}
          />
          <header className="topbar">
            <div className="breadcrumb">
              <button
                className="mobile-toggle icon-button"
                aria-label={menu ? "Close navigation" : "Open navigation"}
                aria-expanded={menu}
                onClick={() => setMenu(!menu)}
              >
                {menu ? <X size={21} /> : <Menu size={21} />}
              </button>
              <span>WORKSPACE</span>
              <i>/</i>
              <strong>
                {navigation.find(([, path]) =>
                  location.pathname.startsWith(path),
                )?.[0] || "Detail"}
              </strong>
            </div>
            <div className="topbar-right">
              <span
                className={`connection ${connection === "Live" ? "live" : ""}`}
              >
                <span className="status-dot" />
                {connection}
              </span>
              <span className="divider" />
              <label className="role-label">
                <span className="avatar">{role[0].toUpperCase()}</span>
                <select
                  aria-label="Demo role"
                  value={role}
                  onChange={(e) =>
                    changeRole(e.target.value)
                      .then(() => notify("Demo role updated"))
                      .catch((e) => notify(e.message, "error"))
                  }
                >
                  <option value="viewer">Viewer</option>
                  <option value="analyst">Analyst</option>
                  <option value="commander">Commander</option>
                  <option value="administrator">Administrator</option>
                </select>
                <ChevronDown size={13} />
              </label>
            </div>
          </header>
        </>
      )}
      <main className={isLanding ? "landing-main" : "workspace-main"}>
        {!isLanding && error && (
          <div className="error-banner" role="alert">
            <TriangleAlert size={18} />
            <span>Unable to load operational state: {error}</span>
            <button onClick={() => refresh().catch(() => {})}>
              <RefreshCw size={15} />
              Retry connection
            </button>
          </div>
        )}
        {!isLanding && loading ? (
          <div className="initial-loading">
            <Activity size={40} className="pulse" />
            <h2>Connecting to shared state</h2>
            <p>Loading incidents, resources and mission proposals…</p>
          </div>
        ) : (
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/incidents/:id" element={<IncidentDetail />} />
            <Route path="/resources" element={<Resources />} />
            <Route path="/missions" element={<Missions />} />
            <Route path="/missions/:id" element={<MissionDetail />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/simulator" element={<Simulator />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route
              path="*"
              element={
                <div className="empty">
                  <h1>Page not found</h1>
                  <Link to="/dashboard">Return to dashboard</Link>
                </div>
              }
            />
          </Routes>
        )}
        {!isLanding && (
          <footer className="workspace-footer">
            <span>MissionSync · SYNAPSE 1.0</span>
            <span>Simulated decisions. Human oversight.</span>
          </footer>
        )}
      </main>
      {toast && (
        <div
          role={toast.tone === "error" ? "alert" : "status"}
          className={`toast ${toast.tone}`}
        >
          <span>{toast.message}</span>
          <button
            aria-label="Dismiss notification"
            onClick={dismissToast}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </>
  );
}
export default function App() {
  return (
    <Provider>
      <Shell />
    </Provider>
  );
}
