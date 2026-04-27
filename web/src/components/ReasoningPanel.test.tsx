import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ReasoningPanel } from './ReasoningPanel'
import type { IterationRecord, ActionType } from '../types'

const _iter = (overrides: Partial<IterationRecord>): IterationRecord => ({
  step: 1, request_messages_digest: 'd',
  provider_response_kind: 'text_only', tool_call: null, tool_result: null,
  text_content: '', tokens: { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
  wall_time_ms: 0,
  ...overrides,
})

describe('ReasoningPanel', () => {
  it('shows actor seat in header', () => {
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={[]} commitAction={{ type: 'fold' }} />
    )
    expect(getByText(/seat 3.*UTG/i)).toBeDefined()
  })

  it('renders text_content for each iteration', () => {
    const iters = [
      _iter({ text_content: 'AKo + UTG raise → 3-bet for value' }),
    ]
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={iters} commitAction={{ type: 'raise_to', amount: 900 }} />
    )
    expect(getByText(/3-bet for value/)).toBeDefined()
  })

  it('renders tool_call + tool_result for utility iterations', () => {
    const iters = [
      _iter({
        provider_response_kind: 'tool_use',
        tool_call: { name: 'pot_odds', args: { to_call: 300, pot: 750 }, tool_use_id: 'p1' },
        tool_result: { value: 0.286 },
        text_content: 'checking pot odds',
      }),
    ]
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={iters} commitAction={{ type: 'fold' }} />
    )
    expect(getByText(/pot_odds/)).toBeDefined()
    expect(getByText(/0\.286/)).toBeDefined()
  })

  it('renders commit action prominently', () => {
    const commit: { type: ActionType; amount?: number } = { type: 'raise_to', amount: 900 }
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={[]} commitAction={commit} />
    )
    expect(getByText(/raise_to.*900/)).toBeDefined()
  })

  it('shows rule-based hint when isRuleBased and no iterations', () => {
    const { getByText, queryByText } = render(
      <ReasoningPanel
        actor={2}
        positionLabel="BB"
        iterations={[]}
        commitAction={{ type: 'fold' }}
        isRuleBased
      />
    )
    expect(getByText(/rule-based agent/i)).toBeDefined()
    expect(queryByText(/no iterations recorded/i)).toBeNull()
  })

  it('shows generic empty hint when LLM with no iterations', () => {
    const { getByText } = render(
      <ReasoningPanel
        actor={3}
        positionLabel="UTG"
        iterations={[]}
        commitAction={{ type: 'fold' }}
        isRuleBased={false}
      />
    )
    expect(getByText(/no iterations recorded/i)).toBeDefined()
  })

  it('renders snapshot-level badges when showDebugBadges + retry counts > 0', () => {
    const snapshot = {
      api_retry_count: 2,
      illegal_action_retry_count: 1,
      no_tool_retry_count: 0,
      tool_usage_error_count: 0,
      default_action_fallback: true,
      api_error: { type: 'rate_limit', detail: 'too many' },
      turn_timeout_exceeded: false,
    } as never as import('../types').AgentViewSnapshot
    const { container, getByText } = render(
      <ReasoningPanel
        actor={3} positionLabel="UTG"
        iterations={[]}
        commitAction={{ type: 'fold' }}
        snapshot={snapshot}
        showDebugBadges
      />
    )
    expect(container.querySelector('[data-snapshot-badges]')).not.toBeNull()
    expect(getByText(/api_error: rate_limit/)).toBeDefined()
    expect(getByText(/api_retry × 2/)).toBeDefined()
    expect(getByText(/illegal × 1/)).toBeDefined()
    expect(getByText(/fallback/)).toBeDefined()
  })

  it('hides snapshot badges when showDebugBadges=false', () => {
    const snapshot = {
      api_retry_count: 5, illegal_action_retry_count: 0, no_tool_retry_count: 0,
      tool_usage_error_count: 0, default_action_fallback: false,
      api_error: null, turn_timeout_exceeded: false,
    } as never as import('../types').AgentViewSnapshot
    const { container } = render(
      <ReasoningPanel
        actor={3} positionLabel="UTG" iterations={[]}
        commitAction={{ type: 'fold' }}
        snapshot={snapshot}
      />
    )
    expect(container.querySelector('[data-snapshot-badges]')).toBeNull()
  })

  it('renders provider_response_kind=error badge when showDebugBadges', () => {
    const iters = [
      _iter({ provider_response_kind: 'error', text_content: 'err' }),
    ]
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={iters}
                      commitAction={{ type: 'fold' }} showDebugBadges />
    )
    expect(getByText(/^error$/)).toBeDefined()
  })

  it('renders reasoning_artifacts.kind labels when showDebugBadges', () => {
    const iters = [
      _iter({
        text_content: 't',
        reasoning_artifacts: [{ kind: 'thinking_block' }, { kind: 'redacted' }],
      }),
    ]
    const { getByText } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={iters}
                      commitAction={{ type: 'fold' }} showDebugBadges />
    )
    expect(getByText(/thinking_block/)).toBeDefined()
    expect(getByText(/redacted/)).toBeDefined()
  })
})
