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
    const { container } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={[]} commitAction={{ type: 'fold' }} />
    )
    // header is now: provider/agent label on top, "UTG · seat 3 · is acting" below
    expect(container.textContent).toMatch(/UTG/)
    expect(container.textContent).toMatch(/seat 3/)
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
    const { container } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={[]} commitAction={commit} />
    )
    // commit row now: lucide icon + formatted action label ("Raise to 900")
    expect(container.textContent).toMatch(/Raise to/)
    expect(container.textContent).toMatch(/900/)
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

  it('renders readable reasoning content (raw / summary / thinking_block) in normal mode', () => {
    // Critical for GPT-5 reasoning summary visibility — the panel used
    // to gate ALL artifact display on dev mode + only show the kind tag,
    // never the content. Smoke test caught it; regression test for
    // both summary (OpenAI Responses API) and raw (DeepSeek/Kimi).
    const iters = [
      _iter({
        text_content: '',  // GPT-5 path: rationale_required=False ⇒ no prose
        reasoning_artifacts: [
          { kind: 'summary', content: 'Weighing pot odds vs implied odds with 3-2 in BB.' },
        ],
      }),
      _iter({
        text_content: '',
        reasoning_artifacts: [
          { kind: 'raw', content: 'Internal CoT from DeepSeek thinking mode.' },
        ],
      }),
    ]
    const { getByText, container } = render(
      <ReasoningPanel actor={2} positionLabel="BB" iterations={iters}
                      commitAction={{ type: 'fold' }} />
    )
    // Content visible without dev mode:
    expect(getByText(/Weighing pot odds vs implied odds/)).toBeDefined()
    expect(getByText(/Internal CoT from DeepSeek/)).toBeDefined()
    // Header labels for the two readable kinds:
    expect(container.querySelector('[data-reasoning-artifact="summary"]')).not.toBeNull()
    expect(container.querySelector('[data-reasoning-artifact="raw"]')).not.toBeNull()
  })

  it('hides opaque artifact kinds (encrypted / redacted / unavailable) from the inline view', () => {
    // These kinds carry no usable content for the user. They still
    // appear as dev-mode tags (covered by the previous test) but should
    // never produce an inline content block.
    const iters = [
      _iter({
        text_content: '',
        reasoning_artifacts: [
          { kind: 'encrypted', content: '[opaque blob]' },
          { kind: 'redacted', content: '[redacted]' },
          { kind: 'unavailable' },
        ],
      }),
    ]
    const { container } = render(
      <ReasoningPanel actor={3} positionLabel="UTG" iterations={iters}
                      commitAction={{ type: 'fold' }} />
    )
    expect(container.querySelector('[data-reasoning-artifact="encrypted"]')).toBeNull()
    expect(container.querySelector('[data-reasoning-artifact="redacted"]')).toBeNull()
    expect(container.querySelector('[data-reasoning-artifact="unavailable"]')).toBeNull()
  })
})
