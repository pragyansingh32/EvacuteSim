// API type definitions mirroring backend/app/schemas.

export interface ExitSpec {
  id: string
  x: number
  y: number
  capacity_pps: number
}

export interface ZoneSpec {
  id: string
  name: string
  cells: [number, number][]
}

export interface BuildingSummary {
  id: number
  name: string
  description: string
  width: number
  height: number
  cell_size_m: number
  is_sample: boolean
  created_at: string
  updated_at: string
}

export interface BuildingDetail extends BuildingSummary {
  walls: [number, number][]
  exits: ExitSpec[]
  zones: ZoneSpec[]
  warnings: string[]
}

export interface DistributionSpec {
  distribution: 'normal' | 'uniform'
  mean?: number | null
  sd?: number | null
  min: number
  max: number
}

export interface ScenarioConfig {
  zone_populations: Record<string, number>
  speed: DistributionSpec
  pre_movement: DistributionSpec
  strategy: 'nearest_exit' | 'capacity_aware' | 'balanced_assignment'
  seed: number
  blocked_exit_ids: string[]
  blocked_cells: [number, number][]
  exit_capacity_overrides: Record<string, number>
  max_duration_s: number
  dt_s: number
  frame_interval_s: number
  record_frames: boolean
}

export interface ScenarioSummary {
  id: number
  building_id: number
  name: string
  description: string
  is_sample: boolean
  created_at: string
  updated_at: string
}

export interface ScenarioDetail extends ScenarioSummary {
  config: ScenarioConfig
}

export interface ExitStat {
  id: string
  x: number
  y: number
  capacity_pps: number
  assigned: number
  evacuated: number
  utilization_pct: number
  first_discharge_s: number | null
  last_discharge_s: number | null
  mean_discharge_s: number | null
  discharge_times: number[]
}

export interface RunMetrics {
  engine_status: string | null
  sim_time_s: number | null
  steps: number | null
  total_occupants: number | null
  evacuated_count: number | null
  unreachable_count: number | null
  remaining_count: number | null
  t50_s: number | null
  t90_s: number | null
  t95_s: number | null
  mean_evacuation_time_s: number | null
  max_evacuation_time_s: number | null
  queue_total_s: number | null
  queue_mean_s: number | null
  queue_max_s: number | null
  fallback_count: number | null
  exit_stats: ExitStat[]
  congestion: Record<string, number>
  warnings: string[]
}

// [id, x, y, statusCode]
export type OccupantFrameEntry = [number, number, number, number]

export interface Frame {
  t: number
  occupants: OccupantFrameEntry[]
}

export interface RunSummary {
  id: number
  scenario_id: number | null
  building_id: number | null
  name: string
  strategy: string
  seed: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface RunDetail extends RunSummary {
  config: Record<string, unknown>
  metrics: RunMetrics | null
  error: { code: string; message: string } | null
  building_snapshot: Record<string, unknown> | null
  timeline: [number, number, number, number][]
  frames: Frame[]
}

export interface CompareRow {
  run_id: number
  name: string
  strategy: string
  seed: number
  metrics: RunMetrics & { evacuated_pct?: number }
}

export interface ComparisonResponse {
  rows: CompareRow[]
  verdicts: Record<string, string>
  notes: string[]
}

export interface ExperimentSummary {
  id: number
  name: string
  description: string
  base_scenario_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  total_planned: number
  created_at: string
  finished_at: string | null
  error: { code: string; message: string } | null
}

export interface ExperimentResultRow {
  experiment_run_id: number
  run_id: number
  sweep_values: Record<string, unknown>
  seed: number
  metrics: Record<string, number | string | null> | null
}

export interface ExperimentResults {
  experiment: ExperimentSummary
  sweep_definition: Record<string, unknown[]>
  rows: ExperimentResultRow[]
}

export interface ApiError {
  error: {
    code: string
    message: string
    details?: { loc: (string | number)[]; msg: string }[]
  }
}

export const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

export const STRATEGY_LABELS: Record<string, string> = {
  nearest_exit: 'Nearest exit (baseline)',
  capacity_aware: 'Capacity-aware',
  balanced_assignment: 'Balanced assignment',
}
