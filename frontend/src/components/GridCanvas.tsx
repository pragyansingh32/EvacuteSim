// SVG rendering of a building grid with optional occupant frames.
// This component draws EXACTLY the state the backend reports: walls, exits,
// zones, blocked cells, and (when a frame is given) occupant positions with
// their recorded status codes. It never invents movement.
//
// Two render modes:
//   editor    (default) — crisp per-cell strokes for precise painting.
//   cinematic — merged rounded walls (goo filter), glowing occupant dots with
//               CSS-transform interpolation between frames (smooth glide),
//               fade-out ghosts for occupants that evacuated, exit glow, and
//               soft congestion blur. Used by the run playback view.
//
// Painting uses POINTER events captured at the SVG level (mouse/touch/pen).

import { useMemo, useRef, useState } from 'react'
import type { BuildingDetail, ExitSpec, Frame, OccupantFrameEntry } from '../types'

export const STATUS_COLORS = ['#94a3b8', '#6366f1', '#f59e0b', '#10b981', '#a78bfa', '#e11d48']
export const STATUS_NAMES = ['Waiting', 'Moving', 'At exit', 'Evacuated', 'Unreachable', 'Incapacitated']

export const ZONE_PALETTE = [
  'rgba(37, 99, 235, 0.15)',
  'rgba(220, 38, 38, 0.14)',
  'rgba(22, 163, 74, 0.15)',
  'rgba(217, 119, 6, 0.16)',
  'rgba(124, 58, 237, 0.15)',
  'rgba(8, 145, 178, 0.15)',
]

export interface ExitPulse {
  key: string
  x: number
  y: number
}

interface GridCanvasProps {
  building: BuildingDetail
  blockedExits?: string[]
  blockedCells?: [number, number][]
  congestion?: Record<string, number>
  frame?: Frame | null
  /** Frame immediately before `frame` — used to fade out evacuated occupants. */
  previousFrame?: Frame | null
  /** Duration of the glide to the current frame's positions, in ms. */
  transitionMs?: number
  cellPx?: number
  cinematic?: boolean
  /** Data-driven discharge pulses at exit cells. */
  pulses?: ExitPulse[]
  /** Editor painting: phase 'down' = pointer pressed, 'drag' = moved onto cell. */
  onPaint?: (x: number, y: number, phase: 'down' | 'drag') => void
  onPaintEnd?: () => void
  onHover?: (cell: [number, number] | null) => void
  interactive?: boolean
  /** Editor brush footprint (square of this size previewed around the cursor). */
  brushSize?: number
  showZoneFill?: boolean
}

