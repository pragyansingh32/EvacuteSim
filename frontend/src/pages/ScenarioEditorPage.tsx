// Scenario editor: configure populations, behavior distributions, route
// availability, strategy, seed, and run limits. Invalid configurations are
// validated by the backend and the errors are shown verbatim.

import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiRequestError } from '../api/client'
import { DisclaimerBanner, ErrorAlert, strategyLabel } from '../components/ui'
import { DISASTER_LABELS, type DisasterConfig } from '../types'
import type { BuildingDetail, ScenarioConfig, ScenarioDetail } from '../types'

const defaultConfig = (zones: { id: string }[]): ScenarioConfig => ({
  disasters: [] as DisasterConfig[],
  zone_populations: Object.fromEntries(zones.map((z) => [z.id, 0])),
  speed: { distribution: 'normal', mean: 1.2, sd: 0.25, min: 0.6, max: 1.8 },
  pre_movement: { distribution: 'uniform', min: 0, max: 15 },
  strategy: 'nearest_exit',
  seed: 42,
  blocked_exit_ids: [],
  blocked_cells: [],
  exit_capacity_overrides: {},
  max_duration_s: 600,
  dt_s: 0.25,
  frame_interval_s: 1,
  record_frames: true,
})

export default function ScenarioEditorPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const preselectedBuilding = searchParams.get('building')
  const [scenarioId, setScenarioId] = useState<number | null>(id ? Number(id) : null)
  const [buildings, setBuildings] = useState<{ id: number; name: string }[]>([])
  const [building, setBuilding] = useState<BuildingDetail | null>(null)
  const [name, setName] = useState('New Scenario')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState<ScenarioConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    api.listBuildings().then((rows) => {
      setBuildings(rows)
      // Pre-select the building from ?building=X query param
      const target = preselectedBuilding ? Number(preselectedBuilding) : null
      if (target && rows.some((b) => b.id === target)) {
        selectBuilding(target)
      }
    }).catch((e) => setError(e.message))
  }, [preselectedBuilding])

  useEffect(() => {
    if (id) {
      api
        .getScenario(Number(id))
        .then((s: ScenarioDetail) => {
          setScenarioId(s.id)
          setName(s.name)
          setDescription(s.description)
          const loaded = { ...s.config }
          if (!loaded.disasters && (loaded as any).disaster && (loaded as any).disaster.type !== 'none') {
            loaded.disasters = [(loaded as any).disaster]
          }
          loaded.disasters = loaded.disasters ?? []
          setConfig(loaded)
          return api.getBuilding(s.building_id)
        })
        .then(setBuilding)
        .catch((e) => setError(e.message))
    }
  }, [id])

  function selectBuilding(buildingId: number) {
    api
      .getBuilding(buildingId)
      .then((b) => {
        setBuilding(b)
        setConfig(defaultConfig(b.zones))
      })
      .catch((e) => setError(e.message))
  }

  const totalPopulation = useMemo(
    () => (config ? Object.values(config.zone_populations).reduce((a, b) => a + b, 0) : 0),
    [config],
  )

  async function save(): Promise<number | null> {
    if (!building || !config) return null
    setError(null)
    setInfo(null)
    const body = { building_id: building.id, name, description, config }
    try {
      if (scenarioId) {
        await api.updateScenario(scenarioId, body)
        setInfo('Scenario saved.')
        return scenarioId
      }
      const saved = await api.createScenario(body)
      setScenarioId(saved.id)
      setInfo(`Scenario saved with id ${saved.id}.`)
      return saved.id
    } catch (e) {
      if (e instanceof ApiRequestError) {
        const detail = e.details?.map((d) => `${d.loc.join('.')}: ${d.msg}`).join('; ')
        setError(detail ? `${e.message} (${detail})` : e.message)
      } else {
        setError(String(e))
      }
      return null
    }
  }

  async function saveAndRun() {
    const sid = await save()
    if (!sid) return
    setRunning(true)
    try {
      const { run } = await api.createRun({ scenario_id: sid, wait: false })
      navigate(`/runs/${run.id}`)
    } catch (e) {
      if (e instanceof ApiRequestError) {
        const detail = e.details?.map((d) => `${d.loc.join('.')}: ${d.msg}`).join('; ')
        setError(detail ? `${e.message} (${detail})` : e.message)
      } else {
        setError(String(e))
      }
      setRunning(false)
    }
  }

  if (!config) {
    return (
      <div>
        <h1>Scenario Editor</h1>
        <ErrorAlert message={error} />
        <div className="card">
          <h3>1. Choose a building</h3>
          <div className="toolbar">
            {buildings.map((b) => (
              <button key={b.id} className="secondary" onClick={() => selectBuilding(b.id)}>
                {b.name}
              </button>
            ))}
          </div>
          <div className="muted">
            Need a building first? <Link to="/buildings">Open the editor</Link>.
          </div>
        </div>
      </div>
    )
  }

  const set = (patch: Partial<ScenarioConfig>) => setConfig({ ...config, ...patch })

  return (
    <div>
      <h1>Scenario Editor {scenarioId ? `#${scenarioId}` : ''}</h1>
      <p className="page-sub">
        Building: <strong>{building?.name}</strong>. Populations are set per starting zone.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />
      {info && <div className="alert info">{info}</div>}

      <div className="grid-2">
        <div className="card">
          <h3>Occupants</h3>
          {building?.zones.map((z) => (
            <label className="field" key={z.id}>
              <span className="lbl">
                {z.name} ({z.id}) - {z.cells.length} cells
              </span>
              <input
                type="number"
                min={0}
                value={config.zone_populations[z.id] ?? 0}
                onChange={(e) =>
                  set({
                    zone_populations: {
                      ...config.zone_populations,
                      [z.id]: Math.max(0, Number(e.target.value) || 0),
                    },
                  })
                }
              />
            </label>
          ))}
          <div className="muted">Total population: {totalPopulation}</div>

          <h3>Walking speed</h3>
          <div className="grid-2">
            <label className="field">
              <span className="lbl">Distribution</span>
              <select
                value={config.speed.distribution}
                onChange={(e) => set({ speed: { ...config.speed, distribution: e.target.value as 'normal' | 'uniform' } })}
              >
                <option value="normal">Normal (clipped)</option>
                <option value="uniform">Uniform</option>
              </select>
            </label>
            {config.speed.distribution === 'normal' && (
              <>
                <label className="field">
                  <span className="lbl">Mean (m/s)</span>
                  <input
                    type="number"
                    step={0.1}
                    value={config.speed.mean ?? 1.2}
                    onChange={(e) => set({ speed: { ...config.speed, mean: Number(e.target.value) } })}
                  />
                </label>
                <label className="field">
                  <span className="lbl">Std. deviation</span>
                  <input
                    type="number"
                    step={0.05}
                    value={config.speed.sd ?? 0.25}
                    onChange={(e) => set({ speed: { ...config.speed, sd: Number(e.target.value) } })}
                  />
                </label>
              </>
            )}
            <label className="field">
              <span className="lbl">Min (m/s)</span>
              <input
                type="number"
                step={0.1}
                value={config.speed.min}
                onChange={(e) => set({ speed: { ...config.speed, min: Number(e.target.value) } })}
              />
            </label>
            <label className="field">
              <span className="lbl">Max (m/s)</span>
              <input
                type="number"
                step={0.1}
                value={config.speed.max}
                onChange={(e) => set({ speed: { ...config.speed, max: Number(e.target.value) } })}
              />
            </label>
          </div>

          <h3>Pre-movement (reaction) delay</h3>
          <div className="grid-2">
            <label className="field">
              <span className="lbl">Distribution</span>
              <select
                value={config.pre_movement.distribution}
                onChange={(e) =>
                  set({ pre_movement: { ...config.pre_movement, distribution: e.target.value as 'normal' | 'uniform' } })
                }
              >
                <option value="uniform">Uniform</option>
                <option value="normal">Normal (clipped)</option>
              </select>
            </label>
            <label className="field">
              <span className="lbl">Min (s)</span>
              <input
                type="number"
                value={config.pre_movement.min}
                onChange={(e) => set({ pre_movement: { ...config.pre_movement, min: Number(e.target.value) } })}
              />
            </label>
            <label className="field">
              <span className="lbl">Max (s)</span>
              <input
                type="number"
                value={config.pre_movement.max}
                onChange={(e) => set({ pre_movement: { ...config.pre_movement, max: Number(e.target.value) } })}
              />
            </label>
          </div>
        </div>

        <div>
          <div className="card">
            <h3>Routing strategy</h3>
            {(['nearest_exit', 'capacity_aware', 'balanced_assignment'] as const).map((s) => (
              <label key={s} className="field" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  type="radio"
                  name="strategy"
                  checked={config.strategy === s}
                  onChange={() => set({ strategy: s })}
                  style={{ width: 'auto' }}
                />
                {strategyLabel(s)}
              </label>
            ))}
            <div className="muted">
              All strategies use the same movement model; only the exit choice differs.
            </div>
          </div>

          <div className="card">
            <h3>Route availability</h3>
            {building?.exits.map((e) => {
              const blocked = config.blocked_exit_ids.includes(e.id)
              return (
                <label key={e.id} className="field" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={blocked}
                    onChange={(ev) =>
                      set({
                        blocked_exit_ids: ev.target.checked
                          ? [...config.blocked_exit_ids, e.id]
                          : config.blocked_exit_ids.filter((x) => x !== e.id),
                      })
                    }
                    style={{ width: 'auto' }}
                  />
                  Block exit {e.id} (capacity {e.capacity_pps} p/s)
                </label>
              )
            })}
            {Object.keys(config.exit_capacity_overrides).length === 0 && building?.exits.length ? (
              <label className="field">
                <span className="lbl">Override exit capacity (persons/second)</span>
                {building.exits.map((e) => (
                  <div key={e.id} className="toolbar" style={{ marginBottom: 4 }}>
                    <span style={{ width: 30 }}>{e.id}</span>
                    <input
                      type="number"
                      step={0.25}
                      min={0.25}
                      placeholder={String(e.capacity_pps)}
                      onChange={(ev) =>
                        set({
                          exit_capacity_overrides: {
                            ...config.exit_capacity_overrides,
                            [e.id]: Number(ev.target.value) || e.capacity_pps,
                          },
                        })
                      }
                    />
                  </div>
                ))}
              </label>
            ) : null}
          </div>

          <div className="card">
            <h3>Disaster scenarios (can combine)</h3>
            {(config.disasters ?? []).map((d, i) => (
              <div key={i} className="zone-row" style={{ alignItems: 'flex-start' }}>
                <button className="small secondary" onClick={() => set({ disasters: (config.disasters ?? []).filter((_, j) => j !== i) })} title="Remove">✕</button>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{DISASTER_LABELS[d.type] ?? d.type}</div>
                  <input
                    type="range" min={5} max={100}
                    value={Math.round(d.intensity * 100)}
                    onChange={(e) => {
                      const updated = [...(config.disasters ?? [])]
                      updated[i] = { ...d, intensity: Number(e.target.value) / 100 }
                      set({ disasters: updated })
                    }}
                    style={{ width: '100%' }}
                  />
                  <div className="kbd-note">Intensity: {Math.round(d.intensity * 100)}%</div>
                </div>
              </div>
            ))}
            <div className="toolbar" style={{ marginTop: 8 }}>
              <select
                value=""
                onChange={(e) => {
                  if (!e.target.value) return
                  const dtype = e.target.value as DisasterConfig['type']
                  if ((config.disasters ?? []).some((d) => d.type === dtype)) return
                  set({ disasters: [...(config.disasters ?? []), { type: dtype, intensity: 0.5 }] })
                }}
                style={{ maxWidth: 200 }}
              >
                <option value="">+ Add disaster…</option>
                {Object.entries(DISASTER_LABELS)
                  .filter(([k]) => k !== 'none' && !(config.disasters ?? []).some((d) => d.type === k))
                  .map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
              </select>
            </div>
            {(config.disasters ?? []).length === 0 && (
              <div className="muted">No disasters - normal evacuation. Add one or more to test under stress.</div>
            )}
          </div>

          <div className="card">
            <h3>Simulation</h3>
            <div className="grid-2">
              <label className="field">
                <span className="lbl">Random seed</span>
                <input type="number" value={config.seed} onChange={(e) => set({ seed: Number(e.target.value) })} />
              </label>
              <label className="field">
                <span className="lbl">Max duration (s)</span>
                <input
                  type="number"
                  value={config.max_duration_s}
                  onChange={(e) => set({ max_duration_s: Number(e.target.value) })}
                />
              </label>
              <label className="field">
                <span className="lbl">Time step dt (s)</span>
                <input type="number" step={0.05} value={config.dt_s} onChange={(e) => set({ dt_s: Number(e.target.value) })} />
              </label>
              <label className="field">
                <span className="lbl">Frame interval (s)</span>
                <input
                  type="number"
                  step={0.5}
                  value={config.frame_interval_s}
                  onChange={(e) => set({ frame_interval_s: Number(e.target.value) })}
                />
              </label>
            </div>
            <label className="field">
              <span className="lbl">Name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="field">
              <span className="lbl">Description</span>
              <input value={description} onChange={(e) => setDescription(e.target.value)} />
            </label>
          </div>
        </div>
      </div>

      <div className="toolbar">
        <button className="secondary" onClick={save}>
          {scenarioId ? 'Save changes' : 'Save scenario'}
        </button>
        <button onClick={saveAndRun} disabled={running || totalPopulation === 0}>
          {running ? 'Starting…' : 'Save & run simulation'}
        </button>
      </div>
    </div>
  )
}
