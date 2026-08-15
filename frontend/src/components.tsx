import type { ReactNode } from "react";
import type { RunStatus } from "./types";

export function StatusBadge({ status }: { status: RunStatus | string }) {
  return <span className={`status status-${status.toLowerCase()}`}>{status}</span>;
}

export function Metric({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-mark">∅</div>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}

export function Loading({ label = "Loading evidence" }: { label?: string }) {
  return (
    <div className="loading">
      <span />
      {label}
    </div>
  );
}

export function ErrorPanel({ error }: { error: Error }) {
  return (
    <div className="error-panel">
      <strong>Could not load this view</strong>
      <span>{error.message}</span>
    </div>
  );
}

export function formatDuration(value?: number | null) {
  if (value == null) return "—";
  if (value < 1000) return `${Math.round(value)} ms`;
  const seconds = value / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)} s` : `${(seconds / 60).toFixed(1)} min`;
}

export function formatNumber(value?: number | null) {
  return value == null ? "—" : new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

export function shortId(id: string) {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}
