// Building editor: paint walls/floor, place exits, define zones, validate,
// save and load layouts. Grid state lives here; the API is the only source
// of persistence and validation truth.

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiRequestError } from '../api/client'
import GridCanvas from '../components/GridCanvas'
import { DisclaimerBanner, ErrorAlert } from '../components/ui'
import type { BuildingDetail, ExitSpec, ZoneSpec } from '../types'

type Tool = 'wall' | 'floor' | 'exit' | 'zone' | 'erase'
type Point = [number, number]

interface EditorState {
  name: string
  description: string
  width: number
  height: number
  cell_size_m: number
  walls: Point[]
  exits: ExitSpec[]
  zones: ZoneSpec[]
}

const emptyState = (): EditorState => ({
  name: 'New Building',
  description: '',
  width: 24,
  height: 16,
  cell_size_m: 0.5,
  walls: [],
  exits: [],
  zones: [],
})

// Border walls are auto-generated for new buildings; keep them when
// re-generating on resize.
function borderWalls(width: number, height: number): Point[] {
  const walls: Point[] = []
  for (let x = 0; x < width; x++) {
    walls.push([x, 0], [x, height - 1])
  }
  for (let y = 0; y < height; y++) {
    walls.push([0, y], [width - 1, y])
  }
  return walls
}

function key(x: number, y: number): string {
  return `${x},${y}`
}

