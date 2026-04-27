import type { ActionType } from '../types'

// Engine-internal labels (raise_to, all_in) leak into the UI as raw
// snake_case which reads as backend dump, not as a poker action. This
// formatter is the single place that turns canonical action types into
// human-friendly labels — "raise_to 250" becomes "Raise to 250", etc.
//
// Amounts get thousands-separated so "10000" reads as "10,000" — a
// 10k pot at 50/100 stakes is the difference between a half-pot bet
// and a 5x overbet, and the comma is the only typographic cue.
const TYPE_LABEL: Record<ActionType, string> = {
  fold: 'Fold',
  check: 'Check',
  call: 'Call',
  bet: 'Bet',
  raise_to: 'Raise to',
  all_in: 'All-in',
}

export function formatActionLabel(
  action: { type: ActionType; amount?: number },
): string {
  const verb = TYPE_LABEL[action.type] ?? action.type
  // all_in carries an amount but it's redundant with the "All-in" label
  // — the seat is shoving its whole stack, the chip count is shown next
  // to the seat. Keeping it would clutter every all-in turn with a
  // duplicate number.
  if (action.amount === undefined || action.amount <= 0 || action.type === 'all_in') {
    return verb
  }
  return `${verb} ${action.amount.toLocaleString()}`
}
