import { describe, it, expect } from 'vitest'
import { seatPosition } from './polar'

describe('seatPosition', () => {
  it('seat 3 sits at bottom-center (positive y, x ≈ 0 with anchor)', () => {
    const { x, y } = seatPosition(3, 6, 100, 50)
    expect(Math.abs(x)).toBeLessThan(0.01)
    expect(y).toBeCloseTo(50, 2)
  })

  it('seat 0 is opposite seat 3 (top-ish)', () => {
    const { y: y3 } = seatPosition(3, 6, 100, 50)
    const { x: x0, y: y0 } = seatPosition(0, 6, 100, 50)
    expect(y0).toBeCloseTo(-y3, 2)
    expect(Math.abs(x0)).toBeLessThan(0.01)
  })

  it('all seats spread around the ellipse (distinct positions)', () => {
    const positions = Array.from({ length: 6 }, (_, i) => seatPosition(i, 6, 100, 50))
    for (let i = 0; i < 6; i++) {
      for (let j = i + 1; j < 6; j++) {
        const dist = Math.hypot(positions[i].x - positions[j].x, positions[i].y - positions[j].y)
        expect(dist).toBeGreaterThan(10)
      }
    }
  })
})