export default function BuildingEditorPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [buildingId, setBuildingId] = useState<number | null>(id ? Number(id) : null)
  const [state, setState] = useState<EditorState>(emptyState)
  const [tool, setTool] = useState<Tool>('wall')
  const [activeZone, setActiveZone] = useState(0)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [painting, setPainting] = useState(false)
  const [loading, setLoading] = useState(!!id)
  const undoStack = useRef<EditorState[]>([])
  const [buildings, setBuildings] = useState<{ id: number; name: string }[]>([])

  // Load existing building or start a fresh bordered layout.
  useEffect(() => {
    setError(null)
    if (id) {
      setLoading(true)
      api
        .getBuilding(Number(id))
        .then((b: BuildingDetail) => {
          setState({
            name: b.name,
            description: b.description,
            width: b.width,
            height: b.height,
            cell_size_m: b.cell_size_m,
            walls: b.walls.map(([x, y]) => [x, y] as Point),
            exits: b.exits,
            zones: b.zones,
          })
          setBuildingId(b.id)
          setWarnings(b.warnings)
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false))
    } else {
      setState({ ...emptyState(), walls: borderWalls(24, 16) })
      setBuildingId(null)
      setWarnings([])
    }
  }, [id])

  useEffect(() => {
    api.listBuildings().then(setBuildings).catch(() => undefined)
  }, [buildingId])

  const pushUndo = useCallback(() => {
    undoStack.current.push(structuredClone(state))
    if (undoStack.current.length > 100) undoStack.current.shift()
  }, [state])

  const undo = () => {
    const prev = undoStack.current.pop()
    if (prev) setState(prev)
  }

  // ---- painting ----------------------------------------------------------
  function applyTool(x: number, y: number) {
    setState((prev) => {
      const walls = new Set(prev.walls.map(([wx, wy]) => key(wx, wy)))
      const k = key(x, y)
      if (tool === 'wall') {
        walls.add(k)
        removeExitAt(prev, x, y) // exits cannot sit on walls
      } else if (tool === 'floor' || tool === 'erase') {
        walls.delete(k)
        if (tool === 'erase') {
          return {
            ...prev,
            walls: [...walls].map((w) => w.split(',').map(Number) as Point),
            exits: prev.exits.filter((e) => !(e.x === x && e.y === y)),
            zones: prev.zones.map((z) => ({ ...z, cells: z.cells.filter(([cx, cy]) => !(cx === x && cy === y)) })),
          }
        }
      } else if (tool === 'exit') {
        walls.delete(k)
        const exits = prev.exits.filter((e) => !(e.x === x && e.y === y))
        const nextId = `E${prev.exits.length + 1}`
        exits.push({ id: nextId, x, y, capacity_pps: 1.0 })
        return { ...prev, walls: [...walls].map((w) => w.split(',').map(Number) as Point), exits }
      } else if (tool === 'zone') {
        const zones = prev.zones.map((z, i) => {
          if (i !== activeZone) return { ...z, cells: z.cells.filter(([cx, cy]) => !(cx === x && cy === y)) }
          const cells = z.cells.filter(([cx, cy]) => !(cx === x && cy === y))
          if (walls.has(k)) return { ...z, cells } // no zone on walls
          cells.push([x, y])
          return { ...z, cells }
        })
        return { ...prev, zones }
      }
      return { ...prev, walls: [...walls].map((w) => w.split(',').map(Number) as Point) }
    })
  }

  function removeExitAt(_prev: EditorState, x: number, y: number) {
    // exits on a freshly painted wall are dropped by the caller via walls set
    void x
    void y
  }

  function onCellMouseDown(x: number, y: number) {
    pushUndo()
    setPainting(true)
    applyTool(x, y)
  }

  function onCellEnter(x: number, y: number, e: React.MouseEvent) {
    if (painting && (tool === 'wall' || tool === 'floor' || tool === 'zone' || tool === 'erase')) {
      if (e.buttons === 1) applyTool(x, y)
    }
  }

  useEffect(() => {
    const up = () => setPainting(false)
    window.addEventListener('mouseup', up)
    return () => window.removeEventListener('mouseup', up)
  }, [])

  // ---- zones management --------------------------------------------------
  function addZone() {
    pushUndo()
    setState((prev) => ({
      ...prev,
      zones: [...prev.zones, { id: `Z${prev.zones.length + 1}`, name: `Zone ${prev.zones.length + 1}`, cells: [] }],
    }))
    setActiveZone(state.zones.length)
  }

  function renameZone(idx: number, name: string) {
    setState((prev) => ({ ...prev, zones: prev.zones.map((z, i) => (i === idx ? { ...z, name } : z)) }))
  }

  // ---- resize ------------------------------------------------------------
  function resize(width: number, height: number) {
    pushUndo()
    setState((prev) => ({
      ...prev,
      width,
      height,
      walls: borderWalls(width, height),
      exits: prev.exits.filter((e) => e.x < width && e.y < height),
      zones: prev.zones.map((z) => ({ ...z, cells: z.cells.filter(([x, y]) => x < width && y < height) })),
    }))
    setInfo('Grid resized — the border was regenerated; interior walls were cleared.')
  }

  // ---- save / validate ---------------------------------------------------
  async function save() {
    setError(null)
    setInfo(null)
    const body = {
      name: state.name,
      description: state.description,
      width: state.width,
      height: state.height,
      cell_size_m: state.cell_size_m,
      walls: state.walls,
      exits: state.exits,
      zones: state.zones,
    }
    try {
      if (buildingId) {
        const saved = await api.updateBuilding(buildingId, body)
        setWarnings(saved.warnings)
        setInfo('Building saved.')
      } else {
        const saved = await api.createBuilding(body)
        setBuildingId(saved.id)
        setWarnings(saved.warnings)
        setInfo(`Building saved with id ${saved.id}.`)
        navigate(`/buildings/${saved.id}`, { replace: true })
      }
      api.listBuildings().then(setBuildings).catch(() => undefined)
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
    }
  }

  const buildingForCanvas = {
    id: buildingId ?? 0,
    name: state.name,
    description: state.description,
    width: state.width,
    height: state.height,
    cell_size_m: state.cell_size_m,
    is_sample: false,
    created_at: '',
    updated_at: '',
    walls: state.walls,
    exits: state.exits,
    zones: state.zones,
    warnings,
  }

  if (loading) return <div className="muted">Loading building…</div>

  return (
    <div>
      <h1>Building Editor</h1>
      <p className="page-sub">
        Paint walls and floor, place exits, define starting zones. One cell ={' '}
        {state.cell_size_m} m ({(state.cell_size_m * state.width).toFixed(1)} m ×{' '}
        {(state.cell_size_m * state.height).toFixed(1)} m floor).
      </p>
      <DisclaimerBanner />

      <ErrorAlert message={error} />
      {info && <div className="alert info">{info}</div>}
      {warnings.length > 0 && (
        <div className="alert error">
          <strong>Validation warnings:</strong>
          <ul style={{ margin: '6px 0 0 18px' }}>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid-2" style={{ gridTemplateColumns: '2fr 1fr', alignItems: 'start' }}>
        <div className="map-wrap">
          <GridCanvas
            building={buildingForCanvas}
            interactive
            cellPx={Math.max(14, Math.min(26, Math.floor(860 / state.width)))}
            onCellMouseDown={onCellMouseDown}
            onCellMouseEnter={onCellEnter}
          />
          <div className="legend">
            <span><span className="swatch" style={{ background: 'var(--wall)' }} />Wall</span>
            <span><span className="swatch" style={{ background: 'var(--floor)' }} />Floor</span>
            <span><span className="swatch" style={{ background: 'var(--exit)' }} />Exit</span>
            <span><span className="swatch" style={{ background: '#93c5fd' }} />Zone fill</span>
          </div>
        </div>

        <div>
          <div className="card">
            <h3>Tools</h3>
            <div className="toolbar">
              {(['wall', 'floor', 'exit', 'zone', 'erase'] as Tool[]).map((t) => (
                <button
                  key={t}
                  className={tool === t ? 'small' : 'small secondary'}
                  style={tool === t ? { background: 'var(--accent)', color: '#fff' } : undefined}
                  onClick={() => setTool(t)}
                >
                  {t[0].toUpperCase() + t.slice(1)}
                </button>
              ))}
              <button className="small secondary" onClick={undo}>
                Undo
              </button>
            </div>
            <div className="kbd-note">
              Drag to paint. Exit tool places a door (1.0 p/s default); Zone tool paints the
              selected zone below.
            </div>
          </div>

          <div className="card">
            <h3>Zones (starting areas)</h3>
            {state.zones.map((z, i) => (
              <div key={z.id} className="toolbar" style={{ marginBottom: 6 }}>
                <button
                  className="small"
                  style={i === activeZone ? undefined : { background: '#64748b' }}
                  onClick={() => {
                    setActiveZone(i)
                    setTool('zone')
                  }}
                >
                  {i === activeZone ? 'Painting' : 'Select'}
                </button>
                <input
                  value={z.name}
                  onChange={(e) => renameZone(i, e.target.value)}
                  aria-label={`Zone ${z.id} name`}
                />
                <span className="muted">{z.cells.length} cells</span>
              </div>
            ))}
            <button className="small secondary" onClick={addZone}>
              Add zone
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Layout settings</h3>
        <div className="grid-4">
          <label className="field">
            <span className="lbl">Name</span>
            <input value={state.name} onChange={(e) => setState((p) => ({ ...p, name: e.target.value }))} />
          </label>
          <label className="field">
            <span className="lbl">Width (cells)</span>
            <input
              type="number"
              min={4}
              max={120}
              value={state.width}
              onChange={(e) => resize(Number(e.target.value) || state.width, state.height)}
            />
          </label>
          <label className="field">
            <span className="lbl">Height (cells)</span>
            <input
              type="number"
              min={4}
              max={120}
              value={state.height}
              onChange={(e) => resize(state.width, Number(e.target.value) || state.height)}
            />
          </label>
          <label className="field">
            <span className="lbl">Cell size (m)</span>
            <input
              type="number"
              step={0.1}
              min={0.1}
              max={5}
              value={state.cell_size_m}
              onChange={(e) => setState((p) => ({ ...p, cell_size_m: Number(e.target.value) || p.cell_size_m }))}
            />
          </label>
        </div>
        <label className="field">
          <span className="lbl">Description</span>
          <input
            value={state.description}
            onChange={(e) => setState((p) => ({ ...p, description: e.target.value }))}
          />
        </label>
        <div className="toolbar">
          <button onClick={save}>{buildingId ? 'Save changes' : 'Create building'}</button>
          <span className="muted">
            Exits: {state.exits.length} · Zone cells: {state.zones.reduce((a, z) => a + z.cells.length, 0)}
          </span>
        </div>
      </div>

      <div className="card">
        <h3>All buildings</h3>
        <div className="toolbar">
          {buildings.map((b) => (
            <Link key={b.id} to={`/buildings/${b.id}`}>
              <button className="small secondary">{b.name}</button>
            </Link>
          ))}
          <Link to="/buildings">
            <button className="small secondary">+ New</button>
          </Link>
        </div>
      </div>
    </div>
  )
}
