import type { AgentViewSnapshot, ActionRecordPrivate } from '../types'

interface Props {
  snapshot: AgentViewSnapshot
  canonicalAction?: ActionRecordPrivate
}

export function DevPanel({ snapshot, canonicalAction }: Props) {
  return (
    <div
      data-dev-panel
      className="bg-slate-900 text-slate-200 text-xs p-3 border-t-2 border-fuchsia-700 overflow-auto"
    >
      <div className="font-mono text-fuchsia-400 mb-2">
        🔧 dev — raw turn data
      </div>
      <details className="mb-2" open>
        <summary className="cursor-pointer text-fuchsia-300 select-none">
          agent_view_snapshot (seat {snapshot.seat} · {snapshot.street})
        </summary>
        <pre className="mt-2 overflow-auto max-h-72 bg-slate-950 p-2 rounded font-mono">
{JSON.stringify(snapshot, null, 2)}
        </pre>
      </details>
      {canonicalAction && (
        <details>
          <summary className="cursor-pointer text-fuchsia-300 select-none">
            canonical action (street {canonicalAction.street})
          </summary>
          <pre className="mt-2 overflow-auto max-h-40 bg-slate-950 p-2 rounded font-mono">
{JSON.stringify(canonicalAction, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}
