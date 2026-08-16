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
import type { Experiment, Run } from "../types";
import { ExperimentMotif } from "../Shell";

function RunTable({ runs }: { runs: Run[] }) {
  return (
    <div className="run-table-wrap">
      <table className="run-table">
        <thead>
          <tr>
            <th>运行</th>
            <th>配置</th>
            <th>状态</th>
            <th>耗时</th>
            <th>命令数</th>
            <th>Token</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <a href={`/runs/${run.id}`}>{shortId(run.id)}</a>
              </td>
              <td>{run.variant_id ?? "独立运行"}</td>
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
  );
}

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
          <span className="eyebrow">实验概览</span>
          <h2>{experiment.name}</h2>
          <p>
            任务 <code>{experiment.task_id}</code> · 创建于{" "}
            {new Date(experiment.created_at).toLocaleDateString("zh-CN")}
          </p>
        </div>
        <span className="id-stamp">{experiment.id}</span>
      </div>

      <div className="metric-grid four">
        <Metric label="运行次数" value={experiment.metrics.runs ?? 0} />
        <Metric label="成功率" value={`${experiment.metrics.success_rate ?? 0}%`} />
        <Metric
          label="耗时中位数"
          value={formatDuration(experiment.metrics.median_duration_ms)}
        />
        <Metric label="Token 中位数" value={formatNumber(experiment.metrics.median_tokens)} />
      </div>

      <div className="section-heading compact">
        <div>
          <span className="eyebrow">配置表现</span>
          <h3>哪套配置更稳定？</h3>
        </div>
      </div>
      <div className="variant-list">
        {experiment.variants.length ? (
          experiment.variants.map((variant) => (
            <div className="variant-row" key={variant.id}>
              <div>
                <strong>{labelById.get(variant.id) ?? variant.id}</strong>
                <small>共运行 {variant.runs ?? 0} 次</small>
              </div>
              <div className="success-track" aria-label={`成功率 ${variant.success_rate}%`}>
                <i style={{ width: `${variant.success_rate ?? 0}%` }} />
              </div>
              <b>{variant.success_rate ?? 0}%</b>
            </div>
          ))
        ) : (
          <p className="muted">这组实验还没有跑出可比较的数据。</p>
        )}
      </div>

      <div className="section-heading compact run-heading">
        <div>
          <span className="eyebrow">每次运行</span>
          <h3>看看具体发生了什么</h3>
        </div>
        <span>{detail.data?.runs.length ?? 0} 条记录</span>
      </div>
      {detail.isLoading && <Loading label="正在读取运行记录" />}
      {detail.error && <ErrorPanel error={detail.error} />}
      {detail.data && <RunTable runs={detail.data.runs} />}
    </section>
  );
}

export function ExperimentsPage() {
  const experiments = useQuery({ queryKey: ["experiments"], queryFn: api.experiments });
  const recentRuns = useQuery({ queryKey: ["runs"], queryFn: api.runs });
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
          <span className="eyebrow">Agent 实验</span>
          <h1>看结果，<br />也看稳定性。</h1>
          <p>同一个任务多跑几次，看看 Agent 到底稳不稳。</p>
        </div>
        <div className="header-index">
          <span>{String(rows.length).padStart(2, "0")}</span>
          <small>组实验<br />已记录</small>
        </div>
        <ExperimentMotif />
      </header>

      {!rows.length ? (
        <>
          <EmptyState title="还没有实验">
            运行 <code>exagium experiment run experiments\demo-auth-stability.yaml</code>，
            开始第一组重复测试。
          </EmptyState>
          {recentRuns.error && <ErrorPanel error={recentRuns.error} />}
          {recentRuns.data && recentRuns.data.length > 0 && (
            <section className="standalone-runs panel">
              <div className="section-heading compact">
                <div>
                  <span className="eyebrow">最近运行</span>
                  <h3>还没加入实验的运行</h3>
                </div>
                <span>{recentRuns.data.length} 条记录</span>
              </div>
              <RunTable runs={recentRuns.data} />
            </section>
          )}
        </>
      ) : (
        <>
          <div className="overview-strip">
            <div><span>总运行数</span><strong>{totalRuns}</strong></div>
            <div><span>通过验证</span><strong>{totalPassed}</strong></div>
            <div><span>测试配置</span><strong>{new Set(rows.flatMap((row) => row.variants.map((item) => item.id))).size}</strong></div>
          </div>
          <div className="experiment-layout">
            <aside className="experiment-rail" aria-label="实验列表">
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
