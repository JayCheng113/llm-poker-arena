import type {
  SessionMeta, RetrySummary, TokenCounts, HudCounters, ParsedSession,
} from '../types'

interface Props {
  meta: SessionMeta
  session?: ParsedSession
  onClose: () => void
}

function tokenSum(t: TokenCounts): number {
  return t.input_tokens + t.output_tokens + t.cache_read_input_tokens + t.cache_creation_input_tokens
}

function retryStatus(r: RetrySummary): { label: string; bad: boolean } {
  const bad =
    r.api_retry_count + r.illegal_action_retry_count + r.no_tool_retry_count +
    r.tool_usage_error_count + r.default_action_fallback_count +
    r.turn_timeout_exceeded_count
  if (bad === 0) return { label: 'OK', bad: false }
  const parts: string[] = []
  if (r.api_retry_count > 0) parts.push(`api×${r.api_retry_count}`)
  if (r.illegal_action_retry_count > 0) parts.push(`illegal×${r.illegal_action_retry_count}`)
  if (r.no_tool_retry_count > 0) parts.push(`no_tool×${r.no_tool_retry_count}`)
  if (r.tool_usage_error_count > 0) parts.push(`tool_err×${r.tool_usage_error_count}`)
  if (r.default_action_fallback_count > 0) parts.push(`fallback×${r.default_action_fallback_count}`)
  if (r.turn_timeout_exceeded_count > 0) parts.push(`timeout×${r.turn_timeout_exceeded_count}`)
  return { label: parts.join(' · '), bad: true }
}

function shortAgent(s: string): string {
  // "anthropic:claude-haiku-4-5" → "claude-haiku-4-5"
  // "rule_based:tag_v1" → "rule_based"  (keep "rule_based" namespace for
  // clarity — distinguishes a rule-based seat from an LLM seat at a glance).
  if (s.startsWith('rule_based')) return 'rule_based'
  return s.split(':').slice(1).join(':') || s
}

