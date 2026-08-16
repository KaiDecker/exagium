import { useQuery } from "@tanstack/react-query";
import { ArrowRight, GitCompareArrows } from "lucide-react";
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
          <span className="eyebrow">运行对比</span>
          <h1>两次运行，<br />差在哪一步？</h1>
          <p>把两次运行放在一起，快速找到行为开始不同的位置。</p>
        </div>
        <div className="compare-glyph" aria-hidden="true"><span>A</span><GitCompareArrows /><span>B</span></div>
      </header>

      <form className="compare-form panel" onSubmit={submit}>
        <label>第一次运行<select value={runA} onChange={(event) => setRunA(event.target.value)}><option value="">选择一条运行</option>{runs.data?.map((run) => <option value={run.id} key={run.id}>{shortId(run.id)} · {statusLabel(run.status)} · {run.variant_id ?? run.agent_name}</option>)}</select></label>
        <div className="versus"><ArrowRight size={17} strokeWidth={1.8} /></div>
        <label>第二次运行<select value={runB} onChange={(event) => setRunB(event.target.value)}><option value="">再选一条运行</option>{runs.data?.map((run) => <option value={run.id} key={run.id}>{shortId(run.id)} · {statusLabel(run.status)} · {run.variant_id ?? run.agent_name}</option>)}</select></label>
        <button type="submit" disabled={!runA || !runB || runA === runB}>对比这两次</button>
      </form>

      {comparison.isLoading && <Loading label="正在比较两次运行" />}
      {comparison.error && <ErrorPanel error={comparison.error} />}
      {!request && <EmptyState title="先选两次运行">最好选择同一个任务的两次运行，这样差异会更有参考价值。</EmptyState>}

      {comparison.data && (
        <section className="comparison panel">
          <div className="comparison-summary">
            <div><span>第一次运行</span><strong>{shortId(comparison.data.run_a.id)}</strong><StatusBadge status={comparison.data.run_a.status} /></div>
            <div className="divergence-callout"><span>第一次出现差异</span><strong>{comparison.data.first_divergence ? `第 ${comparison.data.first_divergence.step} 步` : "没有差异"}</strong><small>{comparison.data.identical ? "两次运行的关键步骤一致" : "从这里开始，两次运行走向不同"}</small></div>
            <div><span>第二次运行</span><strong>{shortId(comparison.data.run_b.id)}</strong><StatusBadge status={comparison.data.run_b.status} /></div>
          </div>
          {!comparison.data.same_task && <div className="warning">这两次运行来自不同任务，结果只能作为参考。</div>}
          <div className="alignment-header"><span>第一次运行</span><span>步骤</span><span>第二次运行</span></div>
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
