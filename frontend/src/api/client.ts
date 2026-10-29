// Typed API client. Every UI result comes from these calls — the frontend
// never fabricates simulation outcomes.

import type {
  BuildingDetail,
  RunMetrics,
  BuildingSummary,
  CompareRow,
  ComparisonResponse,
  ExperimentResults,
  ExperimentSummary,
  RunDetail,
  RunSummary,
  ScenarioDetail,
  ScenarioSummary,
} from '../types'

const BASE = '/api/v1'

export class ApiRequestError extends Error {
  code: string
  status: number
  details?: { loc: (string | number)[]; msg: string }[]

  constructor(status: number, code: string, message: string, details?: { loc: (string | number)[]; msg: string }[]) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Do not set Content-Type for FormData: the browser must add the multipart
  // boundary itself.
  const headers =
    init?.body instanceof FormData
      ? undefined
      : { 'Content-Type': 'application/json', ...(init?.headers as Record<string, string>) }
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  })
  if (!response.ok) {
    let code = 'http_error'
    let message = `Request failed with status ${response.status}`
    let details
    try {
      const body = await response.json()
      if (body?.error) {
        code = body.error.code ?? code
        message = body.error.message ?? message
        details = body.error.details
      }
    } catch {
      // non-JSON error body: keep defaults
    }
    throw new ApiRequestError(response.status, code, message, details)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  // buildings
  listBuildings: () => request<BuildingSummary[]>('/buildings'),
  getBuilding: (id: number) => request<BuildingDetail>(`/buildings/${id}`),
  createBuilding: (body: unknown) =>
    request<BuildingDetail>('/buildings', { method: 'POST', body: JSON.stringify(body) }),
  updateBuilding: (id: number, body: unknown) =>
    request<BuildingDetail>(`/buildings/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteBuilding: (id: number) => request<void>(`/buildings/${id}`, { method: 'DELETE' }),
  validateBuilding: (body: unknown) =>
    request<{ warnings: string[] }>('/buildings/validate', { method: 'POST', body: JSON.stringify(body) }),

  // scenarios
  listScenarios: (buildingId?: number) =>
    request<ScenarioSummary[]>(`/scenarios${buildingId ? `?building_id=${buildingId}` : ''}`),
  getScenario: (id: number) => request<ScenarioDetail>(`/scenarios/${id}`),
  createScenario: (body: unknown) =>
    request<ScenarioDetail>('/scenarios', { method: 'POST', body: JSON.stringify(body) }),
  updateScenario: (id: number, body: unknown) =>
    request<ScenarioDetail>(`/scenarios/${id}`, { method: 'PUT', body: JSON.stringify(body) }),

  // runs
  createRun: (body: unknown) =>
    request<{ run: RunDetail }>('/runs', { method: 'POST', body: JSON.stringify(body) }),
  getRun: (id: number, includeFrames = true) =>
    request<RunDetail>(`/runs/${id}?include_frames=${includeFrames}`),
  listRuns: (scenarioId?: number) =>
    request<RunSummary[]>(`/runs${scenarioId ? `?scenario_id=${scenarioId}` : ''}`),
  recentRuns: () => request<RunSummary[]>('/runs/recent'),
  reproduceRun: (id: number) =>
    request<{ run: RunDetail }>(`/runs/${id}/reproduce`, { method: 'POST' }),
  compareRuns: (runIds: number[]) =>
    request<ComparisonResponse>('/compare', { method: 'POST', body: JSON.stringify({ run_ids: runIds }) }),

  // plan import
  previewImportPlan: (
    file: File,
    params: { name: string; target_width: number; real_width_m: number; threshold: number; invert: boolean },
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('name', params.name)
    form.append('target_width', String(params.target_width))
    form.append('real_width_m', String(params.real_width_m))
    form.append('threshold', String(params.threshold))
    form.append('invert', String(params.invert))
    return request<ImportPreviewResponse>('/import/preview', { method: 'POST', body: form })
  },

  // system validation
  validationBattery: () => request<ValidationReport>('/validation/battery'),

  // AI advisor
  advisorAnalyze: (runId: number) =>
    request<AdvisorReport>('/advisor/analyze', { method: 'POST', body: JSON.stringify({ run_id: runId }) }),
  advisorApply: (runId: number, recommendationId: string) =>
    request<AdvisorApplyResult>('/advisor/apply', {
      method: 'POST',
      body: JSON.stringify({ run_id: runId, recommendation_id: recommendationId }),
    }),

  // restore points
  listRestorePoints: () => request<RestorePoint[]>('/restore-points'),
  createRestorePoint: (name: string) =>
    request<RestorePoint>('/restore-points', { method: 'POST', body: JSON.stringify({ name }) }),
  restorePointDetail: (id: number) => request<RestorePoint>(`/restore-points/${id}`),
  restoreFromPoint: (id: number) =>
    request<{ restored: Record<string, number>; snapshot: string }>(
      `/restore-points/${id}/restore`,
      { method: 'POST' },
    ),
  deleteRestorePoint: (id: number) => request<void>(`/restore-points/${id}`, { method: 'DELETE' }),

  // experiments
  createExperiment: (body: unknown) =>
    request<ExperimentSummary>('/experiments', { method: 'POST', body: JSON.stringify(body) }),
  getExperiment: (id: number) => request<ExperimentSummary>(`/experiments/${id}`),
  listExperiments: () => request<ExperimentSummary[]>('/experiments'),
  getExperimentResults: (id: number) => request<ExperimentResults>(`/experiments/${id}/results`),
}

export interface ImportPreviewResponse {
  draft: {
    name: string
    width: number
    height: number
    cell_size_m: number
    walls: [number, number][]
    exits: []
    zones: []
  }
  stats: {
    source_type: 'image' | 'dxf'
    wall_cell_count: number
    wall_ratio: number
    grid: [number, number]
    cell_size_m: number
    source_pixels?: [number, number]
    segments_imported?: number
    entities_seen?: number
    semantics?: {
      rooms: number
      doors: number
      openings: number
      exits: number
      zones: number
    }
  }
  suggested_scenario?: {
    name: string
    description: string
    config: {
      zone_populations: Record<string, number>
      max_duration_s: number
      dt_s: number
    }
  } | null
  warnings: string[]
}

export interface ValidationCase {
  name: string
  category: 'pass' | 'fail' | 'accuracy'
  description: string
  expected: string
  passed: boolean
  actual: string
  evidence: Record<string, unknown>
}

export interface ValidationReport {
  engine_version: string
  ran_cases: number
  passed: number
  failed: number
  accuracy_pct: number
  cases: ValidationCase[]
  notes: string[]
}

export interface AdvisorObservation {
  severity: 'ok' | 'info' | 'warn' | 'critical'
  title: string
  detail: string
  evidence: Record<string, unknown>
}

export interface AdvisorRecommendation {
  id: string
  title: string
  rationale: string
  patch: Record<string, unknown>
  patch_summary: string
  estimate: string
}

export interface AdvisorReport {
  run_id: number
  verdict: string
  severity: 'ok' | 'info' | 'warn' | 'critical'
  observations: AdvisorObservation[]
  recommendations: AdvisorRecommendation[]
  disclaimer: string
}

export interface AdvisorApplyResult {
  recommendation: AdvisorRecommendation
  scenario_id: number
  before: { run_id: number; metrics: RunMetrics }
  after: { run_id: number; status: string; error: { code: string; message: string } | null; metrics: RunMetrics }
}

export interface RestorePoint {
  id: number
  name: string
  created_at: string
  counts: Record<string, number>
  size_bytes: number
  is_auto: boolean
}

export function formatRunRow(run: CompareRow): Record<string, string | number | null> {
  const m = run.metrics
  return {
    Run: run.name,
    Strategy: run.strategy,
    Seed: run.seed,
    'Evacuated': m.evacuated_count != null ? `${m.evacuated_count}/${m.total_occupants}` : null,
    'Sim time (s)': m.sim_time_s,
    'T50 (s)': m.t50_s,
    'T90 (s)': m.t90_s,
    'T95 (s)': m.t95_s,
    'Max evac (s)': m.max_evacuation_time_s,
    'Mean queue (s)': m.queue_mean_s,
  }
}
