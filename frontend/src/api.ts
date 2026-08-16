import type {
  AgentEvent,
  Artifact,
  Comparison,
  Experiment,
  ExperimentDetail,
  Run,
  Validation,
} from "./types";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  experiments: () => request<Experiment[]>("/api/experiments"),
  experiment: (id: string) => request<ExperimentDetail>(`/api/experiments/${id}`),
  runs: () => request<Run[]>("/api/runs?limit=200"),
  run: (id: string) => request<Run>(`/api/runs/${id}`),
  events: (id: string) => request<AgentEvent[]>(`/api/runs/${id}/events`),
  validations: (id: string) => request<Validation[]>(`/api/runs/${id}/validations`),
  artifacts: (id: string) => request<Artifact[]>(`/api/runs/${id}/artifacts`),
  compare: (runA: string, runB: string) =>
    request<Comparison>(`/api/compare?run_a=${runA}&run_b=${runB}`),
};
