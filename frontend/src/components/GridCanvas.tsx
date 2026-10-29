// SVG rendering of a building grid with optional occupant frames.
// This component draws EXACTLY the state the backend reports: walls, exits,
// zones, blocked cells, and (when a frame is given) occupant positions with
// their recorded status codes. It never invents movement.
//
// Editing uses POINTER events captured at the SVG level (works for mouse,
// touch, and pen), computes the hovered/painted cell from event coordinates,
// and reports a hover position for the editor's status bar and brush preview.

import { useMemo, useRef, useState } from 'react'
import type { BuildingDetail, ExitSpec, Frame, OccupantFrameEntry } from '../types'

const STATUS_COLORS = ['#94a3b8', '#6366f1', '#f59e0b', '#10b981', '#a78bfa']
export const STATUS_NAMES = ['Waiting', 'Moving', 'At exit', 'Evacuated', 'Unreachable']

export const ZONE_PALETTE = [
  'rgba(99, 102, 241, 0.28)',
  'rgba(244, 63, 94, 0.25)',
  'rgba(16, 185, 129, 0.26)',
  'rgba(245, 158, 11, 0.28)',
  'rgba(168, 85, 247, 0.26)',
  'rgba(14, 165, 233, 0.28)',
]

interface GridCanvasProps {
  building: BuildingDetail
  blockedExits?: string[]
  blockedCells?: [number, number][]
  congestion?: Record<string, number>
  frame?: Frame | null
  cellPx?: number
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
  cellPx = 22,
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
    // The SVG may be CSS-scaled down (maxWidth 100%); account for that.
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
      // pointer capture unsupported: drag still works via pointerenter
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

  // ---- render -------------------------------------------------------------
  const cells: React.ReactElement[] = []
  for (let y = 0; y < building.height; y++) {
    for (let x = 0; x < building.width; x++) {
      const key = `${x},${y}`
      const isWall = wallSet.has(key)
      const isBlocked = blockedSet.has(key)
      const zoneIdx = zoneColorByCell.get(key)
      const fill = isWall
        ? 'var(--wall)'
        : isBlocked
          ? 'var(--blocked)'
          : zoneIdx !== undefined && showZoneFill
            ? ZONE_PALETTE[zoneIdx % ZONE_PALETTE.length]
            : 'var(--floor)'
      const con = congestion[key]
      const conOpacity = con && !isWall && !isBlocked ? 0.12 + 0.5 * (con / maxCongestion) : 0
      cells.push(
        <rect
          key={key}
          x={x * cellPx}
          y={y * cellPx}
          width={cellPx}
          height={cellPx}
          fill={fill}
          stroke="var(--grid-line)"
          strokeWidth={0.5}
          data-cell={key}
        >
          {conOpacity > 0 && <title>{`Blocked-move events here: ${con}`}</title>}
        </rect>,
      )
      if (conOpacity > 0) {
        cells.push(
          <rect
            key={`${key}-heat`}
            x={x * cellPx}
            y={y * cellPx}
            width={cellPx}
            height={cellPx}
            fill="#ef4444"
            opacity={conOpacity}
            pointerEvents="none"
          />,
        )
      }
    }
  }

  // Brush footprint preview under the cursor.
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

  const exitMarkers = building.exits.map((exit: ExitSpec) => {
    const blocked = blockedExitSet.has(exit.id)
    return (
      <g key={exit.id} pointerEvents="none">
        <rect
          x={exit.x * cellPx + 2}
          y={exit.y * cellPx + 2}
          width={cellPx - 4}
          height={cellPx - 4}
          rx={3.5}
          fill={blocked ? 'var(--blocked)' : 'var(--exit)'}
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

  const occupantDots =
    frame?.occupants.map((entry: OccupantFrameEntry) => {
      const [id, x, y, status] = entry
      return (
        <circle
          key={id}
          cx={x * cellPx + cellPx / 2}
          cy={y * cellPx + cellPx / 2}
          r={Math.max(2.5, cellPx * 0.27)}
          fill={STATUS_COLORS[status] ?? '#334155'}
          stroke="rgba(255,255,255,0.55)"
          strokeWidth={0.75}
          pointerEvents="none"
        >
          <title>{`Occupant ${id} — ${STATUS_NAMES[status] ?? status}`}</title>
        </circle>
      )
    }) ?? null

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
      {cells}
      {brushCells}
      {/* hover outline drawn above cells, below exits */}
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
      {occupantDots}
    </svg>
  )
}
