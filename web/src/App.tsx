import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { parseSessionFiles, parseSessionFromFiles } from './parsers/parseSessionFiles'
import { getCurrentTurn } from './selectors/getCurrentTurn'
import { cardRevelation } from './selectors/cardRevelation'
import { HandSelector } from './components/HandSelector'
import { PokerTable } from './components/PokerTable'
import { ReasoningPanel } from './components/ReasoningPanel'
import { ActionTimeline } from './components/ActionTimeline'
import type { SeatSeries } from './components/PnlChart'
// Lazy-load heavy / conditional components to keep the initial JS chunk
// lean. Tremor + Recharts (PnlChart) is the biggest, ~200KB gzipped.
// SessionSummary + DevPanel only render on user action / dev mode.
const PnlChart = lazy(() =>
  import('./components/PnlChart').then((m) => ({ default: m.PnlChart })))
const DevPanel = lazy(() =>
  import('./components/DevPanel').then((m) => ({ default: m.DevPanel })))
const SessionSummary = lazy(() =>
  import('./components/SessionSummary').then((m) => ({ default: m.SessionSummary })))
import { useKeyboardNav } from './hooks/useKeyboardNav'
import { useAutoPlay } from './hooks/useAutoPlay'

const AUTO_PLAY_INTERVAL_MS = 1500
import type {
  ParsedSession, SessionManifest, SeatStatus, CardStr, ActionType,
} from './types'

const DATA_ROOT = `${import.meta.env.BASE_URL}data`
const POSITION_LABELS = ['BTN', 'SB', 'BB', 'UTG', 'HJ', 'CO']

function _positionLabelForSeat(seat: number, buttonSeat: number, n: number): string {
  const offset = ((seat - buttonSeat) + n) % n
  return POSITION_LABELS[offset]
}

function readPointerFromUrl() {
  const params = new URLSearchParams(window.location.search)
  return {
    sessionId: params.get('session'),
    handId: Number(params.get('hand') ?? '0'),
    turnIdx: Number(params.get('turn') ?? '0'),
    // Default = god-view (cards visible). ?live=1 opts into the
    // spectator's-camera mode where cards stay face-down until showdown.
    liveMode: params.get('live') === '1',
    // ?dev=1 enables debug-only surfaces (raw JSON viewer, retry/error
    // badges) — independent of card visibility.
    devMode: params.get('dev') === '1',
  }
}

