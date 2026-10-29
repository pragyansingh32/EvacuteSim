// Restore points: full-workspace snapshots. Every restore first auto-snapshots
// the current state, so nothing can ever be lost by restoring.

import { useCallback, useEffect, useState } from 'react'
import { api, ApiRequestError, type RestorePoint } from '../api/client'
import { DisclaimerBanner, ErrorAlert, fmtBytes } from '../components/ui'

export default function RestorePointsPage() {
  const [points, setPoints] = useState<RestorePoint[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      setPoints(await api.listRestorePoints())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function create() {
    if (!name.trim()) {
      setError('Give the restore point a name.')
      return
    }
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      await api.createRestorePoint(name.trim())
      setName('')
      setInfo('Restore point created.')
      await refresh()
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function restore(id: number, snapshotName: string) {
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      const result = await api.restoreFromPoint(id)
      const total = Object.values(result.restored).reduce((a, b) => a + b, 0)
      setInfo(
        `Restored '${snapshotName}' — ${total} records. The previous state was auto-backed up as a new restore point.`,
      )
      await refresh()
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
    } finally {
      setBusy(false)
      setConfirming(null)
    }
  }

  async function remove(id: number) {
    setBusy(true)
    setError(null)
    try {
      await api.deleteRestorePoint(id)
      await refresh()
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1>Restore Points</h1>
      <p className="page-sub">
        Capture the entire workspace — buildings, scenarios, run records, experiments — as a
        named snapshot. Restoring replaces the current data with the snapshot; the current state
        is always auto-backed up first, so a restore is itself reversible.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />
      {info && <div className="alert info">{info}</div>}

      <div className="card">
        <h3>Create a restore point</h3>
        <div className="toolbar">
          <input
            value={name}
            placeholder="e.g. Working state before advisor changes"
            onChange={(e) => setName(e.target.value)}
            style={{ maxWidth: 440 }}
            onKeyDown={(e) => e.key === 'Enter' && create()}
          />
          <button onClick={create} disabled={busy}>
            {busy ? 'Saving…' : 'Create restore point'}
          </button>
        </div>
        <div className="kbd-note">
          Snapshots are stored as JSON documents under <code>backend/data/snapshots/</code> and
          include run records with their full configurations and seeds.
        </div>
      </div>

      <div className="card">
        <h3>Snapshots ({points.length})</h3>
        {points.length === 0 ? (
          <div className="empty">No restore points yet — create one before making big changes.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>Created</th>
                <th>Contents</th>
                <th className="num">Size</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.id}>
                  <td>
                    {p.name}
                    {p.is_auto && <span className="muted"> (auto-backup)</span>}
                  </td>
                  <td className="muted">{new Date(p.created_at).toLocaleString()}</td>
                  <td className="muted">
                    {Object.entries(p.counts)
                      .filter(([, n]) => n > 0)
                      .map(([k, n]) => `${n} ${k}`)
                      .join(', ') || 'empty'}
                  </td>
                  <td className="num muted">{fmtBytes(p.size_bytes)}</td>
                  <td>
                    {confirming === p.id ? (
                      <span className="toolbar" style={{ margin: 0 }}>
                        <button
                          className="small danger"
                          disabled={busy}
                          onClick={() => restore(p.id, p.name)}
                        >
                          Replace data
                        </button>
                        <button className="small secondary" onClick={() => setConfirming(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button className="small secondary" onClick={() => setConfirming(p.id)} disabled={busy}>
                        Restore
                      </button>
                    )}{' '}
                    <button className="small secondary" onClick={() => remove(p.id)} disabled={busy || p.is_auto} title={p.is_auto ? 'Auto-backups keep until you delete them' : 'Delete snapshot'}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
