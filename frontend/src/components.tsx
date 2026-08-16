import type { ReactNode } from "react";
import type { RunStatus } from "./types";

const statusLabels: Record<string, string> = {
  QUEUED: "排队中",
  PREPARING: "准备中",
  RUNNING: "运行中",
  VALIDATING: "验证中",
  PASSED: "已通过",
  FAILED: "未通过",
  ERROR: "异常",
  CANCELLED: "已取消",
};

export function statusLabel(status: string) {
  return statusLabels[status] ?? status;
}

export function StatusBadge({ status }: { status: RunStatus | string }) {
  return (
    <span className={`status status-${status.toLowerCase()}`}>
      {statusLabel(status)}
    </span>
  );
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
      <div className="empty-mark">?</div>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}

export function Loading({ label = "正在读取证据" }: { label?: string }) {
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
      <strong>无法载入当前页面</strong>
      <span>{error.message}</span>
    </div>
  );
}

export function formatDuration(value?: number | null) {
  if (value == null) return "—";
  if (value < 1000) return `${Math.round(value)} 毫秒`;
  const seconds = value / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)} 秒` : `${(seconds / 60).toFixed(1)} 分钟`;
}

export function formatNumber(value?: number | null) {
  return value == null
    ? "—"
    : new Intl.NumberFormat("zh-CN", { notation: "compact" }).format(value);
}

export function shortId(id: string) {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}
