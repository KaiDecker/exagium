export type RunStatus =
  | "QUEUED"
  | "PREPARING"
  | "RUNNING"
  | "VALIDATING"
  | "PASSED"
  | "FAILED"
  | "ERROR"
  | "CANCELLED";

export interface Metrics {
  runs?: number;
  passed?: number;
  failed?: number;
  errors?: number;
  evaluable_runs?: number;
  success_rate?: number | null;
  success_interval?: {
    lower: number;
    upper: number;
    confidence_level: number;
    method: "wilson";
  } | null;
  duration_ms?: number | null;
  median_duration_ms?: number | null;
  tokens_total?: number | null;
  median_tokens?: number | null;
  command_count?: number;
  file_change_count?: number;
}

export interface Run {
  id: string;
  experiment_id: string | null;
  variant_id: string | null;
  task_id: string;
  status: RunStatus;
  started_at: string | null;
  ended_at: string | null;
  agent_name: string;
  agent_version: string | null;
  model_name: string | null;
  provider_name: string | null;
  exit_code: number | null;
  validation_status: string | null;
  metrics: Metrics;
  error: string | null;
}

export interface Experiment {
  id: string;
  name: string;
  task_id: string;
  created_at: string;
  configuration: {
    tasks?: string[];
    variants?: Array<{ id: string; label?: string; repeat?: number | null }>;
    design?: {
      repeats: number;
      randomize_order: boolean;
      block_by: string[];
      allocation_seed: number | null;
    };
    analysis?: {
      confidence_level: number;
    };
  };
  metrics: Metrics;
  variants: Array<{ id: string } & Metrics>;
}

export interface ExperimentDetail {
  experiment: Experiment;
  runs: Run[];
}

export interface AgentEvent {
  id: string;
  seq: number;
  timestamp: string;
  source: string;
  type: string;
  payload: Record<string, unknown>;
  raw_event: unknown;
}

export interface Validation {
  id: string;
  name: string;
  command: string;
  status: string;
  exit_code: number | null;
  duration_ms: number;
  stdout: string;
  stderr: string;
}

export interface Artifact {
  id: string;
  type: string;
  path: string;
  content: string | null;
}

export interface SemanticStep {
  step: number;
  signature: string;
  detail: string | null;
  event_seq: number | null;
  event_type: string | null;
  outcome: string | null;
}

export interface ComparedRun {
  id: string;
  task_id: string;
  status: RunStatus;
  agent_name: string;
  variant_id: string | null;
  steps: SemanticStep[];
}

export interface Comparison {
  run_a: ComparedRun;
  run_b: ComparedRun;
  same_task: boolean;
  identical: boolean;
  first_divergence: {
    step: number;
    run_a: SemanticStep | null;
    run_b: SemanticStep | null;
  } | null;
}
