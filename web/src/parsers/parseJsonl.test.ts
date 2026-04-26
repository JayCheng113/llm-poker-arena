import { describe, it, expect } from 'vitest'
import {
  parseCanonicalPrivate,
  parsePublicReplay,
  parseAgentSnapshots,
  parseMeta,
} from './parseJsonl'

describe('parseCanonicalPrivate', () => {
  it('parses one hand line', () => {
    const text = JSON.stringify({
      hand_id: 0,
      started_at: '2026-04-26T00:00:00Z',
      ended_at: '2026-04-26T00:00:30Z',
      button_seat: 0,
      sb_seat: 1,
      bb_seat: 2,
      deck_seed: 42,
      starting_stacks: { '0': 10000, '1': 10000 },
      hole_cards: { '0': ['As', 'Kh'], '1': ['Qd', 'Qc'] },
      community: ['2s', '3h', '4d'],
      actions: [],
      result: {
        showdown: false, winners: [], side_pots: [],
        final_invested: {}, net_pnl: {},
      },
    })
    const hands = parseCanonicalPrivate(text)
    expect(hands).toHaveLength(1)
    expect(hands[0].hand_id).toBe(0)
    expect(hands[0].hole_cards['0']).toEqual(['As', 'Kh'])
  })

  it('parses multiple lines', () => {
    const text = [
      JSON.stringify({ hand_id: 0, started_at: '', ended_at: '', button_seat: 0, sb_seat: 1, bb_seat: 2, deck_seed: 42, starting_stacks: {}, hole_cards: {}, community: [], actions: [], result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: {} } }),
      JSON.stringify({ hand_id: 1, started_at: '', ended_at: '', button_seat: 1, sb_seat: 2, bb_seat: 3, deck_seed: 43, starting_stacks: {}, hole_cards: {}, community: [], actions: [], result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: {} } }),
    ].join('\n')
    expect(parseCanonicalPrivate(text)).toHaveLength(2)
  })
})

describe('parsePublicReplay', () => {
  it('parses one hand record with events', () => {
    const text = JSON.stringify({
      hand_id: 0,
      street_events: [
        { type: 'hand_started', hand_id: 0, button_seat: 0, blinds: { sb: 50, bb: 100 } },
        { type: 'action', hand_id: 0, seat: 3, street: 'preflop', action: { type: 'raise_to', amount: 300 } },
      ],
    })
    const records = parsePublicReplay(text)
    expect(records).toHaveLength(1)
    expect(records[0].street_events).toHaveLength(2)
    expect(records[0].street_events[0].type).toBe('hand_started')
  })
})

describe('parseAgentSnapshots', () => {
  it('parses one snapshot line', () => {
    const text = JSON.stringify({
      hand_id: 0,
      turn_id: '0-preflop-0',
      session_id: 'demo-1',
      seat: 3,
      street: 'preflop',
      timestamp: '',
      view_at_turn_start: { my_seat: 3, pot: 150, my_stack: 10000, current_bet_to_match: 100, to_call: 100, pot_odds_required: 0.4, effective_stack: 10000, street: 'preflop', legal_actions: { tools: [] }, seats_public: [] },
      iterations: [],
      final_action: { type: 'raise_to', amount: 300 },
      is_forced_blind: false,
      total_utility_calls: 0,
      api_retry_count: 0,
      illegal_action_retry_count: 0,
      no_tool_retry_count: 0,
      tool_usage_error_count: 0,
      default_action_fallback: false,
      api_error: null,
      turn_timeout_exceeded: false,
      total_tokens: { input_tokens: 100, output_tokens: 20, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
      wall_time_ms: 1000,
      agent: { provider: 'anthropic', model: 'claude-haiku-4-5', version: 'phase3a', temperature: 0.7, seed: null },
    })
    const snaps = parseAgentSnapshots(text)
    expect(snaps).toHaveLength(1)
    expect(snaps[0].seat).toBe(3)
    expect(snaps[0].final_action.type).toBe('raise_to')
  })
})

describe('parseMeta', () => {
  it('parses meta.json', () => {
    const text = JSON.stringify({
      session_id: 'demo-1',
      version: 2,
      schema_version: 'v2.0',
      total_hands_played: 6,
      planned_hands: 6,
      chip_pnl: { '0': -50, '3': 100, '5': -50 },
      total_tokens: {},
      retry_summary_per_seat: {},
      tool_usage_summary: {},
      seat_assignment: { '3': 'anthropic:claude-haiku-4-5' },
      initial_button_seat: 0,
      stop_reason: 'completed',
    })
    const meta = parseMeta(text)
    expect(meta.session_id).toBe('demo-1')
    expect(meta.total_hands_played).toBe(6)
    expect(meta.chip_pnl['3']).toBe(100)
  })
})
