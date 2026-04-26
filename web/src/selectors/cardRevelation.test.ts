import { describe, it, expect } from 'vitest'
import { cardRevelation } from './cardRevelation'
import type { ParsedSession, ParsedHand, PublicShowdown } from '../types'

function _hand(showdownEvent: PublicShowdown | null = null): ParsedHand {
  return {
    canonical: {
      hand_id: 0, started_at: '', ended_at: '',
      button_seat: 0, sb_seat: 1, bb_seat: 2, deck_seed: 42,
      starting_stacks: { '0': 10000 },
      hole_cards: {
        '0': ['As', 'Kh'],
        '1': ['2c', '3d'],
        '2': ['Ts', 'Jh'],
        '3': ['Qd', 'Qc'],
        '4': ['7s', '8s'],
        '5': ['9c', '9d'],
      },
      community: ['2s', '3h', '4d', '5s', '6h'],
      actions: [],
      result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: {} },
    },
    publicEvents: showdownEvent
      ? [{ type: 'hand_started', hand_id: 0, button_seat: 0, blinds: { sb: 50, bb: 100 } }, showdownEvent]
      : [{ type: 'hand_started', hand_id: 0, button_seat: 0, blinds: { sb: 50, bb: 100 } }],
    agentSnapshots: [],
  }
}

function _session(hand: ParsedHand): ParsedSession {
  return {
    meta: {
      session_id: 'demo-1', version: 2, schema_version: 'v2.0',
      total_hands_played: 1, planned_hands: 6,
      chip_pnl: {}, total_tokens: {}, retry_summary_per_seat: {},
      tool_usage_summary: {}, seat_assignment: {},
      initial_button_seat: 0, stop_reason: 'completed',
    },
    hands: { 0: hand },
  }
}

describe('cardRevelation (live mode)', () => {
  it('all face-down mid-hand (no showdown event yet)', () => {
    const sess = _session(_hand())
    const cards = cardRevelation(sess, 0, 'live', { handEnded: false })
    expect(cards['0']).toBe('face-down')
    expect(cards['3']).toBe('face-down')
    expect(cards['5']).toBe('face-down')
  })

  it('all face-down on uncalled win (no showdown event)', () => {
    const sess = _session(_hand())
    const cards = cardRevelation(sess, 0, 'live', { handEnded: true })
    expect(cards['0']).toBe('face-down')
    expect(cards['3']).toBe('face-down')
  })

  it('reveals only seats in showdown_event.revealed', () => {
    const showdown: PublicShowdown = {
      type: 'showdown', hand_id: 0,
      revealed: { '3': ['Qd', 'Qc'], '5': ['9c', '9d'] },
    }
    const sess = _session(_hand(showdown))
    const cards = cardRevelation(sess, 0, 'live', { handEnded: true })
    expect(cards['3']).toEqual(['Qd', 'Qc'])
    expect(cards['5']).toEqual(['9c', '9d'])
    expect(cards['0']).toBe('face-down')
    expect(cards['1']).toBe('face-down')
  })
})
