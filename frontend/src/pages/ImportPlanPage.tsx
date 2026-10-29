// Plan import: upload an existing floor plan (image or ASCII DXF), convert it
// to a grid draft, review it, and hand it to the building editor for cleanup,
// exit placement, and zones. The conversion is an approximation — the editor
// step is mandatory, not optional.

import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiRequestError, type ImportPreviewResponse } from '../api/client'
import GridCanvas from '../components/GridCanvas'
import { DisclaimerBanner, ErrorAlert } from '../components/ui'

interface SuggestedScenario {
  name: string
  description: string
  config: {
    zone_populations: Record<string, number>
    max_duration_s: number
    dt_s: number
  }
}

const SAMPLE_PLAN_URL = '/sample-plan.png'

export default function ImportPlanPage() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileName, setFileName] = useState('')
  const [name, setName] = useState('Imported building')
  const [targetWidth, setTargetWidth] = useState(60)
  const [realWidthM, setRealWidthM] = useState(15)
  const [threshold, setThreshold] = useState(128)
  const [invert, setInvert] = useState(false)
  const [result, setResult] = useState<ImportPreviewResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [runningAll, setRunningAll] = useState(false)
  const [isDxf, setIsDxf] = useState(false)

  const draftBuilding = useMemo(() => {
    if (!result) return null
    return {
      id: 0,
      name: result.draft.name,
      description: 'Imported plan draft (walls only)',
      width: result.draft.width,
      height: result.draft.height,
      cell_size_m: result.draft.cell_size_m,
      is_sample: false,
      created_at: '',
      updated_at: '',
      warnings: [],
      walls: result.draft.walls,
      exits: [],
      zones: [],
    }
  }, [result])

  function pickFile(f: File | null) {
    setFile(f)
    setResult(null)
    setError(null)
    if (!f) return
    setFileName(f.name)
    setIsDxf(f.name.toLowerCase().endsWith('.dxf'))
    setName(f.name.replace(/\.[^.]+$/, '') || 'Imported building')
  }

  async function convert() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const preview = await api.previewImportPlan(file, {
        name,
        target_width: targetWidth,
        real_width_m: realWidthM,
        threshold,
        invert,
      })
      setResult(preview)
    } catch (e) {
      setResult(null)
      setError(e instanceof ApiRequestError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function convertAndRun() {
    if (!result) return
    setRunningAll(true)
    setError(null)
    try {
      const suggested = (result as ImportPreviewResponse & { suggested_scenario?: SuggestedScenario })
        .suggested_scenario
      const building = await api.createBuilding({
        name: result.draft.name,
        description: 'Imported from a floor plan with automatic door/exit/zone detection.',
        width: result.draft.width,
        height: result.draft.height,
        cell_size_m: result.draft.cell_size_m,
        walls: result.draft.walls,
        exits: result.draft.exits,
        zones: result.draft.zones,
      })
      let runId: number | null = null
      if (suggested) {
        const scenario = await api.createScenario({
          building_id: building.id,
          name: suggested.name,
          description: suggested.description,
          config: suggested.config,
        })
        const { run } = await api.createRun({ scenario_id: scenario.id })
        runId = run.id
      }
      navigate(runId ? `/runs/${runId}` : `/buildings/${building.id}`)
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
      setRunningAll(false)
    }
  }

  function openInEditor() {
    if (!result) return
    const draft = { ...result.draft, importWarnings: result.warnings }
    try {
      sessionStorage.setItem('evacuatesim-import-draft', JSON.stringify(draft))
    } catch {
      // storage unavailable: router state still carries it for this navigation
    }
    navigate('/buildings', { state: { importDraft: draft } })
  }

  async function useSamplePlan() {
    try {
      setBusy(true)
      const resp = await fetch(SAMPLE_PLAN_URL)
      if (!resp.ok) throw new Error('Sample plan not available')
      const blob = await resp.blob()
      pickFile(new File([blob], 'sample-plan.png', { type: 'image/png' }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1>Import Building Plan</h1>
      <p className="page-sub">
        Upload a prepared floor plan — an image (PNG/JPG/BMP/TIFF) or an ASCII DXF
        CAD file — and EvacuateSim converts it into a simulation automatically:
        walls, doors, exits (with width-based capacities), starting zones with
        suggested populations, and a ready-to-run scenario.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />

      <div className="grid-2" style={{ gridTemplateColumns: '1fr 1.4fr', alignItems: 'start' }}>
        <div>
          <div className="card">
            <h3>1. Upload the plan</h3>
            <input
              ref={fileInputRef}
              type="file"
              accept=".png,.jpg,.jpeg,.bmp,.gif,.tif,.tiff,.webp,.dxf"
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            />
            {fileName && <div className="muted">Selected: {fileName}</div>}
            <div className="toolbar" style={{ marginTop: 10 }}>
              <button className="secondary" onClick={useSamplePlan} disabled={busy}>
                Use the bundled sample plan
              </button>
            </div>
            <div className="kbd-note">
              Supported: PNG/JPG/BMP/GIF/TIFF/WebP images and plain-text (ASCII) DXF
              with LINE / LWPOLYLINE / CIRCLE geometry. Max{' '}
              10 MB. Binary DXF and PDF are not supported.
            </div>
          </div>

          <div className="card">
            <h3>2. Conversion settings</h3>
            <label className="field">
              <span className="lbl">Building name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <div className="grid-2">
              <label className="field">
                <span className="lbl">Grid width (cells, 8–120)</span>
                <input
                  type="number"
                  min={8}
                  max={120}
                  value={targetWidth}
                  onChange={(e) => setTargetWidth(Number(e.target.value) || 60)}
                />
              </label>
              <label className="field">
                <span className="lbl">Real plan width (metres)</span>
                <input
                  type="number"
                  step={0.5}
                  min={1}
                  value={realWidthM}
                  onChange={(e) => setRealWidthM(Number(e.target.value) || 15)}
                />
              </label>
            </div>
            {!isDxf && (
              <>
                <label className="field">
                  <span className="lbl">
                    Wall darkness threshold ({threshold}) — lower keeps only the
                    darkest lines
                  </span>
                  <input
                    type="range"
                    min={20}
                    max={235}
                    value={threshold}
                    onChange={(e) => setThreshold(Number(e.target.value))}
                  />
                </label>
                <label className="field" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={invert}
                    onChange={(e) => setInvert(e.target.checked)}
                    style={{ width: 'auto' }}
                  />
                  Invert (plan drawn light-on-dark)
                </label>
              </>
            )}
            <button onClick={convert} disabled={!file || busy}>
              {busy ? 'Converting…' : 'Convert to simulation grid'}
            </button>
          </div>

          {result && (
            <div className="card">
              <h3>3. Review &amp; open in editor</h3>
              <table className="data">
                <tbody>
                  <tr>
                    <td>Source</td>
                    <td>{result.stats.source_type.toUpperCase()}</td>
                  </tr>
                  <tr>
                    <td>Grid</td>
                    <td>
                      {result.stats.grid[0]}×{result.stats.grid[1]} cells ·{' '}
                      {result.stats.cell_size_m} m/cell
                    </td>
                  </tr>
                  <tr>
                    <td>Wall cells</td>
                    <td>
                      {result.stats.wall_cell_count} ({(result.stats.wall_ratio * 100).toFixed(1)}%)
                    </td>
                  </tr>
                  {'source_pixels' in result.stats && result.stats.source_pixels && (
                    <tr>
                      <td>Source image</td>
                      <td>
                        {result.stats.source_pixels[0]}×{result.stats.source_pixels[1]} px
                      </td>
                    </tr>
                  )}
                  {'segments_imported' in result.stats && (
                    <tr>
                      <td>DXF segments</td>
                      <td>
                        {result.stats.segments_imported} from {result.stats.entities_seen}{' '}
                        entities
                      </td>
                    </tr>
                  )}
                  {result.stats.semantics && (
                    <>
                      <tr>
                        <td>Rooms detected</td>
                        <td>{result.stats.semantics.rooms}</td>
                      </tr>
                      <tr>
                        <td>Doors / openings</td>
                        <td>
                          {result.stats.semantics.doors} / {result.stats.semantics.openings}
                        </td>
                      </tr>
                      <tr>
                        <td>Exits placed</td>
                        <td>{result.stats.semantics.exits}</td>
                      </tr>
                      <tr>
                        <td>Starting zones</td>
                        <td>{result.stats.semantics.zones}</td>
                      </tr>
                    </>
                  )}
                </tbody>
              </table>
              <div className="toolbar" style={{ marginTop: 12 }}>
                <button onClick={convertAndRun} disabled={runningAll}>
                  {runningAll ? 'Creating & simulating…' : 'Convert & run evacuation'}
                </button>
                <button className="secondary" onClick={openInEditor}>
                  Review in editor first
                </button>
              </div>
            </div>
          )}
        </div>

        <div>
          <div className="map-wrap">
            {draftBuilding ? (
              <GridCanvas
                building={draftBuilding}
                cellPx={Math.max(8, Math.min(24, Math.floor(760 / result!.draft.width)))}
              />
            ) : (
              <div className="empty" style={{ minHeight: 300 }}>
                Converted walls will appear here as a grid preview.
              </div>
            )}
          </div>
          {result && (
            <>
              <div className="alert info">
                Auto-detected {result.stats.semantics?.exits ?? 0} exit(s),{' '}
                {result.stats.semantics?.zones ?? 0} starting zone(s) with suggested populations,
                and {result.stats.semantics?.doors ?? 0} door(s). "Convert &amp; run" builds
                everything and starts the evacuation; the editor is there if you want to fine-tune.
              </div>
              {result.warnings.length > 0 && (
                <div className="alert error">
                  <strong>Conversion notes:</strong>
                  <ul style={{ margin: '6px 0 0 18px' }}>
                    {result.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