export function SessionSummary({ meta, session, onClose }: Props) {
  const seats = Object.keys(meta.seat_assignment)
    .map(Number).sort((a, b) => a - b)
  const handIds = session
    ? Object.keys(session.hands).map(Number).sort((a, b) => a - b)
    : []
  return (
    <div
      data-session-summary
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <h2 className="font-bold text-lg text-slate-800">session summary</h2>
          <button
            onClick={onClose}
            aria-label="close summary"
            className="text-slate-500 hover:text-slate-800 text-2xl leading-none px-2"
          >
            ×
          </button>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <Stat label="hands played" value={`${meta.total_hands_played} / ${meta.planned_hands}`} />
            <Stat label="stop reason" value={meta.stop_reason} />
            <Stat label="wall time" value={meta.session_wall_time_sec ? `${meta.session_wall_time_sec}s` : '—'} />
            <Stat label="session id" value={meta.session_id.slice(0, 8) + '…'} />
          </div>

          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-slate-700">
              <tr>
                <th className="text-left p-2">seat</th>
                <th className="text-left p-2">agent</th>
                <th className="text-right p-2">PnL</th>
                <th className="text-right p-2">tokens</th>
                <th className="text-right p-2">utility calls</th>
                <th className="text-left p-2">retry / errors</th>
              </tr>
            </thead>
            <tbody>
              {seats.map((seat) => {
                const seatStr = String(seat)
                const pnl = meta.chip_pnl[seatStr] ?? 0
                const tokens = meta.total_tokens[seatStr]
                  ? tokenSum(meta.total_tokens[seatStr])
                  : 0
                const utility = meta.tool_usage_summary[seatStr]?.total_utility_calls ?? 0
                const retry = meta.retry_summary_per_seat[seatStr]
                  ? retryStatus(meta.retry_summary_per_seat[seatStr])
                  : { label: '—', bad: false }
                return (
                  <tr key={seat} className="border-b border-slate-200">
                    <td className="p-2 font-mono">seat {seat}</td>
                    <td className="p-2 font-mono text-slate-600">
                      {shortAgent(meta.seat_assignment[seatStr] ?? '')}
                    </td>
                    <td className={`p-2 text-right font-mono ${
                      pnl > 0 ? 'text-emerald-700' : pnl < 0 ? 'text-red-700' : 'text-slate-500'
                    }`}>
                      {pnl >= 0 ? '+' : ''}{pnl}
                    </td>
                    <td className="p-2 text-right font-mono text-slate-600">{tokens.toLocaleString()}</td>
                    <td className="p-2 text-right font-mono text-slate-600">{utility}</td>
                    <td className={`p-2 font-mono text-xs ${retry.bad ? 'text-red-700' : 'text-emerald-700'}`}>
                      {retry.label}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {meta.hud_per_seat && Object.keys(meta.hud_per_seat).length > 0 && (
            <HudTable
              hud={meta.hud_per_seat}
              hands={meta.hud_hands_counted ?? 0}
              seats={seats}
              seatAssignment={meta.seat_assignment}
            />
          )}

          {session && handIds.length > 0 && (
            <PerHandTable session={session} handIds={handIds} />
          )}
        </div>
      </div>
    </div>
  )
}

function PerHandTable({
  session, handIds,
}: { session: ParsedSession; handIds: number[] }) {
  return (
    <div className="mt-4">
      <h3 className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
        per-hand outcomes ({handIds.length} hands)
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-slate-700">
            <tr>
              <th className="text-left p-2">hand</th>
              <th className="text-left p-2">btn</th>
              <th className="text-left p-2">winner(s)</th>
              <th className="text-right p-2">pot</th>
              <th className="text-left p-2">community</th>
            </tr>
          </thead>
          <tbody>
            {handIds.map((hid) => {
              const c = session.hands[hid].canonical
              const winners = c.result.winners
              const pot = winners.reduce((s, w) => s + w.winnings, 0)
              return (
                <tr key={hid} className="border-b border-slate-200">
                  <td className="p-2 font-mono tabular-nums text-slate-700">{hid}</td>
                  <td className="p-2 font-mono tabular-nums text-slate-500">s{c.button_seat}</td>
                  <td className="p-2 font-mono text-slate-700">
                    {winners.length === 0
                      ? <span className="text-slate-400">—</span>
                      : winners.map((w, i) => (
                          <span key={i} className="mr-2">
                            s{w.seat} <span className="text-emerald-600">+{w.winnings}</span>
                            {w.best_hand_desc ? (
                              <span className="text-slate-400 text-xs ml-1">
                                ({w.best_hand_desc})
                              </span>
                            ) : null}
                          </span>
                        ))}
                  </td>
                  <td className="p-2 text-right font-mono tabular-nums text-slate-700">{pot}</td>
                  <td className="p-2 font-mono text-xs text-slate-500">
                    {c.community.length > 0 ? c.community.join(' ') : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface HudRowsProps {
  hud: { [seatStr: string]: HudCounters }
  hands: number
  seats: number[]
  seatAssignment: { [seatStr: string]: string }
}

function pct(num: number, denom: number): string {
  if (denom <= 0) return '—'
  return `${Math.round((num / denom) * 100)}%`
}

function af(c: HudCounters): string {
  if (c.af_passive <= 0) {
    return c.af_aggressive > 0 ? '∞' : '—'
  }
  return (c.af_aggressive / c.af_passive).toFixed(1)
}

function HudTable({ hud, hands, seats, seatAssignment }: HudRowsProps) {
  return (
    <div className="mt-4">
      <h3 className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
        per-seat HUD ({hands} hands counted)
      </h3>
      <table className="w-full text-sm">
        <thead className="bg-slate-100 text-slate-700">
          <tr>
            <th className="text-left p-2">seat</th>
            <th className="text-left p-2">agent</th>
            <th className="text-right p-2" title="voluntary $ in pot %">VPIP</th>
            <th className="text-right p-2" title="preflop raise %">PFR</th>
            <th className="text-right p-2" title="3-bet %">3-bet</th>
            <th className="text-right p-2" title="aggression factor (bets+raises)/calls">AF</th>
            <th className="text-right p-2" title="went-to-showdown when VPIP'd %">WTSD</th>
          </tr>
        </thead>
        <tbody>
          {seats.map((seat) => {
            const c = hud[String(seat)]
            const agent = seatAssignment[String(seat)] ?? ''
            return (
              <tr key={seat} className="border-b border-slate-200">
                <td className="p-2 font-mono">seat {seat}</td>
                <td className="p-2 font-mono text-slate-600">
                  {shortAgent(agent)}
                </td>
                {!c ? (
                  <td colSpan={5} className="p-2 text-slate-400 text-center">—</td>
                ) : (
                  <>
                    <td className="p-2 text-right font-mono tabular-nums text-slate-700">{pct(c.vpip_actions, hands)}</td>
                    <td className="p-2 text-right font-mono tabular-nums text-slate-700">{pct(c.pfr_actions, hands)}</td>
                    <td className="p-2 text-right font-mono tabular-nums text-slate-700">{pct(c.three_bet_actions, c.three_bet_chances)}</td>
                    <td className="p-2 text-right font-mono tabular-nums text-slate-700">{af(c)}</td>
                    <td className="p-2 text-right font-mono tabular-nums text-slate-700">{pct(c.wtsd_actions, c.wtsd_chances)}</td>
                  </>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-50 rounded p-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-mono text-slate-800">{value}</div>
    </div>
  )
}
