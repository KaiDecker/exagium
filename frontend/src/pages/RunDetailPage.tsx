import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import {
  ErrorPanel,
  formatDuration,
  formatNumber,
  Loading,
  Metric,
  shortId,
  StatusBadge,
} from "../components";
import type { AgentEvent } from "../types";

type Tab = "trace" | "validation" | "diff" | "raw";

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

  if (run.isLoading) return <Loading label="Loading run evidence" />;
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
      <div className="breadcrumbs"><a href="/experiments">Experiments</a><span>/</span><span>Run {shortId(item.id)}</span></div>
      <header className="run-hero panel">
        <div>
          <span className="eyebrow">Execution record</span>
          <div className="run-title"><h1>Run {shortId(item.id)}</h1><StatusBadge status={item.status} /></div>
          <p>{item.agent_name}{item.agent_version ? ` ${item.agent_version}` : ""} · {item.model_name ?? "model unreported"} · task <code>{item.task_id}</code></p>
        </div>
        {item.experiment_id && <a className="quiet-link" href="/experiments">← Experiment {item.experiment_id}</a>}
      </header>

      <div className="metric-grid run-metrics">
        <Metric label="Duration" value={formatDuration(item.metrics.duration_ms)} />
        <Metric label="Commands" value={item.metrics.command_count ?? 0} />
        <Metric label="Files changed" value={item.metrics.file_change_count ?? 0} />
        <Metric label="Tokens" value={formatNumber(item.metrics.tokens_total)} note={item.metrics.tokens_total == null ? "not reported" : undefined} />
        <Metric label="Validation" value={item.validation_status ?? "—"} />
      </div>

      {item.error && <div className="error-panel"><strong>Run error</strong><span>{item.error}</span></div>}

      <section className="evidence panel">
        <div className="tabs" role="tablist">
          {(["trace", "validation", "diff", "raw"] as Tab[]).map((name) => (
            <button className={tab === name ? "active" : ""} key={name} onClick={() => setTab(name)}>{name}</button>
          ))}
        </div>

        {tab === "trace" && (
          <div className="timeline">
            {events.isLoading && <Loading label="Loading trace" />}
            {events.error && <ErrorPanel error={events.error} />}
            {hiddenEventCount > 0 && (
              <div className="trace-filter-note">
                {hiddenEventCount} system/usage events hidden from the focused trace. Open Raw to
                inspect every recorded event.
              </div>
            )}
            {traceEvents?.map((event) => (
              <article className={`timeline-item ${eventClass(event.type)}`} key={event.id}>
                <div className="timeline-axis"><span>{event.seq}</span><i /></div>
                <div>
                  <header><strong>{event.type.replaceAll("_", " ")}</strong><time>{new Date(event.timestamp).toLocaleTimeString()}</time></header>
                  <p>{eventTitle(event)}</p>
                  <small>{event.source}</small>
                </div>
              </article>
            ))}
          </div>
        )}

        {tab === "validation" && (
          <div className="validation-list">
            {validations.isLoading && <Loading label="Loading validation" />}
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
          diff?.content ? <pre className="diff-view">{diff.content}</pre> : <p className="muted padded">No diff artifact was captured.</p>
        )}

        {tab === "raw" && <pre className="raw-view">{JSON.stringify(events.data ?? [], null, 2)}</pre>}
      </section>
    </div>
  );
}
