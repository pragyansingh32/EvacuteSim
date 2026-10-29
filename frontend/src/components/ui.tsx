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
}: {
  label: string
  value: ReactNode
  hint?: string
}) {
  return (
    <div className="card metric-card">
      <div className="label">{label}</div>
      <div className="value">{value ?? '—'}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  )
}

export function ErrorAlert({ message }: { message: string | null }) {
  if (!message) return null
  return <div className="alert error">{message}</div>
}

export function strategyLabel(s: string): string {
  return STRATEGY_LABELS[s] ?? s
}

export function fmt(v: number | null | undefined, digits = 1): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}
