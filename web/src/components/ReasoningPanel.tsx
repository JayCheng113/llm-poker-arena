import type { IterationRecord, ActionType } from '../types'

interface Props {
  actor: number
  positionLabel: string
  iterations: IterationRecord[]
  commitAction: { type: ActionType; amount?: number }
  isRuleBased?: boolean
}

export function ReasoningPanel({
  actor, positionLabel, iterations, commitAction, isRuleBased,
}: Props) {
  return (
    <div className="bg-slate-100 border-l border-slate-300 p-3 h-full overflow-auto text-sm">
      <div className="font-bold text-slate-700 mb-2">
        seat {actor} ({positionLabel}) is acting
      </div>
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
          <IterationItem key={i} iter={it} />
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

function IterationItem({ iter }: { iter: IterationRecord }) {
  return (
    <div className="border-l-2 border-slate-400 pl-2">
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
