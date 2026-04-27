import type { IterationRecord, ActionType, AgentViewSnapshot } from '../types'

interface Props {
  actor: number
  positionLabel: string
  iterations: IterationRecord[]
  commitAction: { type: ActionType; amount?: number }
  isRuleBased?: boolean
  snapshot?: AgentViewSnapshot
  showDebugBadges?: boolean
}

export function ReasoningPanel({
  actor, positionLabel, iterations, commitAction, isRuleBased,
  snapshot, showDebugBadges,
}: Props) {
  return (
    <div className="bg-slate-100 border-l border-slate-300 p-3 h-full overflow-auto text-sm">
      <div className="font-bold text-slate-700 mb-2">
        seat {actor} ({positionLabel}) is acting
      </div>
      {showDebugBadges && snapshot && <SnapshotBadges snapshot={snapshot} />}
      <div className="space-y-2">
        {iterations.length === 0 && (
          isRuleBased ? (
            <div className="text-slate-500 italic">
              Rule-based agent (no LLM reasoning)
            </div>
          ) : (
            <div className="text-slate-500 italic">(no iterations recorded)</div>
          )
        )}
        {iterations.map((it, i) => (
          <IterationItem key={i} iter={it} showDebugBadges={!!showDebugBadges} />
        ))}
      </div>
      <div className="mt-3 pt-3 border-t border-slate-300">
        <div className="text-xs text-slate-500 mb-1">commit</div>
        <div className="font-bold text-emerald-700">
          {commitAction.type}
          {commitAction.amount !== undefined && ` ${commitAction.amount}`}
        </div>
      </div>
    </div>
  )
}

function SnapshotBadges({ snapshot }: { snapshot: AgentViewSnapshot }) {
  const badges: { label: string; cls: string }[] = []
  if (snapshot.api_error) {
    badges.push({ label: `api_error: ${snapshot.api_error.type}`, cls: 'bg-red-600 text-white' })
  }
  if (snapshot.api_retry_count > 0) {
    badges.push({ label: `api_retry × ${snapshot.api_retry_count}`, cls: 'bg-amber-600 text-white' })
  }
  if (snapshot.illegal_action_retry_count > 0) {
    badges.push({ label: `illegal × ${snapshot.illegal_action_retry_count}`, cls: 'bg-orange-600 text-white' })
  }
  if (snapshot.no_tool_retry_count > 0) {
    badges.push({ label: `no_tool × ${snapshot.no_tool_retry_count}`, cls: 'bg-orange-500 text-white' })
  }
  if (snapshot.tool_usage_error_count > 0) {
    badges.push({ label: `tool_err × ${snapshot.tool_usage_error_count}`, cls: 'bg-orange-700 text-white' })
  }
  if (snapshot.default_action_fallback) {
    badges.push({ label: 'fallback', cls: 'bg-red-700 text-white' })
  }
  if (snapshot.turn_timeout_exceeded) {
    badges.push({ label: 'TIMEOUT', cls: 'bg-red-800 text-white' })
  }
  if (badges.length === 0) return null
  return (
    <div data-snapshot-badges className="flex flex-wrap gap-1 mb-2">
      {badges.map((b, i) => (
        <span key={i} className={`px-1.5 py-0.5 rounded text-xs font-mono ${b.cls}`}>
          {b.label}
        </span>
      ))}
    </div>
  )
}

function IterationItem({
  iter, showDebugBadges,
}: { iter: IterationRecord; showDebugBadges: boolean }) {
  const kindBadge = (() => {
    if (!showDebugBadges) return null
    if (iter.provider_response_kind === 'error') {
      return <span className="px-1 rounded bg-red-200 text-red-800 text-xs font-mono">error</span>
    }
    if (iter.provider_response_kind === 'no_tool') {
      return <span className="px-1 rounded bg-orange-200 text-orange-800 text-xs font-mono">no_tool</span>
    }
    return null
  })()
  return (
    <div className="border-l-2 border-slate-400 pl-2">
      {(kindBadge || (showDebugBadges && iter.reasoning_artifacts && iter.reasoning_artifacts.length > 0)) && (
        <div data-iter-badges className="flex flex-wrap gap-1 mb-1">
          {kindBadge}
          {showDebugBadges && iter.reasoning_artifacts?.map((a, i) => (
            <span key={i} className="px-1 rounded bg-slate-300 text-slate-700 text-xs font-mono">
              {a.kind}
            </span>
          ))}
        </div>
      )}
      {iter.text_content && (
        <div className="text-slate-800 whitespace-pre-wrap">{iter.text_content}</div>
      )}
      {iter.tool_call && (
        <div className="mt-1 text-xs">
          <span className="font-mono text-blue-700">
            {iter.tool_call.name}({JSON.stringify(iter.tool_call.args).slice(1, -1)})
          </span>
          {iter.tool_result && (
            <span className="ml-2 font-mono text-slate-600">
              → {JSON.stringify(iter.tool_result)}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