export default function GridCanvas({
  building,
  blockedExits = [],
  blockedCells = [],
  congestion = {},
  frame = null,
  previousFrame = null,
  transitionMs = 250,
  cellPx = 22,
  cinematic = false,
  pulses = [],
  onPaint,
  onPaintEnd,
  onHover,
  interactive = false,
  brushSize = 1,
  showZoneFill = true,
}: GridCanvasProps) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const paintingRef = useRef(false)
  const lastCellRef = useRef<string>('')
  const [hover, setHover] = useState<[number, number] | null>(null)

  const width = building.width * cellPx
  const height = building.height * cellPx

  const wallSet = useMemo(() => new Set(building.walls.map(([x, y]) => `${x},${y}`)), [building.walls])
  const blockedSet = useMemo(() => new Set(blockedCells.map(([x, y]) => `${x},${y}`)), [blockedCells])
  const zoneColorByCell = useMemo(() => {
    const map = new Map<string, number>()
    building.zones.forEach((zone, i) => {
      zone.cells.forEach(([x, y]) => map.set(`${x},${y}`, i))
    })
    return map
  }, [building.zones])

  const maxCongestion = useMemo(
    () => Math.max(1, ...Object.values(congestion)),
    [congestion],
  )
  const blockedExitSet = new Set(blockedExits)

  // ---- pointer handling (mouse, touch, pen) ------------------------------
  function cellFromEvent(e: React.PointerEvent): [number, number] | null {
    const svg = svgRef.current
    if (!svg) return null
    const rect = svg.getBoundingClientRect()
    const scaleX = rect.width / width
    const scaleY = rect.height / height
    const x = Math.floor((e.clientX - rect.left) / (cellPx * scaleX))
    const y = Math.floor((e.clientY - rect.top) / (cellPx * scaleY))
    if (x < 0 || y < 0 || x >= building.width || y >= building.height) return null
    return [x, y]
  }

  function handlePointerDown(e: React.PointerEvent) {
    if (!onPaint) return
    const cell = cellFromEvent(e)
    if (!cell) return
    e.preventDefault()
    try {
      svgRef.current?.setPointerCapture(e.pointerId)
    } catch {
      // pointer capture unsupported: drag still works via pointer events
    }
    paintingRef.current = true
    lastCellRef.current = `${cell[0]},${cell[1]}`
    onPaint(cell[0], cell[1], 'down')
  }

  function handlePointerMove(e: React.PointerEvent) {
    const cell = cellFromEvent(e)
    setHover(cell)
    onHover?.(cell)
    if (!onPaint || !paintingRef.current || !cell) return
    const key = `${cell[0]},${cell[1]}`
    if (key === lastCellRef.current) return
    lastCellRef.current = key
    onPaint(cell[0], cell[1], 'drag')
  }

  function endPainting() {
    if (paintingRef.current) {
      paintingRef.current = false
      onPaintEnd?.()
    }
  }

  // ---- occupants with smooth interpolation --------------------------------
  const currentOccupants = frame?.occupants ?? []
  const previousById = useMemo(() => {
    const map = new Map<number, [number, number, number]>()
    previousFrame?.occupants.forEach(([id, x, y, status]) => map.set(id, [x, y, status]))
    return map
  }, [previousFrame])

  const currentIds = useMemo(() => new Set(currentOccupants.map((o) => o[0])), [currentOccupants])
  // Occupants that were present last frame but have left the building now:
  // render at their last known position and fade out via CSS animation.
  const ghosts = useMemo(() => {
    if (!previousFrame) return []
    return [...previousById.entries()]
      .filter(([id]) => !currentIds.has(id))
      .map(([id, [x, y]]) => ({ id, x, y }))
  }, [previousFrame, previousById, currentIds])

  // ---- render -------------------------------------------------------------
  // Walls are kept in their own group so the cinematic goo filter can merge
  // them into smooth architecture without blurring zones or heat overlays.
  const wallRects: React.ReactElement[] = []
  const floorRects: React.ReactElement[] = []
  const heatRects: React.ReactElement[] = []
  for (let y = 0; y < building.height; y++) {
    for (let x = 0; x < building.width; x++) {
      const key = `${x},${y}`
      const isWall = wallSet.has(key)
      const isBlocked = blockedSet.has(key)
      const zoneIdx = zoneColorByCell.get(key)
      if (isWall || isBlocked) {
        wallRects.push(
          <rect
            key={key}
            x={x * cellPx}
            y={y * cellPx}
            width={cellPx}
            height={cellPx}
            fill={isWall ? 'var(--wall)' : 'var(--blocked)'}
            data-cell={key}
          />,
        )
        continue
      }
      const zoneFill =
        zoneIdx !== undefined && showZoneFill ? ZONE_PALETTE[zoneIdx % ZONE_PALETTE.length] : null
      floorRects.push(
        <rect
          key={key}
          x={x * cellPx}
          y={y * cellPx}
          width={cellPx}
          height={cellPx}
          fill={zoneFill ?? 'var(--floor)'}
          stroke={cinematic ? 'none' : 'var(--grid-line)'}
          strokeWidth={cinematic ? 0 : 0.5}
          data-cell={key}
        />,
      )
      const con = congestion[key]
      if (con) {
        heatRects.push(
          <rect
            key={`${key}-heat`}
            x={x * cellPx}
            y={y * cellPx}
            width={cellPx}
            height={cellPx}
            fill="#ef4444"
            opacity={0.12 + 0.5 * (con / maxCongestion)}
            pointerEvents="none"
          />,
        )
      }
    }
  }

  // Brush footprint preview under the cursor (editor only).
  const brushCells: React.ReactElement[] = []
  if (interactive && hover && brushSize > 1) {
    for (let dy = 0; dy < brushSize; dy++) {
      for (let dx = 0; dx < brushSize; dx++) {
        const bx = hover[0] + dx
        const by = hover[1] + dy
        if (bx >= building.width || by >= building.height) continue
        brushCells.push(
          <rect
            key={`brush-${bx}-${by}`}
            x={bx * cellPx}
            y={by * cellPx}
            width={cellPx}
            height={cellPx}
            fill="var(--accent)"
            opacity={0.22}
            pointerEvents="none"
          />,
        )
      }
    }
  }

  const architecture = cinematic ? (
    <>
      <g>{floorRects}</g>
      <g filter="url(#heat-blur)">{heatRects}</g>
      <g filter="url(#goo-wall)">{wallRects}</g>
    </>
  ) : (
    <>
      <g>{floorRects}</g>
      <g>{heatRects}</g>
      <g>{wallRects}</g>
    </>
  )

  const exitMarkers = building.exits.map((exit: ExitSpec) => {
    const blocked = blockedExitSet.has(exit.id)
    return (
      <g key={exit.id} pointerEvents="none">
        {cinematic && !blocked && (
          <circle
            cx={exit.x * cellPx + cellPx / 2}
            cy={exit.y * cellPx + cellPx / 2}
            r={cellPx * 0.7}
            fill="var(--exit)"
            opacity={0.25}
            className="exit-halo"
          />
        )}
        <rect
          x={exit.x * cellPx + 2}
          y={exit.y * cellPx + 2}
          width={cellPx - 4}
          height={cellPx - 4}
          rx={Math.min(5, cellPx * 0.22)}
          fill={blocked ? 'var(--blocked)' : 'var(--exit)'}
          filter={cinematic ? 'url(#soft-shadow)' : undefined}
        />
        <text
          x={exit.x * cellPx + cellPx / 2}
          y={exit.y * cellPx + cellPx / 2 + 3.5}
          textAnchor="middle"
          fontSize={Math.min(11, cellPx * 0.44)}
          fontWeight={700}
          fill="#fff"
        >
          {blocked ? '✕' : exit.id}
        </text>
        <title>{`Exit ${exit.id} — capacity ${exit.capacity_pps} p/s${blocked ? ' (BLOCKED in this scenario)' : ''}`}</title>
      </g>
    )
  })

  const dotRadius = Math.max(2.6, cellPx * 0.3)

  function occupantDot(id: number, x: number, y: number, status: number, ghost = false) {
    return (
      <g
        key={ghost ? `ghost-${id}` : `occ-${id}`}
        className={ghost ? 'occ-ghost' : 'occ'}
        style={{
          transform: `translate(${x * cellPx}px, ${y * cellPx}px)`,
          transition: !ghost && transitionMs > 0 ? `transform ${transitionMs}ms linear` : undefined,
          ...(ghost ? { animationDuration: `${transitionMs + 150}ms` } : {}),
        }}
        pointerEvents="none"
      >
        <circle
          cx={cellPx / 2}
          cy={cellPx / 2}
          r={dotRadius}
          fill={STATUS_COLORS[status] ?? '#334155'}
          filter={cinematic ? 'url(#dot-glow)' : undefined}
        >
          {!ghost && <title>{`Occupant ${id} — ${STATUS_NAMES[status] ?? status}`}</title>}
        </circle>
      </g>
    )
  }

  const occupantLayer =
    frame && frame.occupants.length > 0 ? (
      <g>
        {currentOccupants.map((entry: OccupantFrameEntry) => {
          const [id, x, y, status] = entry
          return occupantDot(id, x, y, status)
        })}
        {ghosts.map((g) => occupantDot(g.id, g.x, g.y, 3, true))}
      </g>
    ) : null

  const pulseLayer =
    pulses.length > 0 ? (
      <g pointerEvents="none">
        {pulses.map((p) => (
          <g
            key={p.key}
            style={{
              transform: `translate(${p.x * cellPx + cellPx / 2}px, ${p.y * cellPx + cellPx / 2}px)`,
            }}
          >
            <circle
              className="exit-pulse-ring"
              r={cellPx * 0.5}
              fill="none"
              stroke="var(--exit)"
              strokeWidth={2.5}
            />
          </g>
        ))}
      </g>
    ) : null

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Building grid ${building.width}x${building.height}`}
      style={{
        maxWidth: '100%',
        height: 'auto',
        display: 'block',
        touchAction: interactive ? 'none' : 'auto',
        cursor: interactive ? 'crosshair' : 'default',
        borderRadius: 10,
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endPainting}
      onPointerCancel={endPainting}
      onPointerLeave={() => {
        endPainting()
        setHover(null)
        onHover?.(null)
      }}
    >
      {cinematic && (
        <defs>
          <filter id="goo-wall" x="-5%" y="-5%" width="110%" height="110%">
            <feGaussianBlur in="SourceGraphic" stdDeviation={cellPx * 0.16} result="blur" />
            <feColorMatrix
              in="blur"
              mode="matrix"
              values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 24 -11"
            />
          </filter>
          <filter id="dot-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feDropShadow dx="0" dy="0" stdDeviation={dotRadius * 0.55} floodColor={STATUS_COLORS[1]} floodOpacity="0.55" />
          </filter>
          <filter id="heat-blur" x="-10%" y="-10%" width="120%" height="120%">
            <feGaussianBlur stdDeviation={cellPx * 0.3} />
          </filter>
          <filter id="soft-shadow" x="-60%" y="-60%" width="220%" height="220%">
            <feDropShadow dx="0" dy="1" stdDeviation="1.6" floodOpacity="0.35" />
          </filter>
        </defs>
      )}
      {architecture}
      {brushCells}
      {interactive && hover && (
        <rect
          x={hover[0] * cellPx}
          y={hover[1] * cellPx}
          width={cellPx}
          height={cellPx}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={1.6}
          rx={3}
          pointerEvents="none"
        />
      )}
      {exitMarkers}
      {pulseLayer}
      {occupantLayer}
    </svg>
  )
}
