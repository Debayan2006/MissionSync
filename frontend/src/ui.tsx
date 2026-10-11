import { useEffect, useRef } from "react";
import {
  X,
  LoaderCircle,
  ChevronLeft,
  ChevronRight,
  Search,
  ArrowUpRight,
  CircleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { label, time, Row } from "./state";
export function Badge({
  value,
  children,
}: {
  value?: any;
  children?: React.ReactNode;
}) {
  return (
    <span className={`badge ${String(value || "neutral").toLowerCase()}`}>
      {children || label(value)}
    </span>
  );
}
export function Button({
  children,
  busy,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  return (
    <button {...props} disabled={props.disabled || busy}>
      {busy ? <LoaderCircle size={16} className="spin" /> : null}
      {children}
    </button>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">{actions}</div>
    </div>
  );
}
export function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-heading">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Empty({
  title = "No results",
  description = "Try changing the filters or load a synthetic scenario.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="empty">
      <CircleAlert size={26} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    const handle = () => closeRef.current();
    dialog.addEventListener("cancel", handle);
    return () => {
      dialog.removeEventListener("cancel", handle);
      dialog.close();
    };
  }, []);
  return (
    <dialog ref={ref} aria-labelledby="dialog-title">
      <div className="dialog-heading">
        <h2 id="dialog-title">{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function SearchBox({
  value,
  onChange,
  placeholder = "Search...",
}: {
  value: string;
  onChange: (s: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="search-box">
      <Search size={17} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
export function Pagination({
  page,
  setPage,
  total,
  size = 8,
}: {
  page: number;
  setPage: (p: number) => void;
  total: number;
  size?: number;
}) {
  const max = Math.max(1, Math.ceil(total / size));
  return (
    <div className="pagination">
      <span>
        {total
          ? `${(page - 1) * size + 1}–${Math.min(total, page * size)} of ${total}`
          : "0 results"}
      </span>
      <div>
        <button
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
        >
          <ChevronLeft size={16} />
        </button>
        <span>
          Page {page} / {max}
        </span>
        <button
          aria-label="Next page"
          disabled={page >= max}
          onClick={() => setPage(page + 1)}
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
export function Activity({ rows }: { rows: Row[] }) {
  return (
    <div className="activity">
      {rows.length ? (
        rows.map((row) => (
          <div className="activity-row" key={row.id}>
            <div className="activity-mark" />
            <div>
              <strong>{label(row.action || row.event_type)}</strong>
              <p>
                {row.reason ||
                  `${label(row.entity_type)} ${row.entity_id ? row.entity_id.slice(-8) : ""} · ${row.actor_id || "System"}`}
              </p>
            </div>
            <time>{time(row.timestamp || row.created_at)}</time>
          </div>
        ))
      ) : (
        <Empty title="No activity yet" />
      )}
    </div>
  );
}
export function DetailLink({
  to,
  children,
}: {
  to: string;
  children: React.ReactNode;
}) {
  return (
    <Link className="text-link" to={to}>
      {children}
      <ArrowUpRight size={14} />
    </Link>
  );
}
export function KeyValue({
  label: caption,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="key-value">
      <span>{caption}</span>
      <strong>{value}</strong>
    </div>
  );
}
