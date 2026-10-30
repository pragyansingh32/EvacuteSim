import { describe, expect, it } from 'vitest'
import { formatRunRow } from './client'

describe('formatRunRow', () => {
  it('formats metrics without inventing values', () => {
    const row = formatRunRow({
      run_id: 3,
      name: 'R',
      strategy: 'nearest_exit',
      seed: 1,
      metrics: {
        engine_status: 'completed',
        sim_time_s: 42.5,
        steps: 100,
        total_occupants: 10,
        evacuated_count: 10,
        unreachable_count: 0,
        incapacitated_count: 0,
        disaster: { type: 'none', intensity: 0 },
        remaining_count: 0,
        t50_s: 20,
        t90_s: 40,
        t95_s: 41,
        mean_evacuation_time_s: 22,
        max_evacuation_time_s: 42.5,
        queue_total_s: 5,
        queue_mean_s: 0.5,
        queue_max_s: 2,
        fallback_count: 0,
        exit_stats: [],
        congestion: {},
        warnings: [],
      },
    })
    expect(row['Evacuated']).toBe('10/10')
    expect(row['Sim time (s)']).toBe(42.5)
    expect(row['T90 (s)']).toBe(40)
  })
})
