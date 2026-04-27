import {
  X, Check, Equal, TrendingUp, Zap, HelpCircle,
} from 'lucide-react'
import { ProviderBadge } from './ProviderBadge'
import { shortAgentLabel } from './agentLabel'
import type { IterationRecord, ActionType, AgentViewSnapshot } from '../types'

interface Props {
  actor: number
  positionLabel: string
  iterations: IterationRecord[]
  commitAction: { type: ActionType; amount?: number }
  isRuleBased?: boolean
  agentId?: string
  snapshot?: AgentViewSnapshot
  showDebugBadges?: boolean
}

export function ReasoningPanel({
  actor, positionLabel, iterations, commitAction, isRuleBased,
  agentId, snapshot, showDebugBadges,
}: Props) {
  const label = agentId ? shortAgentLabel(agentId) : 'unknown'
  return (
    <div className="bg-white border-l border-slate-200 h-full overflow-auto">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white border-b border-slate-200 px-4 py-3">
        <div className="flex items-center gap-2">
          {agentId && <ProviderBadge agentId={agentId} size={20} />}
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-900 truncate">
              {label}
            </div>
            <div className="text-xs text-slate-500 mt-0.5">
              {positionLabel} · seat {actor} · is acting
            </div>
          </div>
        </div>
        {showDebugBadges && snapshot && (
          <div className="mt-2">
            <SnapshotBadges snapshot={snapshot} />
          </div>
        )}
      </div>

      {/* Reasoning iterations */}
      <div className="px-4 py-3 space-y-3">
        {iterations.length === 0 ? (
          <EmptyState isRuleBased={isRuleBased} />
        ) : (
          iterations.map((it, i) => (
            <IterationItem
              key={i}
              iter={it}
              stepNumber={i + 1}
              showDebugBadges={!!showDebugBadges}
            />
          ))
        )}
      </div>

      {/* Commit action */}
      <div className="border-t border-slate-200 px-4 py-3 bg-slate-50">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5">
          decision
        </div>
        <CommitAction action={commitAction} />
      </div>
    </div>
  )
}

function EmptyState({ isRuleBased }: { isRuleBased?: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-8 text-slate-400">
      <HelpCircle className="w-6 h-6 mb-2" strokeWidth={1.5} />
      <div className="text-sm">
        {isRuleBased
          ? 'Rule-based agent — no LLM reasoning recorded'
          : '(no iterations recorded)'}
      </div>
    </div>
  )
}

function CommitAction({ action }: { action: { type: ActionType; amount?: number } }) {
  const cfg = ACTION_STYLES[action.type] ?? ACTION_STYLES.fold
  const Icon = cfg.icon
  return (
    <div className={`flex items-center gap-2 ${cfg.text}`}>
      <Icon className="w-5 h-5" strokeWidth={2.5} />
      <span className="text-base font-semibold">{action.type}</span>
      {action.amount !== undefined && action.amount > 0 && (
        <span className="text-base font-mono tabular-nums font-semibold">
          {action.amount.toLocaleString()}
        </span>
      )}
    </div>
  )
}

// Action icon picks (poker semantics, not English literalism):
//   fold      → X            reject the hand
//   check     → Check        pass without putting chips in
//   call      → Equal (=)    match the bet (NOT Phone — "call" here is
//                            "match", not "make a telephone call")
//   bet/raise → TrendingUp   add chips, increase the price
//   all_in    → Zap          shove everything, intense action
const ACTION_STYLES = {
  fold:     { icon: X,           text: 'text-rose-600' },
  check:    { icon: Check,       text: 'text-slate-700' },
  call:     { icon: Equal,       text: 'text-indigo-600' },
  bet:      { icon: TrendingUp,  text: 'text-emerald-600' },
  raise_to: { icon: TrendingUp,  text: 'text-emerald-600' },
  all_in:   { icon: Zap,         text: 'text-amber-600' },
} as const

