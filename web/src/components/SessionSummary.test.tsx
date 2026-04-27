import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { SessionSummary } from './SessionSummary'
import type { SessionMeta } from '../types'

const stubMeta: SessionMeta = {
  session_id: 'abcd1234-aaaa-bbbb-cccc',
  version: 1,
  schema_version: '1.0',
  total_hands_played: 6,
  planned_hands: 6,
  chip_pnl: { '0': 0, '1': 4425, '2': -700, '3': -3725, '4': 150, '5': -150 },
  total_tokens: {
    '0': { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
    '1': { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
    '2': { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
    '3': { input_tokens: 5000, output_tokens: 1500, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
    '4': { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
    '5': { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
  },
  retry_summary_per_seat: {
    '0': { total_turns: 5, api_retry_count: 0, illegal_action_retry_count: 0, no_tool_retry_count: 0, tool_usage_error_count: 0, default_action_fallback_count: 0, turn_timeout_exceeded_count: 0 },
    '1': { total_turns: 5, api_retry_count: 0, illegal_action_retry_count: 0, no_tool_retry_count: 0, tool_usage_error_count: 0, default_action_fallback_count: 0, turn_timeout_exceeded_count: 0 },
    '2': { total_turns: 5, api_retry_count: 0, illegal_action_retry_count: 0, no_tool_retry_count: 0, tool_usage_error_count: 0, default_action_fallback_count: 0, turn_timeout_exceeded_count: 0 },
    '3': { total_turns: 5, api_retry_count: 2, illegal_action_retry_count: 1, no_tool_retry_count: 0, tool_usage_error_count: 0, default_action_fallback_count: 0, turn_timeout_exceeded_count: 0 },
    '4': { total_turns: 5, api_retry_count: 0, illegal_action_retry_count: 0, no_tool_retry_count: 0, tool_usage_error_count: 0, default_action_fallback_count: 0, turn_timeout_exceeded_count: 0 },
    '5': { total_turns: 5, api_retry_count: 0, illegal_action_retry_count: 0, no_tool_retry_count: 0, tool_usage_error_count: 0, default_action_fallback_count: 0, turn_timeout_exceeded_count: 0 },
  },
  tool_usage_summary: {
    '0': { total_utility_calls: 0 }, '1': { total_utility_calls: 0 },
    '2': { total_utility_calls: 0 }, '3': { total_utility_calls: 5 },
    '4': { total_utility_calls: 0 }, '5': { total_utility_calls: 0 },
  },
  seat_assignment: {
    '0': 'rule_based:tag_v1', '1': 'rule_based:tag_v1', '2': 'rule_based:tag_v1',
    '3': 'anthropic:claude-haiku-4-5', '4': 'rule_based:tag_v1', '5': 'rule_based:tag_v1',
  },
  initial_button_seat: 0,
  stop_reason: 'completed',
  session_wall_time_sec: 50,
}

describe('SessionSummary', () => {
  it('renders session-level stats', () => {
    const { getByText } = render(<SessionSummary meta={stubMeta} onClose={() => {}} />)
    expect(getByText('6 / 6')).toBeDefined()
    expect(getByText('completed')).toBeDefined()
    expect(getByText('50s')).toBeDefined()
  })

  it('renders one row per seat with PnL signed', () => {
    const { container, getByText } = render(<SessionSummary meta={stubMeta} onClose={() => {}} />)
    const rows = container.querySelectorAll('tbody tr')
    expect(rows.length).toBe(6)
    expect(getByText('+4425')).toBeDefined()
    expect(getByText('-3725')).toBeDefined()
  })

  it('shows agent identifier (short form)', () => {
    const { getAllByText, getByText } = render(<SessionSummary meta={stubMeta} onClose={() => {}} />)
    expect(getAllByText('rule_based').length).toBe(5)
    expect(getByText('claude-haiku-4-5')).toBeDefined()
  })

  it('shows OK for clean retry, error label for noisy retry', () => {
    const { getAllByText, getByText } = render(<SessionSummary meta={stubMeta} onClose={() => {}} />)
    expect(getAllByText('OK').length).toBe(5)
    expect(getByText(/api×2.*illegal×1/)).toBeDefined()
  })

  it('shows utility call counts', () => {
    const { container } = render(<SessionSummary meta={stubMeta} onClose={() => {}} />)
    expect(container.textContent).toContain('5')  // seat 3 utility calls
  })

  it('calls onClose when clicking ×', () => {
    const onClose = vi.fn()
    const { getByLabelText } = render(<SessionSummary meta={stubMeta} onClose={onClose} />)
    fireEvent.click(getByLabelText('close summary'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose on backdrop click but not card click', () => {
    const onClose = vi.fn()
    const { container, getByText } = render(
      <SessionSummary meta={stubMeta} onClose={onClose} />
    )
    fireEvent.click(getByText('session summary'))
    expect(onClose).not.toHaveBeenCalled()
    const backdrop = container.querySelector('[data-session-summary]')!
    fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalledOnce()
  })
})
