// Building editor: paint walls/floor, place exits, define zones, validate,
// save and load layouts. Painting uses pointer events (mouse/touch/pen) with
// an adjustable brush, keyboard shortcuts, undo/redo, zoom, and an explicit
// unsaved-changes indicator. Grid state lives here; the API is the only
// source of persistence and validation truth.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
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

const TOOLS: { id: Tool; label: string; icon: string; key: string }[] = [
  { id: 'wall', label: 'Wall', icon: '▉', key: 'W' },
  { id: 'floor', label: 'Floor', icon: '·', key: 'F' },
  { id: 'exit', label: 'Exit', icon: '⇥', key: 'E' },
  { id: 'zone', label: 'Zone', icon: '◱', key: 'Z' },
  { id: 'erase', label: 'Erase', icon: '⌫', key: 'X' },
]

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

// Border walls are auto-generated for new buildings; regenerated on resize.
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
  const location = useLocation()
  const [buildingId, setBuildingId] = useState<number | null>(id ? Number(id) : null)
  const [state, setState] = useState<EditorState>(emptyState)
  const [tool, setTool] = useState<Tool>('wall')
  const [brush, setBrush] = useState(1)
  const [activeZone, setActiveZone] = useState(0)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [loading, setLoading] = useState(!!id)
  const [hover, setHover] = useState<[number, number] | null>(null)
  const [zoom, setZoom] = useState<number | null>(null) // null = auto
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const undoStack = useRef<EditorState[]>([])
  const redoStack = useRef<EditorState[]>([])
  const savedSnapshot = useRef<string>('')
  const [buildings, setBuildings] = useState<{ id: number; name: string }[]>([])

  const markDirty = useCallback(() => setDirty(true), [])

  // ---- history ------------------------------------------------------------
  const pushUndo = useCallback(() => {
    undoStack.current.push(structuredClone(state))
    if (undoStack.current.length > 120) undoStack.current.shift()
    redoStack.current = []
  }, [state])

  const undo = useCallback(() => {
    const prev = undoStack.current.pop()
    if (prev) {
      redoStack.current.push(structuredClone(state))
      setState(prev)
      setDirty(true)
    }
  }, [state])

  const redo = useCallback(() => {
    const next = redoStack.current.pop()
    if (next) {
      undoStack.current.push(structuredClone(state))
      setState(next)
      setDirty(true)
    }
  }, [state])

  // ---- load ---------------------------------------------------------------
  useEffect(() => {
    setError(null)
    if (id) {
      setLoading(true)
      api
        .getBuilding(Number(id))
        .then((b: BuildingDetail) => {
          const next: EditorState = {
            name: b.name,
            description: b.description,
            width: b.width,
            height: b.height,
            cell_size_m: b.cell_size_m,
            walls: b.walls.map(([x, y]) => [x, y] as Point),
            exits: b.exits,
            zones: b.zones,
          }
          setState(next)
          setBuildingId(b.id)
          setWarnings(b.warnings)
          savedSnapshot.current = JSON.stringify(next)
          setDirty(false)
          undoStack.current = []
          redoStack.current = []
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false))
      return
    }
    // Adopt an imported plan draft (router state, with sessionStorage fallback).
    const routerDraft = (location.state as { importDraft?: Record<string, unknown> } | null)
      ?.importDraft
    let storedDraft: Record<string, unknown> | null = null
    try {
      const raw = sessionStorage.getItem('evacuatesim-import-draft')
      if (raw) storedDraft = JSON.parse(raw)
    } catch {
      storedDraft = null
    }
    const source = routerDraft ?? storedDraft
    if (source && typeof source.width === 'number' && Array.isArray(source.walls)) {
      try {
        sessionStorage.removeItem('evacuatesim-import-draft')
      } catch {
        // ignore storage errors
      }
      const next: EditorState = {
        name: String(source.name ?? 'Imported building'),
        description: 'Imported plan draft — review walls, then add exits and zones.',
        width: source.width as number,
        height: source.height as number,
        cell_size_m: (source.cell_size_m as number) || 0.5,
        walls: (source.walls as [number, number][]).map(([x, y]) => [x, y] as Point),
        exits: (source.exits as ExitSpec[]) ?? [],
        zones: (source.zones as ZoneSpec[]) ?? [],
      }
      setState(next)
      setBuildingId(null)
      setWarnings([])
      savedSnapshot.current = JSON.stringify(next)
      setDirty(true)
      undoStack.current = []
      redoStack.current = []
      const autoExits = (source.exits as ExitSpec[] | undefined)?.length ?? 0
      const autoZones = (source.zones as ZoneSpec[] | undefined)?.length ?? 0
      setInfo(
        `Imported plan draft loaded with ${autoExits} auto-detected exit(s) and ` +
          `${autoZones} zone(s). Review, adjust, then save.`,
      )
      return
    }
    const fresh = { ...emptyState(), walls: borderWalls(24, 16) }
    setState(fresh)
    setBuildingId(null)
    setWarnings([])
    savedSnapshot.current = JSON.stringify(fresh)
    setDirty(false)
    undoStack.current = []
    redoStack.current = []
  }, [id, location.state])

  useEffect(() => {
    api.listBuildings().then(setBuildings).catch(() => undefined)
  }, [buildingId])

  // ---- keyboard shortcuts -------------------------------------------------
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'SELECT' || target.tagName === 'TEXTAREA') {
        return
      }
      const k = e.key.toLowerCase()
      if ((e.ctrlKey || e.metaKey) && k === 'z') {
        e.preventDefault()
        if (e.shiftKey) redo()
        else undo()
        return
      }
      if ((e.ctrlKey || e.metaKey) && k === 'y') {
        e.preventDefault()
        redo()
        return
      }
      if (e.ctrlKey || e.metaKey) return
      const tool = TOOLS.find((t) => t.key.toLowerCase() === k)
      if (tool) setTool(tool.id)
      if (k === '[') setBrush((b) => Math.max(1, b - 1))
      if (k === ']') setBrush((b) => Math.min(4, b + 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [undo, redo])

  // ---- painting -----------------------------------------------------------
  const applyTool = useCallback(
    (x: number, y: number) => {
      setState((prev) => {
        const walls = new Set(prev.walls.map(([wx, wy]) => key(wx, wy)))
        const zoneCells = new Set(
          (prev.zones[activeZone]?.cells ?? []).map(([wx, wy]) => key(wx, wy)),
        )
        const footprint: Point[] = []
        for (let dy = 0; dy < brush; dy++) {
          for (let dx = 0; dx < brush; dx++) {
            const bx = x + dx
            const by = y + dy
            if (bx < prev.width && by < prev.height) footprint.push([bx, by])
          }
        }
        let next: EditorState = prev

        if (tool === 'wall') {
          footprint.forEach(([bx, by]) => walls.add(key(bx, by)))
          next = {
            ...prev,
            exits: prev.exits.filter((e) => !footprint.some(([fx, fy]) => fx === e.x && fy === e.y)),
            walls: [...walls].map((w) => w.split(',').map(Number) as Point),
          }
        } else if (tool === 'floor' || tool === 'erase') {
          footprint.forEach(([bx, by]) => walls.delete(key(bx, by)))
          if (tool === 'erase') {
            next = {
              ...prev,
              walls: [...walls].map((w) => w.split(',').map(Number) as Point),
              exits: prev.exits.filter((e) => !footprint.some(([fx, fy]) => fx === e.x && fy === e.y)),
              zones: prev.zones.map((z) => ({
                ...z,
                cells: z.cells.filter(([cx, cy]) => !footprint.some(([fx, fy]) => fx === cx && fy === cy)),
              })),
            }
          } else {
            next = { ...prev, walls: [...walls].map((w) => w.split(',').map(Number) as Point) }
          }
        } else if (tool === 'exit') {
          if (footprint.length === 1) {
            const [bx, by] = footprint[0]
            const wallsSet = new Set(walls)
            wallsSet.delete(key(bx, by))
            const exits = prev.exits.filter((e) => !(e.x === bx && e.y === by))
            const nextId = `E${prev.exits.length + 1}`
            exits.push({ id: nextId, x: bx, y: by, capacity_pps: 1.0 })
            next = {
              ...prev,
              walls: [...wallsSet].map((w) => w.split(',').map(Number) as Point),
              exits,
            }
          } else {
            next = prev
          }
        } else if (tool === 'zone') {
          if (!prev.zones[activeZone]) return prev
          const zones = prev.zones.map((z, i) => {
            if (i !== activeZone) return z
            const cells = new Set(z.cells.map(([cx, cy]) => key(cx, cy)))
            footprint.forEach(([bx, by]) => {
              if (!walls.has(key(bx, by))) cells.add(key(bx, by))
            })
            return { ...z, cells: [...cells].map((c) => c.split(',').map(Number) as Point) }
          })
          next = { ...prev, zones }
          void zoneCells
        }
        if (next !== prev) markDirty()
        return next
      })
    },
    [tool, brush, activeZone, markDirty],
  )

  const onPaint = useCallback(
    (x: number, y: number, phase: 'down' | 'drag') => {
      if (phase === 'down') pushUndo()
      applyTool(x, y)
    },
    [applyTool, pushUndo],
  )

  // ---- zones & exits ------------------------------------------------------
  function addZone() {
    pushUndo()
    setState((prev) => ({
      ...prev,
      zones: [...prev.zones, { id: `Z${prev.zones.length + 1}`, name: `Zone ${prev.zones.length + 1}`, cells: [] }],
    }))
    setActiveZone(state.zones.length)
    setTool('zone')
    markDirty()
  }

  function deleteZone(idx: number) {
    pushUndo()
    setState((prev) => ({ ...prev, zones: prev.zones.filter((_, i) => i !== idx) }))
    setActiveZone(0)
    markDirty()
  }

  function renameZone(idx: number, name: string) {
    setState((prev) => ({ ...prev, zones: prev.zones.map((z, i) => (i === idx ? { ...z, name } : z)) }))
    markDirty()
  }

  function setExitCapacity(exitId: string, capacity: number) {
    setState((prev) => ({
      ...prev,
      exits: prev.exits.map((e) => (e.id === exitId ? { ...e, capacity_pps: capacity } : e)),
    }))
    markDirty()
  }

  function deleteExit(exitId: string) {
    pushUndo()
    setState((prev) => ({ ...prev, exits: prev.exits.filter((e) => e.id !== exitId) }))
    markDirty()
  }

  // ---- resize / zoom ------------------------------------------------------
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
    markDirty()
  }

  const autoCellPx = Math.max(12, Math.min(26, Math.floor(820 / state.width)))
  const cellPx = zoom ?? autoCellPx

  // ---- save ---------------------------------------------------------------
  async function save() {
    setError(null)
    setInfo(null)
    setSaving(true)
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
        window.history.replaceState(null, '', `/buildings/${saved.id}`)
      }
      savedSnapshot.current = JSON.stringify(state)
      setDirty(false)
      api.listBuildings().then(setBuildings).catch(() => undefined)
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const buildingForCanvas = useMemo(
    () => ({
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
    }),
    [buildingId, state, warnings],
  )

  if (loading) return <div className="muted">Loading building…</div>

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Building Editor</h1>
          <p className="page-sub">
            Paint walls and floor, place exits, define starting zones. One cell ={' '}
            {state.cell_size_m} m — the floor is {(state.cell_size_m * state.width).toFixed(1)} m ×{' '}
            {(state.cell_size_m * state.height).toFixed(1)} m.
          </p>
        </div>
        <div className="page-actions">
          <button className="secondary" onClick={undo} disabled={undoStack.current.length === 0} title="Undo (Ctrl+Z)">
            ↶ Undo
          </button>
          <button className="secondary" onClick={redo} disabled={redoStack.current.length === 0} title="Redo (Ctrl+Shift+Z)">
            ↷ Redo
          </button>
          <button onClick={save} disabled={saving}>
            {saving ? 'Saving…' : buildingId ? (dirty ? 'Save changes •' : 'Saved') : dirty ? 'Create building •' : 'Saved'}
          </button>
        </div>
      </div>
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

      <div className="editor-layout">
        {/* ---- tool rail ---- */}
        <div className="tool-rail card">
          <div className="rail-label">Tools</div>
          {TOOLS.map((t) => (
            <button
              key={t.id}
              className={`rail-btn${tool === t.id ? ' active' : ''}`}
              onClick={() => setTool(t.id)}
              title={`${t.label} (${t.key})`}
            >
              <span className="rail-icon">{t.icon}</span>
              <span className="rail-text">{t.label}</span>
              <span className="rail-key">{t.key}</span>
            </button>
          ))}
          <div className="rail-label">Brush</div>
          <div className="brush-row">
            {[1, 2, 3, 4].map((b) => (
              <button
                key={b}
                className={`brush-btn${brush === b ? ' active' : ''}`}
                onClick={() => setBrush(b)}
                title={`${b}×${b} brush`}
              >
                {b}×{b}
              </button>
            ))}
          </div>
          <div className="rail-label">Zoom</div>
          <div className="brush-row">
            <button className="brush-btn" onClick={() => setZoom(Math.max(8, (zoom ?? autoCellPx) - 4))} title="Zoom out">
              −
            </button>
            <button className="brush-btn" onClick={() => setZoom(null)} title="Fit to window">
              Fit
            </button>
            <button className="brush-btn" onClick={() => setZoom(Math.min(40, (zoom ?? autoCellPx) + 4))} title="Zoom in">
              +
            </button>
          </div>
        </div>

        {/* ---- map ---- */}
        <div className="editor-map">
          <div className="map-wrap">
            <GridCanvas
              building={buildingForCanvas}
              interactive
              brushSize={tool === 'wall' || tool === 'floor' || tool === 'erase' || tool === 'zone' ? brush : 1}
              cellPx={cellPx}
              onPaint={onPaint}
              onHover={setHover}
            />
          </div>
          <div className="status-bar">
            <span>
              <strong>{TOOLS.find((t) => t.id === tool)?.label}</strong>
              {hover ? ` @ (${hover[0]}, ${hover[1]})` : ' — hover the map'}
            </span>
            <span>
              {state.width}×{state.height} cells · {cellPx} px/cell
            </span>
            <span>
              Exits: {state.exits.length} · Zone cells:{' '}
              {state.zones.reduce((a, z) => a + z.cells.length, 0)} · Walls:{' '}
              {state.walls.length}
            </span>
            <span className={`save-state${dirty ? ' dirty' : ''}`}>
              {dirty ? '● Unsaved changes' : '✓ Saved'}
            </span>
          </div>
        </div>

        {/* ---- side panel ---- */}
        <div className="editor-side">
          <div className="card">
            <h3>Zones — occupant starting areas</h3>
            {state.zones.length === 0 && (
              <div className="muted" style={{ marginBottom: 8 }}>
                No zones yet. Add one, then paint it on the map with the Zone tool.
              </div>
            )}
            {state.zones.map((z, i) => (
              <div key={z.id} className={`zone-row${i === activeZone && tool === 'zone' ? ' active' : ''}`}>
                <button
                  className="small"
                  onClick={() => {
                    setActiveZone(i)
                    setTool('zone')
                  }}
                  title="Paint this zone"
                >
                  {i === activeZone && tool === 'zone' ? 'Painting' : 'Paint'}
                </button>
                <input value={z.name} onChange={(e) => renameZone(i, e.target.value)} aria-label={`Zone ${z.id} name`} />
                <span className="muted">{z.cells.length}</span>
                <button className="small secondary" onClick={() => deleteZone(i)} title="Delete zone">
                  ✕
                </button>
              </div>
            ))}
            <button className="small secondary" onClick={addZone}>
              + Add zone
            </button>
          </div>

          <div className="card">
            <h3>Exits ({state.exits.length})</h3>
            {state.exits.length === 0 && (
              <div className="muted" style={{ marginBottom: 8 }}>
                Place exits with the Exit tool (⇥) — click a floor or border cell.
              </div>
            )}
            {state.exits.map((e) => (
              <div key={e.id} className="zone-row">
                <span className="exit-chip">{e.id}</span>
                <span className="muted">
                  ({e.x}, {e.y})
                </span>
                <input
                  type="number"
                  step={0.25}
                  min={0.25}
                  value={e.capacity_pps}
                  onChange={(ev) => setExitCapacity(e.id, Number(ev.target.value) || e.capacity_pps)}
                  aria-label={`Exit ${e.id} capacity`}
                  style={{ width: 76 }}
                />
                <button className="small secondary" onClick={() => deleteExit(e.id)} title="Remove exit">
                  ✕
                </button>
              </div>
            ))}
            <div className="kbd-note">Capacity in persons/second through that door.</div>
          </div>

          <div className="card">
            <h3>Layout settings</h3>
            <label className="field">
              <span className="lbl">Name</span>
              <input
                value={state.name}
                onChange={(e) => {
                  setState((p) => ({ ...p, name: e.target.value }))
                  markDirty()
                }}
              />
            </label>
            <label className="field">
              <span className="lbl">Description</span>
              <input
                value={state.description}
                onChange={(e) => {
                  setState((p) => ({ ...p, description: e.target.value }))
                  markDirty()
                }}
              />
            </label>
            <div className="grid-3">
              <label className="field">
                <span className="lbl">Width</span>
                <input
                  type="number"
                  min={4}
                  max={120}
                  value={state.width}
                  onChange={(e) => resize(Number(e.target.value) || state.width, state.height)}
                />
              </label>
              <label className="field">
                <span className="lbl">Height</span>
                <input
                  type="number"
                  min={4}
                  max={120}
                  value={state.height}
                  onChange={(e) => resize(state.width, Number(e.target.value) || state.height)}
                />
              </label>
              <label className="field">
                <span className="lbl">Cell (m)</span>
                <input
                  type="number"
                  step={0.1}
                  min={0.1}
                  max={5}
                  value={state.cell_size_m}
                  onChange={(e) => {
                    setState((p) => ({ ...p, cell_size_m: Number(e.target.value) || p.cell_size_m }))
                    markDirty()
                  }}
                />
              </label>
            </div>
          </div>
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
