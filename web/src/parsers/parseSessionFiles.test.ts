import { describe, it, expect } from 'vitest'
import { parseSessionFiles, parseSessionFromFiles } from './parseSessionFiles'

const META = JSON.stringify({
  session_id: 'test', version: 1, schema_version: '1',
  total_hands_played: 1, planned_hands: 1,
  chip_pnl: { '0': 0 },
  total_tokens: { '0': { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } },
  retry_summary_per_seat: { '0': { total_turns: 1, api_retry_count: 0, illegal_action_retry_count: 0, no_tool_retry_count: 0, tool_usage_error_count: 0, default_action_fallback_count: 0, turn_timeout_exceeded_count: 0 } },
  tool_usage_summary: { '0': { total_utility_calls: 0 } },
  seat_assignment: { '0': 'rule_based:tag_v1' },
  initial_button_seat: 0, stop_reason: 'completed',
})

const CANONICAL = JSON.stringify({
  hand_id: 0, button_seat: 0, sb_seat: 1, bb_seat: 2,
  starting_stacks: { '0': 10000 }, hole_cards: { '0': ['As', 'Kc'] },
  community: ['Ah', '2d', '3c', '4h', '5s'],
  actions: [],
  result: { showdown: false, winners: [], side_pots: [], final_invested: {}, net_pnl: { '0': 0 } },
}) + '\n'

const PUBLIC = JSON.stringify({ hand_id: 0, street_events: [] }) + '\n'
const SNAPSHOTS = ''  // empty session

describe('parseSessionFiles', () => {
  it('builds ParsedSession from four text strings', () => {
    const session = parseSessionFiles({
      canonical: CANONICAL,
      public: PUBLIC,
      snapshots: SNAPSHOTS,
      meta: META,
    })
    expect(session.meta.session_id).toBe('test')
    expect(Object.keys(session.hands)).toEqual(['0'])
    expect(session.hands[0].canonical.hand_id).toBe(0)
    expect(session.hands[0].publicEvents).toEqual([])
    expect(session.hands[0].agentSnapshots).toEqual([])
  })
})

function fakeFile(name: string, body: string): File {
  return new File([body], name, { type: 'text/plain' })
}

describe('parseSessionFromFiles', () => {
  it('finds the four files by name and parses them', async () => {
    const dt = new DataTransfer()
    dt.items.add(fakeFile('canonical_private.jsonl', CANONICAL))
    dt.items.add(fakeFile('public_replay.jsonl', PUBLIC))
    dt.items.add(fakeFile('agent_view_snapshots.jsonl', SNAPSHOTS))
    dt.items.add(fakeFile('meta.json', META))
    const session = await parseSessionFromFiles(dt.files)
    expect(session.meta.session_id).toBe('test')
  })

  it('throws when a required file is missing', async () => {
    const dt = new DataTransfer()
    dt.items.add(fakeFile('canonical_private.jsonl', CANONICAL))
    dt.items.add(fakeFile('meta.json', META))
    await expect(parseSessionFromFiles(dt.files))
      .rejects.toThrow(/public_replay\.jsonl.*agent_view_snapshots\.jsonl/)
  })
})
