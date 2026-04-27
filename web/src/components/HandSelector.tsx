import { useRef, useState } from 'react'
import { KeyboardHelp } from './KeyboardHelp'
import {
  ChevronLeft, ChevronRight, Play, Pause,
  Eye, EyeOff, BarChart3, Bug, Upload, X, Spade,
  Keyboard,
} from 'lucide-react'
import type { SessionManifest } from '../types'

interface Props {
  handIds: number[]
  currentHandId: number
  onSelect: (handId: number) => void
  isPlaying?: boolean
  onTogglePlay?: () => void
  playbackSpeed?: number
  onChangeSpeed?: (s: number) => void
  liveMode?: boolean
  onToggleLive?: () => void
  devMode?: boolean
  onToggleDev?: () => void
  onOpenSummary?: () => void
  manifest?: SessionManifest | null
  currentSessionId?: string
  onSelectSession?: (id: string) => void
  customLoaded?: boolean
  onLoadCustom?: (files: FileList) => void
  onClearCustom?: () => void
}

export function HandSelector({
  handIds, currentHandId, onSelect, isPlaying, onTogglePlay,
  playbackSpeed, onChangeSpeed,
  liveMode, onToggleLive,
  devMode, onToggleDev, onOpenSummary,
  manifest, currentSessionId, onSelectSession,
  customLoaded, onLoadCustom, onClearCustom,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [showKeyboardHelp, setShowKeyboardHelp] = useState(false)
  const idx = handIds.indexOf(currentHandId)
  const canPrev = idx > 0
  const canNext = idx >= 0 && idx < handIds.length - 1

  return (
    <div className="flex items-center gap-2 px-4 py-2.5 bg-white border-b border-slate-200 shadow-sm">
      {/* Brand */}
      <div className="flex items-center gap-2 mr-2">
        <Spade className="w-5 h-5 text-indigo-600" strokeWidth={2.5} />
        <span className="font-semibold text-slate-900 text-sm hidden sm:inline">
          LLM Poker Arena
        </span>
      </div>

      <div className="h-6 w-px bg-slate-200" />

      {/* Session selector — primary navigation, kept on the left */}
      {manifest && manifest.sessions.length > 1 && onSelectSession && (
        <select
          value={currentSessionId ?? manifest.sessions[0].id}
          onChange={(e) => onSelectSession(e.target.value)}
          aria-label="select session"
          className="bg-slate-50 border border-slate-300 rounded-md px-2.5 py-1 text-xs text-slate-700 hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 max-w-[18rem] truncate"
        >
          {manifest.sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      )}

      {/* Hand nav: prev / counter / next / dropdown */}
      <div className="flex items-center gap-0.5 ml-2">
        <IconButton
          onClick={() => canPrev && onSelect(handIds[idx - 1])}
          disabled={!canPrev}
          aria-label="previous hand"
        >
          <ChevronLeft className="w-4 h-4" />
        </IconButton>
        <select
          value={currentHandId}
          onChange={(e) => onSelect(Number(e.target.value))}
          aria-label="select hand"
          className="bg-transparent text-sm font-mono tabular-nums font-semibold text-slate-900 border-0 px-1.5 py-1 hover:bg-slate-100 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer appearance-none text-center"
          style={{ paddingRight: '0.5rem' }}
        >
          {handIds.map((h) => (
            <option key={h} value={h}>
              hand {h}
            </option>
          ))}
        </select>
        <span className="text-xs text-slate-400 tabular-nums px-1">
          {idx + 1}/{handIds.length}
        </span>
        <IconButton
          onClick={() => canNext && onSelect(handIds[idx + 1])}
          disabled={!canNext}
          aria-label="next hand"
        >
          <ChevronRight className="w-4 h-4" />
        </IconButton>
      </div>

      <div className="h-6 w-px bg-slate-200 mx-1" />

      {/* Play controls */}
      {onTogglePlay && (
        <button
          onClick={onTogglePlay}
          aria-label={isPlaying ? 'pause' : 'play'}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${
            isPlaying
              ? 'bg-amber-100 text-amber-800 hover:bg-amber-200 border border-amber-200'
              : 'bg-indigo-600 text-white hover:bg-indigo-700 border border-indigo-600'
          }`}
        >
          {isPlaying
            ? <><Pause className="w-3.5 h-3.5" fill="currentColor" /> pause</>
            : <><Play className="w-3.5 h-3.5" fill="currentColor" /> play</>}
        </button>
      )}
      {onChangeSpeed && (
        <select
          value={String(playbackSpeed ?? 1)}
          onChange={(e) => onChangeSpeed(Number(e.target.value))}
          aria-label="playback speed"
          className="bg-slate-50 border border-slate-300 rounded-md px-2 py-1 text-xs text-slate-700 hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        >
          <option value="0.5">0.5×</option>
          <option value="1">1×</option>
          <option value="2">2×</option>
          <option value="4">4×</option>
        </select>
      )}

      {/* Right-side controls (push to the end) */}
      <div className="flex items-center gap-1.5 ml-auto">
        {/* Keyboard shortcut help — opens a modal with the full list */}
        <button
          type="button"
          onClick={() => setShowKeyboardHelp(true)}
          aria-label="show keyboard shortcuts"
          title="keyboard shortcuts"
          className="hidden md:flex items-center p-1.5 rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        >
          <Keyboard className="w-4 h-4" />
        </button>
        {showKeyboardHelp && (
          <KeyboardHelp onClose={() => setShowKeyboardHelp(false)} />
        )}

        {onToggleLive && (
          <ToggleButton
            active={!liveMode}
            onClick={onToggleLive}
            aria-label={liveMode ? 'reveal all cards' : 'hide cards (live spectator mode)'}
            title={
              liveMode
                ? 'live spectator mode: cards face-down until showdown — click to reveal all'
                : 'god-view: all cards visible — click for live spectator mode'
            }
            icon={liveMode ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          >
            {liveMode ? 'cards hidden' : 'cards shown'}
          </ToggleButton>
        )}

        {onOpenSummary && (
          <IconLabelButton
            onClick={onOpenSummary}
            aria-label="open session summary"
            icon={<BarChart3 className="w-3.5 h-3.5" />}
          >
            summary
          </IconLabelButton>
        )}

        {onToggleDev && (
          <ToggleButton
            active={!!devMode}
            onClick={onToggleDev}
            aria-label="toggle dev mode"
            title="dev mode: raw JSON viewer + retry/error badges in reasoning panel"
            icon={<Bug className="w-3.5 h-3.5" />}
            activeTone="fuchsia"
          >
            dev
          </ToggleButton>
        )}

        {devMode && onLoadCustom && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".jsonl,.json"
              aria-label="custom session files"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  onLoadCustom(e.target.files)
                  e.target.value = ''
                }
              }}
            />
            {customLoaded ? (
              <ToggleButton
                active
                onClick={onClearCustom ?? (() => {})}
                aria-label="clear custom session"
                icon={<X className="w-3.5 h-3.5" />}
                activeTone="fuchsia"
              >
                custom
              </ToggleButton>
            ) : (
              <IconLabelButton
                onClick={() => fileInputRef.current?.click()}
                aria-label="load custom session"
                title="select 4 files: canonical_private.jsonl, public_replay.jsonl, agent_view_snapshots.jsonl, meta.json"
                icon={<Upload className="w-3.5 h-3.5" />}
              >
                load
              </IconLabelButton>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// Reusable button primitives — keep styling consistent.

function IconButton({
  onClick, disabled, children, ...rest
}: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
  'aria-label': string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="p-1.5 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-30 disabled:hover:bg-transparent disabled:cursor-not-allowed"
      {...rest}
    >
      {children}
    </button>
  )
}

function IconLabelButton({
  onClick, icon, children, ...rest
}: {
  onClick: () => void
  icon: React.ReactNode
  children: React.ReactNode
  'aria-label': string
  title?: string
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200"
      {...rest}
    >
      {icon}
      {children}
    </button>
  )
}

function ToggleButton({
  active, onClick, icon, children, activeTone = 'indigo', ...rest
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  children: React.ReactNode
  activeTone?: 'indigo' | 'fuchsia'
  'aria-label': string
  title?: string
}) {
  const onClasses =
    activeTone === 'fuchsia'
      ? 'bg-fuchsia-600 text-white border-fuchsia-600 hover:bg-fuchsia-700'
      : 'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100'
  const offClasses =
    'bg-white text-slate-500 border-slate-200 hover:text-slate-700 hover:bg-slate-50'
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${
        active ? onClasses : offClasses
      }`}
      {...rest}
    >
      {icon}
      {children}
    </button>
  )
}
