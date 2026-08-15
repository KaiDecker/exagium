import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";
import {
  EmptyState,
  ErrorPanel,
  formatDuration,
  formatNumber,
  Loading,
  Metric,
  shortId,
  StatusBadge,
} from "../components";
import type { Experiment } from "../types";

function ExperimentDetail({ experiment }: { experiment: Experiment }) {
  const detail = useQuery({
    queryKey: ["experiment", experiment.id],
    queryFn: () => api.experiment(experiment.id),
  });
  const labelById = new Map(
    (experiment.configuration.variants ?? []).map((variant) => [
      variant.id,
      variant.label ?? variant.id,
    ]),
  );

  return (
    <section className="experiment-detail panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Selected experiment</span>
          <h2>{experiment.name}</h2>
          <p>
            Task <code>{experiment.task_id}</code> · created{" "}
            {new Date(experiment.created_at).toLocaleDateString()}
          </p>
        </div>
        <span className="id-stamp">{experiment.id}</span>
      </div>

      <div className="metric-grid four">
        <Metric label="Runs" value={experiment.metrics.runs ?? 0} />
        <Metric label="Success" value={`${experiment.metrics.success_rate ?? 0}%`} />
        <Metric
          label="Median duration"
          value={formatDuration(experiment.metrics.median_duration_ms)}
        />
        <Metric label="Median tokens" value={formatNumber(experiment.metrics.median_tokens)} />
      </div>

      <div className="section-heading compact">
        <div>
          <span className="eyebrow">Variant performance</span>
          <h3>Reliability by configuration</h3>
        </div>
      </div>
      <div className="variant-list">
        {experiment.variants.length ? (
          experiment.variants.map((variant) => (
            <div className="variant-row" key={variant.id}>
              <div>
                <strong>{labelById.get(variant.id) ?? variant.id}</strong>
                <small>{variant.runs ?? 0} sequential runs</small>
              </div>
              <div className="success-track" aria-label={`${variant.success_rate}% success`}>
                <i style={{ width: `${variant.success_rate ?? 0}%` }} />
              </div>
              <b>{variant.success_rate ?? 0}%</b>
            </div>
          ))
        ) : (
          <p className="muted">No completed variants yet.</p>
        )}
      </div>

      <div className="section-heading compact run-heading">
        <div>
          <span className="eyebrow">Evidence ledger</span>
          <h3>Runs</h3>
        </div>
        <span>{detail.data?.runs.length ?? 0} records</span>
      </div>
      {detail.isLoading && <Loading label="Loading runs" />}
      {detail.error && <ErrorPanel error={detail.error} />}
      {detail.data && (
        <div className="run-table-wrap">
          <table className="run-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Variant</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Commands</th>
                <th>Tokens</th>
              </tr>
            </thead>
            <tbody>
              {detail.data.runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <a href={`/runs/${run.id}`}>{shortId(run.id)}</a>
                  </td>
                  <td>{run.variant_id ?? "—"}</td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td>{formatDuration(run.metrics.duration_ms)}</td>
                  <td>{run.metrics.command_count ?? 0}</td>
                  <td>{formatNumber(run.metrics.tokens_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function ExperimentsPage() {
  const experiments = useQuery({ queryKey: ["experiments"], queryFn: api.experiments });
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!selected && experiments.data?.length) setSelected(experiments.data[0].id);
  }, [experiments.data, selected]);

  if (experiments.isLoading) return <Loading />;
  if (experiments.error) return <ErrorPanel error={experiments.error} />;
  const rows = experiments.data ?? [];
  const current = rows.find((experiment) => experiment.id === selected) ?? rows[0];
  const totalRuns = rows.reduce((sum, experiment) => sum + (experiment.metrics.runs ?? 0), 0);
  const totalPassed = rows.reduce((sum, experiment) => sum + (experiment.metrics.passed ?? 0), 0);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Experiment registry</span>
          <h1>Measure reliability,<br />not confidence.</h1>
          <p>Repeatable tasks, independent validation, comparable evidence.</p>
        </div>
        <div className="header-index">
          <span>{String(rows.length).padStart(2, "0")}</span>
          <small>EXPERIMENTS<br />ON RECORD</small>
        </div>
      </header>

      {!rows.length ? (
        <EmptyState title="No experiments recorded">
          Run <code>exagium experiment run experiments\example.yaml</code> to create the first
          evidence set.
        </EmptyState>
      ) : (
        <>
          <div className="overview-strip">
            <div><span>Total runs</span><strong>{totalRuns}</strong></div>
            <div><span>Validated passes</span><strong>{totalPassed}</strong></div>
            <div><span>Agent profiles</span><strong>{new Set(rows.flatMap((row) => row.variants.map((item) => item.id))).size}</strong></div>
          </div>
          <div className="experiment-layout">
            <aside className="experiment-rail" aria-label="Experiments">
              {rows.map((experiment, index) => (
                <button
                  className={experiment.id === current?.id ? "selected" : ""}
                  key={experiment.id}
                  onClick={() => setSelected(experiment.id)}
                >
                  <span className="rail-number">{String(index + 1).padStart(2, "0")}</span>
                  <span>
                    <strong>{experiment.name}</strong>
                    <small>{experiment.task_id}</small>
                  </span>
                  <b>{experiment.metrics.success_rate ?? 0}%</b>
                </button>
              ))}
            </aside>
            {current && <ExperimentDetail experiment={current} />}
          </div>
        </>
      )}
    </div>
  );
}
