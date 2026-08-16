import { useQuery } from "@tanstack/react-query";
import { Activity, Braces, FileDiff, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import {
  ErrorPanel,
  formatDuration,
  formatNumber,
  Loading,
  Metric,
  shortId,
  statusLabel,
  StatusBadge,
} from "../components";
import type { AgentEvent } from "../types";

type Tab = "trace" | "validation" | "diff" | "raw";

// 集中维护标签文字与图标，后续增加证据类型时只需改这里。
const tabItems = [
  { name: "trace" as Tab, label: "运行过程", icon: Activity },
  { name: "validation" as Tab, label: "验证结果", icon: ShieldCheck },
  { name: "diff" as Tab, label: "代码改动", icon: FileDiff },
  { name: "raw" as Tab, label: "原始事件", icon: Braces },
];

const eventLabels: Record<string, string> = {
  RUN_STARTED: "运行开始",
  RUN_FINISHED: "运行完成",
  RUN_FAILED: "运行失败",
  AGENT_MESSAGE: "Agent 消息",
  TOOL_STARTED: "工具开始",
  TOOL_COMPLETED: "工具完成",
  TOOL_FAILED: "工具失败",
  COMMAND_STARTED: "命令开始",
  COMMAND_COMPLETED: "命令完成",
  COMMAND_FAILED: "命令失败",
  FILE_CHANGED: "文件变更",
  VALIDATION_STARTED: "验证开始",
  VALIDATION_COMPLETED: "验证完成",
};

function eventTitle(event: AgentEvent) {
  const payload = event.payload;
  if (typeof payload.command === "string") return payload.command;
  if (typeof payload.path === "string") return payload.path;
  if (Array.isArray(payload.changes) && payload.changes.length) {
    const first = payload.changes[0] as { path?: unknown };
    if (typeof first.path === "string") return first.path;
  }
  if (typeof payload.text === "string") return payload.text;
  if (typeof payload.status === "string") return payload.status;
  return event.type.replaceAll("_", " ").toLowerCase();
}

function eventClass(type: string) {
  if (type.includes("FAILED")) return "danger";
  if (type.includes("FILE")) return "edit";
  if (type.includes("COMMAND") || type.includes("TOOL")) return "command";
  if (type.includes("VALIDATION")) return "validation";
  return "note";
}

export function RunDetailPage({ runId }: { runId: string }) {
  const [tab, setTab] = useState<Tab>("trace");
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const events = useQuery({ queryKey: ["events", runId], queryFn: () => api.events(runId) });
  const validations = useQuery({
    queryKey: ["validations", runId],
    queryFn: () => api.validations(runId),
  });
  const artifacts = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => api.artifacts(runId),
  });

  if (run.isLoading) return <Loading label="正在读取这次运行" />;
  if (run.error) return <ErrorPanel error={run.error} />;
  if (!run.data) return null;
  const item = run.data;
  const diff = artifacts.data?.find((artifact) => artifact.type === "git_diff");
  const traceEvents = events.data?.filter(
    (event) => event.type !== "SYSTEM_NOTE" && event.type !== "USAGE_REPORTED",
  );
  const hiddenEventCount = (events.data?.length ?? 0) - (traceEvents?.length ?? 0);

  return (
    <div className="page run-page">
      <div className="breadcrumbs"><a href="/experiments">实验</a><span>/</span><span>运行 {shortId(item.id)}</span></div>
      <header className="run-hero panel">
        <div>
          <span className="eyebrow">这次运行发生了什么</span>
          <div className="run-title"><h1>运行 {shortId(item.id)}</h1><StatusBadge status={item.status} /></div>
          <p>{item.agent_name}{item.agent_version ? ` ${item.agent_version}` : ""} · {item.model_name ?? "未记录模型"} · 任务 <code>{item.task_id}</code></p>
        </div>
        {item.experiment_id && <a className="quiet-link" href="/experiments">返回实验</a>}
      </header>

      <div className="metric-grid run-metrics">
        <Metric label="运行耗时" value={formatDuration(item.metrics.duration_ms)} />
        <Metric label="命令数" value={item.metrics.command_count ?? 0} />
        <Metric label="文件变更" value={item.metrics.file_change_count ?? 0} />
        <Metric label="Token" value={formatNumber(item.metrics.tokens_total)} note={item.metrics.tokens_total == null ? "Agent 未报告" : undefined} />
        <Metric label="验证结果" value={item.validation_status ? statusLabel(item.validation_status) : "—"} />
      </div>

      {item.error && <div className="error-panel"><div><strong>这次运行出错了</strong><span>{item.error}</span></div></div>}

      <section className="evidence panel">
        <div className="tabs" role="tablist">
          {tabItems.map(({ name, label, icon: Icon }) => (
            <button className={tab === name ? "active" : ""} key={name} role="tab" aria-selected={tab === name} onClick={() => setTab(name)}>
              <Icon size={16} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
          ))}
        </div>

        {tab === "trace" && (
          <div className="timeline">
            {events.isLoading && <Loading label="正在整理运行过程" />}
            {events.error && <ErrorPanel error={events.error} />}
            {hiddenEventCount > 0 && (
              <div className="trace-filter-note">
                为了方便阅读，暂时收起了 {hiddenEventCount} 条系统和用量事件；完整内容在“原始事件”里。
              </div>
            )}
            {traceEvents?.map((event) => (
              <article className={`timeline-item ${eventClass(event.type)}`} key={event.id}>
                <div className="timeline-axis"><span>{event.seq}</span><i /></div>
                <div>
                  <header><strong>{eventLabels[event.type] ?? event.type.replaceAll("_", " ")}</strong><time>{new Date(event.timestamp).toLocaleTimeString("zh-CN")}</time></header>
                  <p>{eventTitle(event)}</p>
                  <small>{event.source}</small>
                </div>
              </article>
            ))}
          </div>
        )}

        {tab === "validation" && (
          <div className="validation-list">
            {validations.isLoading && <Loading label="正在读取验证结果" />}
            {validations.data?.map((validation) => (
              <article key={validation.id}>
                <header><div><StatusBadge status={validation.status} /><strong>{validation.name}</strong></div><span>{formatDuration(validation.duration_ms)}</span></header>
                <code>{validation.command}</code>
                {(validation.stdout || validation.stderr) && <pre>{validation.stdout || validation.stderr}</pre>}
              </article>
            ))}
          </div>
        )}

        {tab === "diff" && (
          diff?.content ? <pre className="diff-view">{diff.content}</pre> : <p className="muted padded">这次运行没有留下代码改动。</p>
        )}

        {tab === "raw" && <pre className="raw-view">{JSON.stringify(events.data ?? [], null, 2)}</pre>}
      </section>
    </div>
  );
}
