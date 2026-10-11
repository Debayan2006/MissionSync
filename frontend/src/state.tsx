import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

export type Row = Record<string, any>;
export type Snapshot = {
  incidents: Row[];
  resources: Row[];
  missions: Row[];
  agents: Row[];
  agent_runs: Row[];
  audit: Row[];
  settings: Row;
  simulation: Row;
  summary: Row;
};
const empty: Snapshot = {
  incidents: [],
  resources: [],
  missions: [],
  agents: [],
  agent_runs: [],
  audit: [],
  settings: {},
  simulation: {},
  summary: {},
};
type Store = {
  data: Snapshot;
  loading: boolean;
  error: string;
  busy: boolean;
  connection: string;
  role: string;
  changeRole: (role: string) => Promise<void>;
  refresh: () => Promise<void>;
  act: (
    path: string,
    body?: any,
    method?: string,
    success?: string,
  ) => Promise<any>;
  request: (path: string, body?: any, method?: string) => Promise<any>;
  notify: (message: string, tone?: string) => void;
  dismissToast: () => void;
  toast: { message: string; tone: string } | null;
};
const Context = createContext<Store>(null!);
export const useStore = () => useContext(Context);
export function Provider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<Snapshot>(empty),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [connection, setConnection] = useState("Connecting"),
    [role, setRole] = useState(
      localStorage.getItem("missionsync.role") || "commander",
    ),
    [toast, setToast] = useState<Store["toast"]>(null);
  const token = useRef(""),
    toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notify = useCallback((message: string, tone = "success") => {
    setToast({ message, tone });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 6000);
  }, []);
  const dismissToast = useCallback(() => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(null);
  }, []);
  const request = useCallback(
    async (path: string, body?: any, method = "GET") => {
      const response = await fetch(`/api/v1${path}`, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token.current
            ? { Authorization: `Bearer ${token.current}` }
            : {}),
        },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
      let result;
      try {
        result = await response.json();
      } catch {
        throw new Error(
          `Service returned ${response.status}; please try again.`,
        );
      }
      if (!response.ok) {
        const fieldMessages = result.error?.fields
          ?.map(
            (field: any) =>
              `${field.field || (field.location || field.loc || []).join(".")}: ${field.message || field.msg}`,
          )
          .join("; ");
        const msg =
          fieldMessages ||
          result.error?.message ||
          result.detail?.message ||
          result.message ||
          result.detail;
        throw new Error(
          typeof msg === "string"
            ? msg
            : Array.isArray(msg)
              ? msg.map((x) => x.msg).join("; ")
              : `Request failed (${response.status}).`,
        );
      }
      return result;
    },
    [],
  );
  const refresh = useCallback(async () => {
    try {
      const state = await request("/state");
      setData({ ...empty, ...state });
      setError("");
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setLoading(false);
    }
  }, [request]);
  const changeRole = useCallback(
    async (next: string) => {
      const session = await request("/auth/demo", { role: next }, "POST");
      token.current = session.token;
      setRole(next);
      localStorage.setItem("missionsync.role", next);
    },
    [request],
  );
  const act = useCallback(
    async (
      path: string,
      body: any = {},
      method = "POST",
      success = "Saved to shared state",
    ) => {
      setBusy(true);
      try {
        if (!token.current) {
          const session = await request("/auth/demo", { role }, "POST");
          token.current = session.token;
        }
        const result = await request(path, body, method);
        await refresh();
        notify(success);
        return result;
      } catch (e) {
        notify((e as Error).message, "error");
        throw e;
      } finally {
        setBusy(false);
      }
    },
    [request, refresh, notify, role],
  );
  useEffect(() => {
    changeRole(role).catch((e) => notify(e.message, "error"));
    refresh().catch(() => {});
    const stream = new EventSource("/api/v1/events/stream");
    let eventTimer: ReturnType<typeof setTimeout> | null = null;
    const update = () => {
      setConnection("Live");
      if (!eventTimer)
        eventTimer = setTimeout(() => {
          eventTimer = null;
          refresh().catch(() => {});
        }, 100);
    };
    stream.onopen = () => setConnection("Live");
    stream.onmessage = update;
    const events = [
      "incident.created",
      "incident.updated",
      "incident.priority_changed",
      "agent.run_started",
      "agent.run_completed",
      "agent.run_failed",
      "resource.status_changed",
      "mission.generated",
      "mission.conflict_detected",
      "mission.approved",
      "mission.rejected",
      "simulation.state_changed",
      "state.updated",
      "weather.updated",
      "resource.created",
      "mission.revision_requested",
      "settings.updated",
      "simulation.error",
      "agent.run_queued",
    ];
    events.forEach((event) => stream.addEventListener(event, update));
    stream.onerror = () => setConnection("Polling fallback");
    const poll = setInterval(
      () => refresh().catch(() => setConnection("Offline")),
      5000,
    );
    return () => {
      stream.close();
      clearInterval(poll);
      if (eventTimer) clearTimeout(eventTimer);
    };
  }, [refresh, changeRole]);
  return (
    <Context.Provider
      value={{
        data,
        loading,
        error,
        busy,
        connection,
        role,
        changeRole,
        refresh,
        act,
        request,
        notify,
        dismissToast,
        toast,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export const label = (value: any) =>
  String(value ?? "Unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
export const time = (value: any) =>
  value
    ? new Date(value).toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata",
        timeZoneName: "short",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Not recorded";
export const shortId = (value: string) => value?.slice(-8) || "—";
export const sortNewest = (rows: Row[]) =>
  [...rows].sort((a, b) =>
    String(b.created_at || b.timestamp || b.updated_at || "").localeCompare(
      String(a.created_at || a.timestamp || a.updated_at || ""),
    ),
  );
