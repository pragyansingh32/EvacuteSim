import { render } from '@testing-library/react'
import GridCanvas from './GridCanvas'
import type { BuildingDetail, Frame } from '../types'

const building: BuildingDetail = {
  id: 1,
  name: 'Test',
  description: '',
  width: 6,
  height: 4,
  cell_size_m: 0.5,
  is_sample: false,
  created_at: '',
  updated_at: '',
  warnings: [],
  walls: [[1, 1]],
  exits: [{ id: 'E1', x: 5, y: 1, capacity_pps: 1.0 }],
  zones: [{ id: 'Z', name: 'Z', cells: [[0, 0]] }],
}

describe('GridCanvas', () => {
  it('renders the grid with the correct dimensions', () => {
    const { container } = render(<GridCanvas building={building} />)
    const svg = container.querySelector('svg')
    expect(svg).toBeTruthy()
    expect(svg?.getAttribute('viewBox')).toBe('0 0 132 88') // 6*22 x 4*22
  })

  it('draws exactly one dot per occupant in the frame', () => {
    const frame: Frame = { t: 2.0, occupants: [[0, 0, 0, 1], [1, 3, 2, 2]] }
    const { container } = render(<GridCanvas building={building} frame={frame} />)
    expect(container.querySelectorAll('circle')).toHaveLength(2)
  })

  it('marks blocked exits distinctly', () => {
    const { container } = render(<GridCanvas building={building} blockedExits={['E1']} />)
    expect(container.textContent).toContain('✕')
  })
})
