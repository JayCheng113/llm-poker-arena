import { describe, it, expect } from 'vitest'
import { getCurrentTurn } from './getCurrentTurn'
import type { ParsedSession, AgentViewSnapshot } from '../types'

function _makeSnap(handId: number, turnIdx: number, seat: number): AgentViewSnapshot {
  return {
    hand_id: handId,
    turn_id: `${handId}-preflop-${turnIdx}`,
    session_id: 'demo-1',
    seat,
    street: 'preflop',
    timestamp: '',
    view_at_turn_start: {
      my_seat: seat, pot: 150 + turnIdx * 50, my_stack: 10000,
      current_bet_to_match: 100, to_call: 100, pot_odds_required: 0.4,
      effective_stack: 10000, street: 'preflop',
      legal_actions: { tools: [{ name: 'fold', args: {} }] },
      seats_public: [],
    },
    iterations: [],
    final_action: { type: 'raise_to', amount: 300 },
    is_forced_blind: false,
    total_utility_calls: 0,
    api_retry_count: 0, illegal_action_retry_count: 0,
    no_tool_retry_count: 0, tool_usage_error_count: 0,
    default_action_fallback: false, api_error: null,
    turn_timeout_exceeded: false,
    total_tokens: { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
    wall_time_ms: 0,
    agent: { provider: 'anthropic', model: 'claude-haiku-4-5', version: 'p', temperature: 0.7, seed: null },
  }
}

const sess: ParsedSession = {
  meta: {
    session_id: 'demo-1', version: 2, schema_version: 'v2.0',
    total_hands_played: 1, planned_hands: 6,
    chip_pnl: {}, total_tokens: {}, retry_summary_per_seat: {},
    tool_usage_summary: {},
    seat_assignment: { '3': 'anthropic:claude-haiku-4-5' },
    initial_button_seat: 0, stop_reason: 'completed',
  },
  hands: {
    0: {
      canonical: {
        hand_id: 0, started_at: '', ended_at: '',
        button_seat: 0, sb_seat: 1, bb_seat: 2, deck_seed: 42,
        starting_stacks: { '0': 10000, '1': 10000, '2': 10000, '3': 10000, '4': 10000, '5': 10000 },
        hole_cards: { '3': ['As', 'Kh'] },
        community: ['2s', '3h', '4d'],
        actions: [], result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: {} },
      },
      publicEvents: [],
      agentSnapshots: [_makeSnap(0, 0, 3), _makeSnap(0, 1, 4)],
    },
  },
}

describe('getCurrentTurn', () => {
  it('returns actor + pot from snapshot at given turn', () => {
    const t = getCurrentTurn(sess, 0, 0)
    expect(t.actor).toBe(3)
    expect(t.pot).toBe(150)
    expect(t.street).toBe('preflop')
  })

  it('returns later turn correctly', () => {
    const t = getCurrentTurn(sess, 0, 1)
    expect(t.actor).toBe(4)
    expect(t.pot).toBe(200)
  })

  it('returns last commit action via reasoning', () => {
    const t = getCurrentTurn(sess, 0, 0)
    expect(t.commitAction).toEqual({ type: 'raise_to', amount: 300 })
  })
})
