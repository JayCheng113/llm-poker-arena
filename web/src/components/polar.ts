/**
 * Compute the (x, y) position on an ellipse for a seat index.
 *
 * Convention (spec §266): seat 3 sits at bottom-center (270° / 6 o'clock,
 * +y direction in screen coords). Other seats distribute counterclockwise
 * at 60° increments.
 *
 * Returns {x, y} in pixel offsets from table center.
 * y is positive DOWN (screen coords): 90° = top (negative y),
 * 270° = bottom (positive y).
 */
export function seatPosition(
  seatIdx: number,
  n: number,
  rx: number,
  ry: number,
): { x: number; y: number } {
  // Seat 3 anchor at 270° (bottom). Each seat += 60° counterclockwise.
  const baseDeg = 270 // seat 3
  const deltaDeg = ((seatIdx - 3) * 360) / n
  const angleDeg = baseDeg - deltaDeg // counterclockwise visually = subtract
  const angleRad = (angleDeg * Math.PI) / 180
  const x = rx * Math.cos(angleRad)
  // Screen y axis points DOWN; sin(270°) = -1 should map to bottom (positive y).
  const y = -ry * Math.sin(angleRad)
  return { x, y }
}
