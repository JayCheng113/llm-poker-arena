import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { DevPanel } from './DevPanel'
import type { AgentViewSnapshot, ActionRecordPrivate } from '../types'

const stubSnapshot: AgentViewSnapshot = {
  hand_id: 1,
  turn_id: 't',
  session_id: 's',
  seat: 3,
  street: 'preflop',
  timestamp: '2026-04-26',
  view_at_turn_start: {} as never,
  iterations: [],
  final_action: { type: 'fold' },
  is_forced_blind: false,
  total_utility_calls: 0,
  api_retry_count: 0,
  illegal_action_retry_count: 0,
  no_tool_retry_count: 0,
  tool_usage_error_count: 0,
  default_action_fallback: false,
  api_error: null,
  turn_timeout_exceeded: false,
  total_tokens: {},
} as AgentViewSnapshot

describe('DevPanel', () => {
  it('renders dev panel with snapshot JSON', () => {
    const { container, getByText } = render(<DevPanel snapshot={stubSnapshot} />)
    expect(container.querySelector('[data-dev-panel]')).not.toBeNull()
    expect(getByText(/agent_view_snapshot/)).toBeDefined()
    // JSON contains seat:3
    expect(container.textContent).toMatch(/"seat": 3/)
  })

  it('renders canonical action section when provided', () => {
    const action: ActionRecordPrivate = {
      seat: 3, street: 'preflop', action_type: 'raise_to',
      amount: 300, is_forced_blind: false, turn_index: 5,
    }
    const { getByText, container } = render(
      <DevPanel snapshot={stubSnapshot} canonicalAction={action} />
    )
    expect(getByText(/canonical action/)).toBeDefined()
    expect(container.textContent).toMatch(/"action_type": "raise_to"/)
  })

  it('omits canonical action section when not provided', () => {
    const { queryByText } = render(<DevPanel snapshot={stubSnapshot} />)
    expect(queryByText(/canonical action/)).toBeNull()
  })
})