function useUrlPointer(): {
  sessionId: string | null
  handId: number
  turnIdx: number
  liveMode: boolean
  devMode: boolean
  setSessionId: (s: string) => void
  setHandId: (h: number) => void
  setTurnIdx: (t: number) => void
  toggleLive: () => void
  toggleDev: () => void
} {
  const [pointer, setPointer] = useState(readPointerFromUrl)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (pointer.sessionId) params.set('session', pointer.sessionId)
    else params.delete('session')
    params.set('hand', String(pointer.handId))
    params.set('turn', String(pointer.turnIdx))
    if (pointer.liveMode) params.set('live', '1')
    else params.delete('live')
    if (pointer.devMode) params.set('dev', '1')
    else params.delete('dev')
    const newUrl = `${window.location.pathname}?${params.toString()}`
    window.history.replaceState(null, '', newUrl)
  }, [pointer])

  // Listen for browser back/forward (codex IMPORTANT-1) — re-parse URL.
  useEffect(() => {
    const onPop = () => setPointer(readPointerFromUrl())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // Stable setters so consumers can list them in effect deps without churn.
  const setSessionId = useCallback(
    (s: string) => setPointer((p) => ({ ...p, sessionId: s, handId: 0, turnIdx: 0 })),
    [],
  )
  const setHandId = useCallback(
    (h: number) => setPointer((p) => ({ ...p, handId: h, turnIdx: 0 })),
    [],
  )
  const setTurnIdx = useCallback(
    (t: number) => setPointer((p) => ({ ...p, turnIdx: t })),
    [],
  )
  const toggleLive = useCallback(
    () => setPointer((p) => ({ ...p, liveMode: !p.liveMode })),
    [],
  )
  const toggleDev = useCallback(
    () => setPointer((p) => ({ ...p, devMode: !p.devMode })),
    [],
  )

  return {
    sessionId: pointer.sessionId,
    handId: pointer.handId,
    turnIdx: pointer.turnIdx,
    liveMode: pointer.liveMode,
    devMode: pointer.devMode,
    setSessionId, setHandId, setTurnIdx, toggleLive, toggleDev,
  }
}

function useWindowWidth(): number {
  const [w, setW] = useState(() =>
    typeof window === 'undefined' ? 1024 : window.innerWidth
  )
  useEffect(() => {
    const onResize = () => setW(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return w
}

function _formatAction(action: { type: ActionType; amount?: number }): string {
  if (action.amount !== undefined) return `${action.type} ${action.amount}`
  return action.type
}

function App() {
  const [manifest, setManifest] = useState<SessionManifest | null>(null)
  const [sessionData, setSessionData] = useState<
    { id: string; session: ParsedSession } | null
  >(null)
  const [customSession, setCustomSession] = useState<ParsedSession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)
  const [showSummary, setShowSummary] = useState(false)
  const ptr = useUrlPointer()

  const loadCustomSession = useCallback(async (files: FileList) => {
    try {
      const parsed = await parseSessionFromFiles(files)
      setCustomSession(parsed)
      setError(null)
    } catch (e) {
      setError(`Failed to load custom session: ${(e as Error).message}`)
    }
  }, [])

  const clearCustomSession = useCallback(() => setCustomSession(null), [])

  // Load manifest once
  useEffect(() => {
    fetch(`${DATA_ROOT}/manifest.json`)
      .then((r) => r.json() as Promise<SessionManifest>)
      .then(setManifest)
      .catch((e: Error) => setError(`Failed to load manifest: ${e.message}`))
  }, [])

  // Resolve effective session id: ?session=, else first manifest entry.
  // Stays null until manifest loads → session-load effect waits (codex IMPORTANT-2).
  const effectiveSessionId =
    ptr.sessionId
    ?? manifest?.sessions[0]?.id
    ?? null

  // Derived: custom session takes priority; else session matching the active id.
  const session = customSession
    ?? (sessionData && sessionData.id === effectiveSessionId
      ? sessionData.session
      : null)

  // Load session data when id changes (gated on manifest being ready, skipped
  // when a custom session is active to avoid wasted fetches)
  useEffect(() => {
    if (customSession) return
    if (!effectiveSessionId) return
    let cancelled = false
    const base = `${DATA_ROOT}/${effectiveSessionId}`
    Promise.all([
      fetch(`${base}/canonical_private.jsonl`).then((r) => r.text()),
      fetch(`${base}/public_replay.jsonl`).then((r) => r.text()),
      fetch(`${base}/agent_view_snapshots.jsonl`).then((r) => r.text()),
      fetch(`${base}/meta.json`).then((r) => r.text()),
    ])
      .then(([canonText, publicText, snapText, metaText]) => {
        if (cancelled) return
        setSessionData({
          id: effectiveSessionId,
          session: parseSessionFiles({
            canonical: canonText, public: publicText,
            snapshots: snapText, meta: metaText,
          }),
        })
      })
      .catch((e: Error) => {
        if (!cancelled) setError(`Failed to load session: ${e.message}`)
      })
    return () => { cancelled = true }
  }, [effectiveSessionId, customSession])

  // Compute nav state (safe when session not loaded yet) — must be before
  // early returns so hook order is stable.
  const handIds = useMemo(
    () => session ? Object.keys(session.hands).map(Number).sort((a, b) => a - b) : [],
    [session]
  )

  // Snap handId to first available when current isn't in the loaded session's
  // hand list (codex IMPORTANT-3 — sessions with non-contiguous hand_ids).
  const { handId: ptrHandId, setHandId: ptrSetHandId } = ptr
  useEffect(() => {
    if (handIds.length > 0 && !handIds.includes(ptrHandId)) {
      ptrSetHandId(handIds[0])
    }
  }, [handIds, ptrHandId, ptrSetHandId])

  // Responsive table scale: fit width below 850px viewport (codex NIT-4: live resize)
  const winW = useWindowWidth()
  const tableScale = winW >= 850 ? 1 : Math.max(0.4, (winW - 32) / 800)
  const pnlSeries = useMemo<SeatSeries[]>(() => {
    if (!session) return []
    const seats = [0, 1, 2, 3, 4, 5]
    // Render running stack (starting + cumulative PnL), not raw PnL deltas.
    // All seats start at the same value so the chart is read as
    // "trajectory of each player's bankroll" — much more intuitive than
    // a centered-at-zero PnL plot where small swings vanish next to big ones.
    // Stack is allowed to go negative (we don't model rebuys).
    const firstHand = handIds.length > 0 ? session.hands[handIds[0]] : null
    const startingStacks: Record<string, number> = firstHand
      ? firstHand.canonical.starting_stacks
      : {}
    return seats.map((seat) => {
      const start = startingStacks[String(seat)] ?? 0
      const values: number[] = []
      let cum = 0
      for (const h of handIds) {
        const pnl = session.hands[h].canonical.result.net_pnl[String(seat)] ?? 0
        cum += pnl
        values.push(start + cum)
      }
      return { seat, values }
    })
  }, [session, handIds])
  const hand = session?.hands[ptr.handId]
  const turnCount = hand?.agentSnapshots.length ?? 0
  const safeTurnIdx = Math.min(ptr.turnIdx, Math.max(0, turnCount - 1))
  const togglePlay = useMemo(() => () => setIsPlaying((p) => !p), [])
  const navTargets = useMemo(() => ({
    onPrevTurn: () => ptr.setTurnIdx(Math.max(0, safeTurnIdx - 1)),
    onNextTurn: () => ptr.setTurnIdx(Math.min(turnCount - 1, safeTurnIdx + 1)),
    onPrevHand: () => {
      const idx = handIds.indexOf(ptr.handId)
      if (idx > 0) ptr.setHandId(handIds[idx - 1])
    },
    onNextHand: () => {
      const idx = handIds.indexOf(ptr.handId)
      if (idx >= 0 && idx < handIds.length - 1) ptr.setHandId(handIds[idx + 1])
    },
    onTogglePlay: togglePlay,
  }), [ptr, safeTurnIdx, turnCount, handIds, togglePlay])
  useKeyboardNav(navTargets, !!hand)

  // Auto-advance: turn → next turn → next hand → stop at end of session
  const autoTick = useMemo(() => () => {
    if (safeTurnIdx < turnCount - 1) {
      ptr.setTurnIdx(safeTurnIdx + 1)
      return
    }
    const idx = handIds.indexOf(ptr.handId)
    if (idx >= 0 && idx < handIds.length - 1) {
      ptr.setHandId(handIds[idx + 1])
      return
    }
    setIsPlaying(false)
  }, [ptr, safeTurnIdx, turnCount, handIds])
  useAutoPlay({
    isPlaying: isPlaying && !!hand,
    intervalMs: Math.round(AUTO_PLAY_INTERVAL_MS / playbackSpeed),
    onTick: autoTick,
  })

  if (error) {
    return <div className="p-8 text-red-700">{error}</div>
  }
  if (!session) {
    return <div className="p-8">Loading session...</div>
  }
  if (!hand) {
    return <div className="p-8">Hand {ptr.handId} not in session</div>
  }
  const turn = getCurrentTurn(session, ptr.handId, safeTurnIdx)
  const handEnded = safeTurnIdx >= turnCount - 1
  const revealed = cardRevelation(
    session, ptr.handId,
    ptr.liveMode ? 'live' : 'god-view',
    { handEnded },
  )

  const cfg = hand.canonical
  const buttonSeat = cfg.button_seat
  const folded = new Set<number>()
  const actionsByTurn = hand.agentSnapshots.slice(0, safeTurnIdx + 1)
  for (const snap of actionsByTurn) {
    if (snap.final_action.type === 'fold') {
      folded.add(snap.seat)
    }
  }

  // Stacks come from current snapshot's view_at_turn_start.seats_public
  // (codex IMPORTANT-7 fix; see types.ts SeatPublicInfo)
  const currentSnap = hand.agentSnapshots[safeTurnIdx]
  const seatsPublic = currentSnap?.view_at_turn_start.seats_public ?? []
  const seatsPublicByIdx: { [k: number]: typeof seatsPublic[0] } = {}
  for (const sp of seatsPublic) {
    seatsPublicByIdx[sp.seat] = sp
  }
  const seats = [0, 1, 2, 3, 4, 5].map((seatIdx) => {
    const positionLabel = _positionLabelForSeat(seatIdx, buttonSeat, 6)
    const sp = seatsPublicByIdx[seatIdx]
    const status: SeatStatus = sp?.status ?? (folded.has(seatIdx) ? 'folded' : 'in_hand')
    const holeFromRevealed = revealed[String(seatIdx)]
    const holeCards: 'face-down' | [CardStr, CardStr] =
      holeFromRevealed && holeFromRevealed !== 'face-down' ? holeFromRevealed : 'face-down'
    const myActions = actionsByTurn.filter((s) => s.seat === seatIdx)
    const lastSnap = myActions.length > 0 ? myActions[myActions.length - 1] : undefined
    const lastAction = lastSnap ? _formatAction(lastSnap.final_action) : undefined
    const lastActionAmount = lastSnap?.final_action.amount
    return {
      seatIdx,
      positionLabel,
      stack: sp?.stack ?? cfg.starting_stacks[String(seatIdx)] ?? 0,
      status,
      holeCards,
      lastAction,
      lastActionAmount,
      agentId: session.meta.seat_assignment[String(seatIdx)],
    }
  })

  const community: CardStr[] =
    turn.street === 'preflop'
      ? []
      : turn.street === 'flop'
      ? cfg.community.slice(0, 3)
      : turn.street === 'turn'
      ? cfg.community.slice(0, 4)
      : cfg.community.slice(0, 5)

  const timelineTurns = hand.agentSnapshots.map((s) => ({
    actor: s.seat,
    actionLabel: _formatAction(s.final_action),
    actionType: s.final_action.type,
    street: s.street,
    agentId: session.meta.seat_assignment[String(s.seat)],
  }))

  const actorPosition = _positionLabelForSeat(turn.actor, buttonSeat, 6)

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      <HandSelector
        handIds={handIds}
        currentHandId={ptr.handId}
        onSelect={ptr.setHandId}
        isPlaying={isPlaying}
        onTogglePlay={togglePlay}
        playbackSpeed={playbackSpeed}
        onChangeSpeed={setPlaybackSpeed}
        liveMode={ptr.liveMode}
        onToggleLive={ptr.toggleLive}
        devMode={ptr.devMode}
        onToggleDev={ptr.toggleDev}
        onOpenSummary={() => setShowSummary(true)}
        manifest={manifest}
        currentSessionId={effectiveSessionId ?? undefined}
        onSelectSession={(s) => { clearCustomSession(); ptr.setSessionId(s) }}
        customLoaded={!!customSession}
        onLoadCustom={loadCustomSession}
        onClearCustom={clearCustomSession}
      />
      {showSummary && (
        <Suspense fallback={<div className="fixed inset-0 z-50 bg-black/40" />}>
          <SessionSummary
            meta={session.meta}
            session={session}
            onClose={() => setShowSummary(false)}
          />
        </Suspense>
      )}
      <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
        <div className="flex-1 flex items-center justify-center p-2 md:p-4 overflow-auto">
          <PokerTable
            seats={seats}
            community={community}
            pot={turn.pot}
            activeSeatIdx={turn.actor}
            handResult={handEnded ? cfg.result : undefined}
            scale={tableScale}
          />
        </div>
        <div className="w-full md:w-96 max-h-72 md:max-h-none flex flex-col border-t-2 md:border-t-0 md:border-l-2 border-slate-200">
          <div className="flex-1 overflow-auto">
            <ReasoningPanel
              actor={turn.actor}
              positionLabel={actorPosition}
              iterations={turn.reasoning}
              commitAction={turn.commitAction}
              isRuleBased={(session.meta.seat_assignment[String(turn.actor)] ?? '').startsWith('rule_based')}
              agentId={session.meta.seat_assignment[String(turn.actor)]}
              snapshot={currentSnap}
              showDebugBadges={ptr.devMode}
            />
          </div>
          {ptr.devMode && currentSnap && (
            <Suspense fallback={null}>
              <DevPanel
                snapshot={currentSnap}
                canonicalAction={cfg.actions.find((a) => a.turn_index === safeTurnIdx)}
              />
            </Suspense>
          )}
        </div>
      </div>
      <Suspense
        fallback={
          <div className="bg-white border-y border-slate-200 px-4 py-2 h-[88px] flex items-center text-xs text-slate-400">
            loading PnL chart…
          </div>
        }
      >
        <PnlChart
          series={pnlSeries}
          currentHandIdx={handIds.indexOf(ptr.handId)}
        />
      </Suspense>
      <ActionTimeline
        turns={timelineTurns}
        currentTurnIdx={safeTurnIdx}
        onSeek={ptr.setTurnIdx}
      />
    </div>
  )
}

export default App
