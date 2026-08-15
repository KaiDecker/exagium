import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import { EmptyState, ErrorPanel, Loading, shortId, StatusBadge } from "../components";

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
          <span className="eyebrow">Deterministic trace alignment</span>
          <h1>Find the moment<br />behavior changed.</h1>
          <p>Semantic signatures expose the first meaningful divergence without an LLM judge.</p>
        </div>
        <div className="compare-glyph" aria-hidden="true"><span>A</span><i /><span>B</span></div>
      </header>

      <form className="compare-form panel" onSubmit={submit}>
        <label>Run A<select value={runA} onChange={(event) => setRunA(event.target.value)}><option value="">Select a run</option>{runs.data?.map((run) => <option value={run.id} key={run.id}>{shortId(run.id)} · {run.status} · {run.variant_id ?? run.agent_name}</option>)}</select></label>
        <div className="versus">VS</div>
        <label>Run B<select value={runB} onChange={(event) => setRunB(event.target.value)}><option value="">Select a run</option>{runs.data?.map((run) => <option value={run.id} key={run.id}>{shortId(run.id)} · {run.status} · {run.variant_id ?? run.agent_name}</option>)}</select></label>
        <button type="submit" disabled={!runA || !runB || runA === runB}>Compare traces</button>
      </form>

      {comparison.isLoading && <Loading label="Aligning traces" />}
      {comparison.error && <ErrorPanel error={comparison.error} />}
      {!request && <EmptyState title="Choose two terminal runs">Successful and failed runs from the same task usually reveal the most useful divergence.</EmptyState>}

      {comparison.data && (
        <section className="comparison panel">
          <div className="comparison-summary">
            <div><span>Run A</span><strong>{shortId(comparison.data.run_a.id)}</strong><StatusBadge status={comparison.data.run_a.status} /></div>
            <div className="divergence-callout"><span>First divergence</span><strong>{comparison.data.first_divergence ? `Step ${comparison.data.first_divergence.step}` : "None"}</strong><small>{comparison.data.identical ? "Semantic sequences match" : "The earliest behavior change"}</small></div>
            <div><span>Run B</span><strong>{shortId(comparison.data.run_b.id)}</strong><StatusBadge status={comparison.data.run_b.status} /></div>
          </div>
          {!comparison.data.same_task && <div className="warning">These runs belong to different tasks; interpret the comparison cautiously.</div>}
          <div className="alignment-header"><span>Run A sequence</span><span>Step</span><span>Run B sequence</span></div>
          <div className="alignment">
            {aligned.map(({ a, b, number }) => {
              const highlighted = comparison.data?.first_divergence?.step === number;
              return (
                <div className={`alignment-row ${highlighted ? "diverged" : ""}`} key={number}>
                  <div className="semantic-step"><b>{a?.signature ?? "—"}</b><span>{a?.detail ?? "No corresponding step"}</span>{a?.outcome && <small>{a.outcome}</small>}</div>
                  <i>{number}</i>
                  <div className="semantic-step"><b>{b?.signature ?? "—"}</b><span>{b?.detail ?? "No corresponding step"}</span>{b?.outcome && <small>{b.outcome}</small>}</div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
