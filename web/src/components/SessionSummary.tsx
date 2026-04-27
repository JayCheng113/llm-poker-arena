import type { SessionMeta, RetrySummary, TokenCounts } from '../types'

interface Props {
  meta: SessionMeta
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
  // "rule_based:tag_v1" → "rule_based:tag_v1"  (keep namespace for clarity)
  if (s.startsWith('rule_based')) return 'rule_based'
  return s.split(':').slice(1).join(':') || s
}

export function SessionSummary({ meta, onClose }: Props) {
  const seats = Object.keys(meta.seat_assignment)
    .map(Number).sort((a, b) => a - b)
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
        </div>
      </div>
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
