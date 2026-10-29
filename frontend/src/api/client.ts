// Typed API client. Every UI result comes from these calls — the frontend
// never fabricates simulation outcomes.

import type {
  BuildingDetail,
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
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
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

  // experiments
  createExperiment: (body: unknown) =>
    request<ExperimentSummary>('/experiments', { method: 'POST', body: JSON.stringify(body) }),
  getExperiment: (id: number) => request<ExperimentSummary>(`/experiments/${id}`),
  listExperiments: () => request<ExperimentSummary[]>('/experiments'),
  getExperimentResults: (id: number) => request<ExperimentResults>(`/experiments/${id}/results`),
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
