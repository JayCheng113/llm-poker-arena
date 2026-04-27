// Mirror of Pydantic schemas in src/llm_poker_arena/{engine/views.py,
// agents/llm/types.py, storage/schemas.py}. JSON shapes only — no
// runtime validation (we trust generated artifacts).

export type Suit = 's' | 'h' | 'd' | 'c'
export type Rank = '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' | 'T' | 'J' | 'Q' | 'K' | 'A'
export type CardStr = `${Rank}${Suit}` // e.g. "As", "Kh"

export type Street = 'preflop' | 'flop' | 'turn' | 'river'
export type ActionType = 'fold' | 'check' | 'call' | 'bet' | 'raise_to' | 'all_in'
export type SeatStatus = 'in_hand' | 'folded' | 'all_in'

// === meta.json ===
export interface SessionMeta {
  session_id: string
  version: number
  schema_version: string
  total_hands_played: number
  planned_hands: number
  chip_pnl: { [seatStr: string]: number }
  total_tokens: { [seatStr: string]: TokenCounts }
  retry_summary_per_seat: { [seatStr: string]: RetrySummary }
  tool_usage_summary: { [seatStr: string]: { total_utility_calls: number } }
  seat_assignment: { [seatStr: string]: string }
  initial_button_seat: number
  stop_reason: string
  session_wall_time_sec?: number
  estimated_cost_breakdown?: { [k: string]: unknown }
  hud_per_seat?: { [seatStr: string]: HudCounters }
  hud_hands_counted?: number
}

export interface HudCounters {
  vpip_actions: number
  pfr_actions: number
  three_bet_chances: number
  three_bet_actions: number
  af_aggressive: number
  af_passive: number
  wtsd_chances: number
  wtsd_actions: number
}

export interface TokenCounts {
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

export interface RetrySummary {
  total_turns: number
  api_retry_count: number
  illegal_action_retry_count: number
  no_tool_retry_count: number
  tool_usage_error_count: number
  default_action_fallback_count: number
  turn_timeout_exceeded_count: number
}

// === canonical_private.jsonl ===
export interface CanonicalPrivateHand {
  hand_id: number
  started_at: string
  ended_at: string
  button_seat: number
  sb_seat: number
  bb_seat: number
  deck_seed: number
  starting_stacks: { [seatStr: string]: number }
  hole_cards: { [seatStr: string]: [CardStr, CardStr] }
  community: CardStr[]
  actions: ActionRecordPrivate[]
  result: HandResultPrivate
}

export interface ActionRecordPrivate {
  seat: number
  street: Street
  action_type: ActionType
  amount: number | null
  is_forced_blind: boolean
  turn_index: number
}

export interface HandResultPrivate {
  showdown: boolean
  winners: WinnerInfo[]
  side_pots: SidePotSummary[]
  final_invested: { [seatStr: string]: number }
  net_pnl: { [seatStr: string]: number }
}

export interface WinnerInfo {
  seat: number
  winnings: number
  best_hand_desc: string
}

export interface SidePotSummary {
  amount: number
  eligible_seats: number[]
}

// === public_replay.jsonl ===
export interface PublicHandRecord {
  hand_id: number
  street_events: PublicEvent[]
}

export type PublicEvent =
  | PublicHandStarted
  | PublicHoleDealt
  | PublicAction
  | PublicFlop
  | PublicTurn
  | PublicRiver
  | PublicShowdown
  | PublicHandEnded

export interface PublicHandStarted {
  type: 'hand_started'
  hand_id: number
  button_seat: number
  blinds: { sb: number; bb: number }
}

export interface PublicHoleDealt {
  type: 'hole_dealt'
  hand_id: number
}

export interface PublicAction {
  type: 'action'
  hand_id: number
  seat: number
  street: Street
  action: { type: ActionType; amount?: number }
}

export interface PublicFlop {
  type: 'flop'
  hand_id: number
  community: [CardStr, CardStr, CardStr]
}

export interface PublicTurn {
  type: 'turn'
  hand_id: number
  card: CardStr
}

export interface PublicRiver {
  type: 'river'
  hand_id: number
  card: CardStr
}

export interface PublicShowdown {
  type: 'showdown'
  hand_id: number
  revealed: { [seatStr: string]: [CardStr, CardStr] }
}

export interface PublicHandEnded {
  type: 'hand_ended'
  hand_id: number
  winnings: { [seatStr: string]: number }
}

// === agent_view_snapshots.jsonl ===
export interface AgentViewSnapshot {
  hand_id: number
  turn_id: string
  session_id: string
  seat: number
  street: Street
  timestamp: string
  view_at_turn_start: PlayerViewLite
  iterations: IterationRecord[]
  final_action: { type: ActionType; amount?: number }
  is_forced_blind: boolean
  total_utility_calls: number
  api_retry_count: number
  illegal_action_retry_count: number
  no_tool_retry_count: number
  tool_usage_error_count: number
  default_action_fallback: boolean
  api_error: ApiErrorInfo | null
  turn_timeout_exceeded: boolean
  total_tokens: TokenCounts | object
  wall_time_ms: number
  agent: AgentDescriptor
}

// Subset of PlayerView the UI actually reads. The full schema has more
// fields (opponent_seats_in_hand, opponent_stats, etc.) but Phase 1
// surfaces only what's needed by the table+timeline+reasoning views.
//
// seats_public: included so per-seat stacks/status reflect the CURRENT
// snapshot (not the hand's starting_stacks). codex IMPORTANT-7 fix —
// otherwise visible stacks don't shrink as raises/calls happen.
export interface PlayerViewLite {
  my_seat: number
  pot: number
  my_stack: number
  current_bet_to_match: number
  to_call: number
  pot_odds_required: number | null
  effective_stack: number
  street: Street
  legal_actions: { tools: { name: string; args: object }[] }
  seats_public: SeatPublicInfo[]
}

export interface SeatPublicInfo {
  seat: number
  label: string
  position_short: string
  position_full: string
  stack: number
  invested_this_hand: number
  invested_this_round: number
  status: SeatStatus
}

export interface IterationRecord {
  step: number
  request_messages_digest: string
  provider_response_kind: 'tool_use' | 'text_only' | 'error' | 'no_tool'
  tool_call: ToolCall | null
  tool_result: { [k: string]: unknown } | null
  text_content: string
  tokens: TokenCounts
  wall_time_ms: number
  reasoning_artifacts?: ReasoningArtifact[]
}

export interface ToolCall {
  name: string
  args: { [k: string]: unknown }
  tool_use_id: string
}

export interface ReasoningArtifact {
  kind: 'raw' | 'summary' | 'thinking_block' | 'encrypted' | 'redacted' | 'unavailable'
  content?: string
}

export interface AgentDescriptor {
  provider: string
  model: string
  version: string
  temperature: number | null
  seed: number | null
}

export interface ApiErrorInfo {
  type: string
  detail: string
}

// === manifest.json (multi-session selector) ===
export interface SessionManifest {
  sessions: SessionManifestEntry[]
}

export interface SessionManifestEntry {
  id: string
  label: string
  hands: number
}

// === Top-level container after parsing all 4 files ===
export interface ParsedSession {
  meta: SessionMeta
  hands: { [handId: number]: ParsedHand }
}

export interface ParsedHand {
  canonical: CanonicalPrivateHand
  publicEvents: PublicEvent[]
  agentSnapshots: AgentViewSnapshot[]
}
