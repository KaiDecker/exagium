import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import {
  EmptyState,
  ErrorPanel,
  Loading,
  shortId,
  statusLabel,
  StatusBadge,
} from "../components";

const signatureLabels: Record<string, string> = {
  SEARCH: "搜索",
  READ: "读取",
  EDIT: "编辑",
  TEST: "测试",
  COMMAND: "命令",
  TOOL: "工具",
  PASS: "通过",
  FAIL: "失败",
  ERROR: "异常",
  CANCELLED: "取消",
};

const outcomeLabels: Record<string, string> = {
  PASSED: "通过",
  FAILED: "失败",
  COMPLETED: "完成",
};

export function ComparePage() {
  const initial = new URLSearchParams(window.location.search);
  const [runA, setRunA] = useState(initial.get("run_a") ?? "");
  const [runB, setRunB] = useState(initial.get("run_b") ?? "");
  const [request, setRequest] = useState<[string, string] | null>(
    runA && runB ? [runA, runB] : null,
  );
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const comparison = useQuery({
    queryKey: ["compare", request],
    queryFn: () => api.compare(request![0], request![1]),
    enabled: Boolean(request),
  });

  const aligned = useMemo(() => {
    if (!comparison.data) return [];
    const { steps: a } = comparison.data.run_a;
    const { steps: b } = comparison.data.run_b;
    return Array.from({ length: Math.max(a.length, b.length) }, (_, index) => ({
      a: a[index],
      b: b[index],
      number: index + 1,
    }));
  }, [comparison.data]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!runA || !runB || runA === runB) return;
    const params = new URLSearchParams({ run_a: runA, run_b: runB });
    window.history.replaceState(null, "", `/compare?${params}`);
    setRequest([runA, runB]);
  }

  return (
    <div className="page compare-page">
      <header className="page-header compare-header">
        <div>
          <span className="eyebrow">确定性轨迹对齐</span>
          <h1>找到行为改变的<br />第一个瞬间。</h1>
          <p>使用语义签名定位首次有效分歧，无需依赖 LLM Judge。</p>
        </div>
        <div className="compare-glyph" aria-hidden="true"><span>A</span><i /><span>B</span></div>
      </header>

      <form className="compare-form panel" onSubmit={submit}>
        <label>运行 A<select value={runA} onChange={(event) => setRunA(event.target.value)}><option value="">选择运行记录</option>{runs.data?.map((run) => <option value={run.id} key={run.id}>{shortId(run.id)} · {statusLabel(run.status)} · {run.variant_id ?? run.agent_name}</option>)}</select></label>
        <div className="versus">对</div>
        <label>运行 B<select value={runB} onChange={(event) => setRunB(event.target.value)}><option value="">选择运行记录</option>{runs.data?.map((run) => <option value={run.id} key={run.id}>{shortId(run.id)} · {statusLabel(run.status)} · {run.variant_id ?? run.agent_name}</option>)}</select></label>
        <button type="submit" disabled={!runA || !runB || runA === runB}>开始对比</button>
      </form>

      {comparison.isLoading && <Loading label="正在对齐执行轨迹" />}
      {comparison.error && <ErrorPanel error={comparison.error} />}
      {!request && <EmptyState title="请选择两条已结束的运行">同一任务下成功与失败的运行通常能揭示最有价值的行为分歧。</EmptyState>}

      {comparison.data && (
        <section className="comparison panel">
          <div className="comparison-summary">
            <div><span>运行 A</span><strong>{shortId(comparison.data.run_a.id)}</strong><StatusBadge status={comparison.data.run_a.status} /></div>
            <div className="divergence-callout"><span>首次分歧</span><strong>{comparison.data.first_divergence ? `第 ${comparison.data.first_divergence.step} 步` : "无"}</strong><small>{comparison.data.identical ? "两条语义序列一致" : "最早出现的行为变化"}</small></div>
            <div><span>运行 B</span><strong>{shortId(comparison.data.run_b.id)}</strong><StatusBadge status={comparison.data.run_b.status} /></div>
          </div>
          {!comparison.data.same_task && <div className="warning">两条运行来自不同任务，请谨慎解释对比结果。</div>}
          <div className="alignment-header"><span>运行 A 序列</span><span>步骤</span><span>运行 B 序列</span></div>
          <div className="alignment">
            {aligned.map(({ a, b, number }) => {
              const highlighted = comparison.data?.first_divergence?.step === number;
              return (
                <div className={`alignment-row ${highlighted ? "diverged" : ""}`} key={number}>
                  <div className="semantic-step"><b>{a ? (signatureLabels[a.signature] ?? a.signature) : "—"}</b><span>{a?.detail ?? "无对应步骤"}</span>{a?.outcome && <small>{outcomeLabels[a.outcome] ?? a.outcome}</small>}</div>
                  <i>{number}</i>
                  <div className="semantic-step"><b>{b ? (signatureLabels[b.signature] ?? b.signature) : "—"}</b><span>{b?.detail ?? "无对应步骤"}</span>{b?.outcome && <small>{outcomeLabels[b.outcome] ?? b.outcome}</small>}</div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
