// Small shared UI primitives.

import type { ReactNode } from 'react'
import type { RunSummary } from '../types'
import { STRATEGY_LABELS, STATUS_LABELS } from '../types'

export function DisclaimerBanner({ children }: { children?: ReactNode }) {
  return (
    <div className="disclaimer">
      {children ??
        'Simulation outputs depend on model assumptions. EvacuateSim is an educational/research tool — not a certified fire-safety system and not a safety prediction for any real building.'}
    </div>
  )
}

export function StatusBadge({ status }: { status: RunSummary['status'] }) {
  return <span className={`badge ${status}`}>{STATUS_LABELS[status] ?? status}</span>
}

export function MetricCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: 'accent' | 'ok' | 'warn' | 'danger'
}) {
  return (
    <div className={`card metric-card${tone && tone !== 'accent' ? ` tone-${tone}` : ''}`}>
      <div className="label">{label}</div>
      <div className="value">{value ?? '—'}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  )
}

export function ErrorAlert({
  message,
  details,
}: {
  message: string | null
  details?: { loc: (string | number)[]; msg: string }[]
}) {
  if (!message) return null
  return (
    <div className="alert error">
      {message}
      {details && details.length > 0 && (
        <ul style={{ margin: '6px 0 0 18px' }}>
          {details.map((d, i) => (
            <li key={i}>
              {d.loc.join(' → ')}: {d.msg}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function strategyLabel(s: string): string {
  return STRATEGY_LABELS[s] ?? s
}

export function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function fmt(v: number | null | undefined, digits = 1): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}
