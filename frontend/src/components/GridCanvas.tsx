// SVG rendering of a building grid with optional occupant frames.
// This component draws EXACTLY the state the backend reports: walls, exits,
// zones, blocked cells, and (when a frame is given) occupant positions with
// their recorded status codes. It never invents movement.

import { useMemo } from 'react'
import type { BuildingDetail, ExitSpec, Frame, OccupantFrameEntry } from '../types'

const STATUS_COLORS = ['#94a3b8', '#1f6feb', '#b45309', '#15803d', '#7c3aed']
export const STATUS_NAMES = ['Waiting', 'Moving', 'At exit', 'Evacuated', 'Unreachable']

interface GridCanvasProps {
  building: BuildingDetail
  blockedExits?: string[]
  blockedCells?: [number, number][]
  congestion?: Record<string, number>
  frame?: Frame | null
  cellPx?: number
  onCellClick?: (x: number, y: number, event: React.MouseEvent) => void
  onCellMouseDown?: (x: number, y: number, event: React.MouseEvent) => void
  onCellMouseEnter?: (x: number, y: number, event: React.MouseEvent) => void
  onCellMouseUp?: (x: number, y: number, event: React.MouseEvent) => void
  interactive?: boolean
  showZoneFill?: boolean
}

export default function GridCanvas({
  building,
  blockedExits = [],
  blockedCells = [],
  congestion = {},
  frame = null,
  cellPx = 22,
  onCellClick,
  onCellMouseDown,
  onCellMouseEnter,
  onCellMouseUp,
  interactive = false,
  showZoneFill = true,
}: GridCanvasProps) {
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
  const zonePalette = ['#93c5fd', '#fca5a5', '#86efac', '#fdba74', '#c4b5fd', '#6ee7b7']

  const maxCongestion = useMemo(
    () => Math.max(1, ...Object.values(congestion)),
    [congestion],
  )

  const maxCong = maxCongestion
  const blockedExitSet = new Set(blockedExits)

  function isExitBlocked(exit: ExitSpec): boolean {
    return blockedExitSet.has(exit.id)
  }

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
          ? '#7f1d1d'
          : zoneIdx !== undefined && showZoneFill
            ? zonePalette[zoneIdx % zonePalette.length]
            : 'var(--floor)'
      const con = congestion[key]
      const conOpacity = con && !isWall && !isBlocked ? 0.15 + 0.55 * (con / maxCong) : 0
      cells.push(
        <rect
          key={key}
          x={x * cellPx}
          y={y * cellPx}
          width={cellPx}
          height={cellPx}
          fill={fill}
          stroke="#d7dce3"
          strokeWidth={0.5}
          data-cell={key}
          onClick={onCellClick ? (e) => onCellClick(x, y, e) : undefined}
          onMouseDown={onCellMouseDown ? (e) => onCellMouseDown(x, y, e) : undefined}
          onMouseEnter={onCellMouseEnter ? (e) => onCellMouseEnter(x, y, e) : undefined}
          onMouseUp={onCellMouseUp ? (e) => onCellMouseUp(x, y, e) : undefined}
          style={{ cursor: interactive ? 'crosshair' : 'default' }}
        >
          {conOpacity > 0 && (
            <title>{`Blocked-move events here: ${con}`}</title>
          )}
        </rect>,
      )
      // Congestion heat overlay
      if (conOpacity > 0) {
        cells.push(
          <rect
            key={`${key}-heat`}
            x={x * cellPx}
            y={y * cellPx}
            width={cellPx}
            height={cellPx}
            fill="#dc2626"
            opacity={conOpacity}
            pointerEvents="none"
          />,
        )
      }
    }
  }

  const exitMarkers = building.exits.map((exit) => {
    const blocked = isExitBlocked(exit)
    return (
      <g key={exit.id} pointerEvents="none">
        <rect
          x={exit.x * cellPx + 2}
          y={exit.y * cellPx + 2}
          width={cellPx - 4}
          height={cellPx - 4}
          rx={3}
          fill={blocked ? '#7f1d1d' : 'var(--exit)'}
        />
        <text
          x={exit.x * cellPx + cellPx / 2}
          y={exit.y * cellPx + cellPx / 2 + 3.5}
          textAnchor="middle"
          fontSize={10}
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
          r={Math.max(2.5, cellPx * 0.28)}
          fill={STATUS_COLORS[status] ?? '#333'}
          pointerEvents="none"
        >
          <title>{`Occupant ${id} — ${STATUS_NAMES[status] ?? status}`}</title>
        </circle>
      )
    }) ?? null

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Building grid ${building.width}x${building.height}`}
      style={{ maxWidth: '100%', height: 'auto', display: 'block' }}
      onMouseUp={onCellMouseUp ? () => undefined : undefined}
    >
      {cells}
      {exitMarkers}
      {occupantDots}
    </svg>
  )
}