function SnapshotBadges({ snapshot }: { snapshot: AgentViewSnapshot }) {
  const badges: { label: string; cls: string }[] = []
  if (snapshot.api_error) {
    badges.push({ label: `api_error: ${snapshot.api_error.type}`, cls: 'bg-rose-100 text-rose-700 border-rose-200' })
  }
  if (snapshot.api_retry_count > 0) {
    badges.push({ label: `api_retry × ${snapshot.api_retry_count}`, cls: 'bg-amber-100 text-amber-700 border-amber-200' })
  }
  if (snapshot.illegal_action_retry_count > 0) {
    badges.push({ label: `illegal × ${snapshot.illegal_action_retry_count}`, cls: 'bg-amber-100 text-amber-700 border-amber-200' })
  }
  if (snapshot.no_tool_retry_count > 0) {
    badges.push({ label: `no_tool × ${snapshot.no_tool_retry_count}`, cls: 'bg-amber-100 text-amber-700 border-amber-200' })
  }
  if (snapshot.tool_usage_error_count > 0) {
    badges.push({ label: `tool_err × ${snapshot.tool_usage_error_count}`, cls: 'bg-amber-100 text-amber-700 border-amber-200' })
  }
  if (snapshot.default_action_fallback) {
    badges.push({ label: 'fallback', cls: 'bg-rose-100 text-rose-700 border-rose-200' })
  }
  if (snapshot.turn_timeout_exceeded) {
    badges.push({ label: 'TIMEOUT', cls: 'bg-rose-100 text-rose-700 border-rose-200' })
  }
  if (badges.length === 0) return null
  return (
    <div data-snapshot-badges className="flex flex-wrap gap-1">
      {badges.map((b, i) => (
        <span
          key={i}
          className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${b.cls}`}
        >
          {b.label}
        </span>
      ))}
    </div>
  )
}

function IterationItem({
  iter, stepNumber, showDebugBadges,
}: { iter: IterationRecord; stepNumber: number; showDebugBadges: boolean }) {
  const kindBadge = (() => {
    if (!showDebugBadges) return null
    if (iter.provider_response_kind === 'error') {
      return <span className="px-1.5 py-0.5 rounded border border-rose-200 bg-rose-50 text-rose-700 text-[10px] font-mono">error</span>
    }
    if (iter.provider_response_kind === 'no_tool') {
      return <span className="px-1.5 py-0.5 rounded border border-amber-200 bg-amber-50 text-amber-700 text-[10px] font-mono">no_tool</span>
    }
    return null
  })()

  const showHeaderRow =
    showDebugBadges && (kindBadge || (iter.reasoning_artifacts && iter.reasoning_artifacts.length > 0))

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
          step {stepNumber}
        </span>
        {showHeaderRow && (
          <div className="flex flex-wrap gap-1">
            {kindBadge}
            {iter.reasoning_artifacts?.map((a, i) => (
              <span key={i} className="px-1.5 py-0.5 rounded border border-slate-200 bg-slate-50 text-slate-600 text-[10px] font-mono">
                {a.kind}
              </span>
            ))}
          </div>
        )}
      </div>

      {iter.text_content && (
        <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
          {iter.text_content}
        </div>
      )}

      {iter.tool_call && (
        <div className="rounded-md border border-slate-200 bg-slate-50 overflow-hidden">
          <div className="px-2.5 py-1.5 border-b border-slate-200 bg-white">
            <span className="text-xs font-mono font-semibold text-indigo-700">
              {iter.tool_call.name}
            </span>
            <span className="text-xs font-mono text-slate-500 ml-1">
              ({formatArgs(iter.tool_call.args)})
            </span>
          </div>
          {iter.tool_result && (
            <div className="px-2.5 py-1.5 text-xs font-mono text-emerald-700">
              → {JSON.stringify(iter.tool_result)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function formatArgs(args: { [k: string]: unknown }): string {
  const parts = Object.entries(args).map(([k, v]) =>
    `${k}=${typeof v === 'string' ? `"${v}"` : JSON.stringify(v)}`
  )
  return parts.join(', ')
}
