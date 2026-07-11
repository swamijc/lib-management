import { useState, useEffect, useMemo, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Play, RefreshCw, Loader2, Clock, CheckCircle, XCircle, AlertCircle,
  ChevronDown, ChevronUp, Calendar, User, Library,
} from 'lucide-react'
import ExecutiveTriad from '../components/ExecutiveTriad'
import SectionCard from '../components/SectionCard'
import { RowsPerPageControl, PaginatedSectionFooter } from '../components/PaginatedSectionControls'
import { parseApiError, schedulerApi, settingsApi } from '../api/client'
import { useAuth } from '../context/AuthContext'
import type { PipelineRun, PipelineStep, RetryRunResponse } from '../api/types'

type SchedulerCategory = 'control' | 'runtime' | 'current' | 'history'

// ── Cron expression → human-readable description ──────────────────────────────
function parseCron(expr: string): string {
  if (!expr) return 'Not configured'
  const parts = expr.trim().split(/\s+/)
  if (parts.length < 5) return expr
  const [min, hour, dom, month, dow] = parts
  if (expr === '* * * * *')    return 'Every minute'
  if (expr === '0 * * * *')    return 'Every hour'
  if (min !== '*' && hour !== '*' && dom === '*' && month === '*' && dow === '*')
    return `Every day at ${hour.padStart(2,'0')}:${min.padStart(2,'0')}`
  if (min !== '*' && hour !== '*' && dom === '*' && month === '*' && dow !== '*') {
    const days: Record<string,string> = {'0':'Sun','1':'Mon','2':'Tue','3':'Wed','4':'Thu','5':'Fri','6':'Sat','7':'Sun','1-5':'Mon\u2013Fri','0-6':'Daily'}
    return `Every ${days[dow] ?? `day ${dow}`} at ${hour.padStart(2,'0')}:${min.padStart(2,'0')}`
  }
  if (min !== '*' && hour !== '*' && dom !== '*' && month === '*' && dow === '*')
    return `Monthly on day ${dom} at ${hour.padStart(2,'0')}:${min.padStart(2,'0')}`
  if (min.startsWith('*/'))  return `Every ${min.replace('*/','')  } minutes`
  if (hour.startsWith('*/')) return `Every ${hour.replace('*/','') } hours`
  return expr
}

// Build cron from visual fields
function buildCron(freq: string, timeH: string, timeM: string, weekday: string, monthday: string): string {
  const h = timeH.padStart(1,'0')
  const m = timeM.padStart(1,'0')
  switch (freq) {
    case 'daily':    return `${m} ${h} * * *`
    case 'weekdays': return `${m} ${h} * * 1-5`
    case 'weekly':   return `${m} ${h} * * ${weekday}`
    case 'monthly':  return `${m} ${h} ${monthday} * *`
    case 'hourly':   return `${m} * * * *`
    default:         return `${m} ${h} * * *`
  }
}

// ── Inline Schedule Editor ────────────────────────────────────────────────────
function ScheduleEditor({
  current, onSave, onCancel,
}: {
  current: { cron: string; enabled: boolean }
  onSave: (cron: string, enabled: boolean) => Promise<void>
  onCancel: () => void
}) {
  const [tab, setTab]         = useState<'visual' | 'expr'>('visual')
  const [cronExpr, setCronExpr] = useState(current.cron)
  const [enabled, setEnabled] = useState(current.enabled)
  const [saving, setSaving]   = useState(false)
  const [err, setErr]         = useState('')

  // Visual state — parse initial cron
  const initFreq = () => {
    const p = current.cron.trim().split(/\s+/)
    if (!p[4]) return 'daily'
    if (p[4] === '1-5') return 'weekdays'
    if (p[2] !== '*')   return 'monthly'
    if (p[4] !== '*' && p[3] === '*') return 'weekly'
    if (p[1] === '*')   return 'hourly'
    return 'daily'
  }
  const [freq,     setFreq]     = useState(initFreq)
  const [timeH,    setTimeH]    = useState(() => { const p=current.cron.split(/\s+/); return p[1] !== '*' ? p[1] : '2' })
  const [timeM,    setTimeM]    = useState(() => { const p=current.cron.split(/\s+/); return p[0] !== '*' ? p[0] : '0' })
  const [weekday,  setWeekday]  = useState(() => { const p=current.cron.split(/\s+/); return p[4] !== '*' && p[4] !== '1-5' && p[2]==='*' ? p[4] : '1' })
  const [monthday, setMonthday] = useState(() => { const p=current.cron.split(/\s+/); return p[2] !== '*' ? p[2] : '1' })

  // Sync visual → expr when visual fields change
  const syncVisualToExpr = (f=freq, h=timeH, m=timeM, wd=weekday, md=monthday) => {
    setCronExpr(buildCron(f, h, m, wd, md))
  }

  const previewLabel = parseCron(cronExpr)

  const handleSave = async () => {
    const p = cronExpr.trim().split(/\s+/)
    if (p.length !== 5) { setErr('Invalid cron — must have 5 fields (min hour dom month dow)'); return }
    setSaving(true); setErr('')
    try { await onSave(cronExpr.trim(), enabled) }
    catch (e: unknown) { setErr((e as Error).message ?? 'Save failed') }
    finally { setSaving(false) }
  }

  const FREQ_OPTIONS = [
    { value: 'daily',    label: 'Daily' },
    { value: 'weekdays', label: 'Weekdays (Mon\u2013Fri)' },
    { value: 'weekly',   label: 'Weekly' },
    { value: 'monthly',  label: 'Monthly' },
    { value: 'hourly',   label: 'Hourly' },
  ]
  const WEEKDAYS = [
    {v:'1',l:'Monday'},{v:'2',l:'Tuesday'},{v:'3',l:'Wednesday'},{v:'4',l:'Thursday'},
    {v:'5',l:'Friday'},{v:'6',l:'Saturday'},{v:'0',l:'Sunday'},
  ]

  return (
    <div className="card border-2 border-primary-300 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-800">Edit Schedule</p>
        <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} className="w-3.5 h-3.5" />
          Enabled
        </label>
      </div>

      {/* Tab toggle */}
      <div className="flex gap-1 border-b border-slate-200">
        {(['visual','expr'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              tab === t ? 'border-primary-600 text-primary-700' : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}>
            {t === 'visual' ? '🗓️ Visual Builder' : '⌨️ Cron Expression'}
          </button>
        ))}
      </div>

      {/* Visual builder */}
      {tab === 'visual' && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs text-slate-500 mb-1">Frequency</label>
              <select className="select text-sm w-full" value={freq}
                onChange={e => { setFreq(e.target.value); syncVisualToExpr(e.target.value) }}>
                {FREQ_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            {freq !== 'hourly' && (
              <div>
                <label className="block text-xs text-slate-500 mb-1">Time</label>
                <div className="flex items-center gap-1">
                  <select className="select text-sm flex-1" value={timeH}
                    onChange={e => { setTimeH(e.target.value); syncVisualToExpr(freq, e.target.value) }}>
                    {Array.from({length:24},(_,i)=>i).map(h => (
                      <option key={h} value={String(h)}>{String(h).padStart(2,'0')}</option>
                    ))}
                  </select>
                  <span className="text-slate-400 font-bold">:</span>
                  <select className="select text-sm flex-1" value={timeM}
                    onChange={e => { setTimeM(e.target.value); syncVisualToExpr(freq, timeH, e.target.value) }}>
                    {['0','5','10','15','20','25','30','35','40','45','50','55'].map(m => (
                      <option key={m} value={m}>{m.padStart(2,'0')}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
            {freq === 'weekly' && (
              <div>
                <label className="block text-xs text-slate-500 mb-1">Day of Week</label>
                <select className="select text-sm w-full" value={weekday}
                  onChange={e => { setWeekday(e.target.value); syncVisualToExpr(freq, timeH, timeM, e.target.value) }}>
                  {WEEKDAYS.map(d => <option key={d.v} value={d.v}>{d.l}</option>)}
                </select>
              </div>
            )}
            {freq === 'monthly' && (
              <div>
                <label className="block text-xs text-slate-500 mb-1">Day of Month</label>
                <select className="select text-sm w-full" value={monthday}
                  onChange={e => { setMonthday(e.target.value); syncVisualToExpr(freq, timeH, timeM, weekday, e.target.value) }}>
                  {Array.from({length:28},(_,i)=>i+1).map(d => (
                    <option key={d} value={String(d)}>{d}</option>
                  ))}
                </select>
              </div>
            )}
            {freq === 'hourly' && (
              <div>
                <label className="block text-xs text-slate-500 mb-1">At minute</label>
                <select className="select text-sm w-full" value={timeM}
                  onChange={e => { setTimeM(e.target.value); setCronExpr(`${e.target.value} * * * *`) }}>
                  {['0','5','10','15','20','25','30','35','40','45','50','55'].map(m => (
                    <option key={m} value={m}>:{m.padStart(2,'0')}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Direct cron input */}
      {tab === 'expr' && (
        <div>
          <label className="block text-xs text-slate-500 mb-1">
            Cron Expression <span className="text-slate-400">(minute hour dom month dow)</span>
          </label>
          <input
            className="input font-mono text-sm"
            value={cronExpr}
            onChange={e => setCronExpr(e.target.value)}
            placeholder="0 2 * * *"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Examples: <code className="bg-slate-100 px-1 rounded">0 8 * * 1-5</code> weekdays 8am · <code className="bg-slate-100 px-1 rounded">0 */6 * * *</code> every 6h · <code className="bg-slate-100 px-1 rounded">30 9 * * 1</code> Mondays 9:30am
          </p>
        </div>
      )}

      {/* Live preview */}
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 rounded-lg border border-slate-200">
        <span className="text-sm">🕐</span>
        <div>
          <span className="font-mono text-xs text-slate-500 mr-2">{cronExpr}</span>
          <span className="text-xs font-semibold text-primary-700">{previewLabel}</span>
        </div>
      </div>

      {err && <p className="text-xs text-red-600">\u274c {err}</p>}

      {/* Actions */}
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary text-sm py-1.5" onClick={onCancel} disabled={saving}>Cancel</button>
        <button className="btn-primary text-sm py-1.5" onClick={handleSave} disabled={saving}>
          {saving ? <><Loader2 size={13} className="animate-spin" /> Saving\u2026</> : 'Save Schedule'}
        </button>
      </div>
    </div>
  )
}

// ── Step metadata ──────────────────────────────────────────────────────────────
const STEP_META: Record<string, { label: string; icon: string; description: string }> = {
  fetch_libraries:       { label: 'Fetch SDKs',   icon: '📦', description: 'Load all SDKs from database' },
  batch_scrape:          { label: 'Scrape Versions',   icon: '🔍', description: 'Fetch latest versions from registries' },
  fetch_version_history: { label: 'Version History',  icon: '🏷️',  description: 'Pull all versions from Maven Central / CocoaPods' },
  batch_compare:         { label: 'Compare Versions', icon: '⚖️',  description: 'Detect upgrades needed' },
  batch_recommend:       { label: 'Generate Recs',    icon: '🤖', description: 'AI/rule-based recommendations' },
  notify:                { label: 'Notifications',    icon: '🔔', description: 'Email / Teams alerts' },
}

// SLA targets (seconds) for pipeline observability.
const STEP_SLA_SECONDS: Record<string, number> = {
  fetch_libraries: 5,
  batch_scrape: 45,
  fetch_version_history: 120,
  batch_compare: 10,
  batch_recommend: 180,
  notify: 15,
}

function stepMeta(step: string) {
  return STEP_META[step] ?? { label: step.replace(/_/g, ' '), icon: '⚙️', description: '' }
}

// ── Step status icon ───────────────────────────────────────────────────────────
function StepIcon({ status, size = 16 }: { status: string; size?: number }) {
  if (status === 'completed' || status === 'success')
    return <CheckCircle size={size} className="text-green-500" />
  if (status === 'failed' || status === 'error')
    return <XCircle size={size} className="text-red-500" />
  if (status === 'running')
    return <Loader2 size={size} className="text-blue-500 animate-spin" />
  if (status === 'skipped')
    return <AlertCircle size={size} className="text-slate-400" />
  return <AlertCircle size={size} className="text-amber-400" />
}

function stepColor(status: string) {
  if (status === 'completed' || status === 'success') return 'border-green-200 bg-green-50'
  if (status === 'failed' || status === 'error')      return 'border-red-200 bg-red-50'
  if (status === 'running')                           return 'border-blue-200 bg-blue-50'
  if (status === 'skipped')                           return 'border-slate-200 bg-slate-50'
  return 'border-amber-200 bg-amber-50'
}

function stepTextColor(status: string) {
  if (status === 'completed' || status === 'success') return 'text-green-800'
  if (status === 'failed' || status === 'error')      return 'text-red-800'
  if (status === 'running')                           return 'text-blue-800'
  return 'text-slate-600'
}

function fmtDuration(s: number) {
  if (!s || s < 0.01) return '—'
  if (s < 1) return `${(s * 1000).toFixed(0)}ms`
  return `${s.toFixed(2)}s`
}

function fmtTime(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function totalDuration(run: PipelineRun) {
  if (!run.started_at || !run.finished_at) return null
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
  return fmtDuration(ms / 1000)
}

// Canonical pipeline step order
const PIPELINE_ORDER = ['fetch_libraries', 'batch_scrape', 'fetch_version_history', 'batch_compare', 'batch_recommend', 'notify']

// ── Live pipeline status card ──────────────────────────────────────────────────
function LivePipelineStatus({ runs, onOpenRun }: { runs: PipelineRun[]; onOpenRun?: (runId: string) => void }) {
  const latestRun = runs[0] ?? null
  const isRunning = latestRun?.status === 'running'
  const [canvasMode, setCanvasMode] = useState<'compact' | 'expanded'>('expanded')
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | null>(null)
  const [retryMsg, setRetryMsg] = useState<string | null>(null)
  const [retryResult, setRetryResult] = useState<RetryRunResponse | null>(null)
  const [activeRetryAction, setActiveRetryAction] = useState<{ mode: 'stage' | 'from-here'; step: string } | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const nodeRefs = useRef<Record<string, HTMLButtonElement | null>>({})

  // Build a map of step → status from the latest run
  const stepMap: Record<string, PipelineStep> = {}
  if (latestRun?.steps) {
    latestRun.steps.forEach((s) => { stepMap[s.step] = s })
  }

  // Determine the currently active step index for blinking
  const runningIdx = PIPELINE_ORDER.findIndex((s) => stepMap[s]?.status === 'running')
  // Pending = steps not yet started (no entry in stepMap)
  const lastCompletedIdx = PIPELINE_ORDER.reduce(
    (acc, s, i) => (stepMap[s]?.status === 'completed' || stepMap[s]?.status === 'success' ? i : acc), -1
  )

  const getStepStatus = (key: string, idx: number): string => {
    if (!latestRun) return 'idle'
    const s = stepMap[key]
    if (!s) {
      // Not yet started — pending if pipeline is running and this step is next
      if (isRunning && idx === lastCompletedIdx + 1 && runningIdx === -1) return 'pending'
      if (isRunning && idx > lastCompletedIdx && runningIdx === -1) return 'idle'
      return 'idle'
    }
    return s.status as ReturnType<typeof getStepStatus>
  }

  const stageModels = PIPELINE_ORDER.map((key, idx) => {
    const meta = stepMeta(key)
    const status = getStepStatus(key, idx)
    const step = stepMap[key]
    const isActive = status === 'running' || (isRunning && idx === lastCompletedIdx + 1 && runningIdx === -1)
    const slaTarget = STEP_SLA_SECONDS[key]
    const durationSeconds = step?.duration_seconds ?? 0
    const isTerminal = status === 'completed' || status === 'success' || status === 'failed' || status === 'error'
    const slaBreached = Boolean(isTerminal && durationSeconds > 0 && durationSeconds > slaTarget)
    return {
      key,
      idx,
      meta,
      status,
      step,
      isActive,
      slaTarget,
      durationSeconds,
      slaBreached,
    }
  })

  const completedCount = stageModels.filter((n) => n.status === 'completed' || n.status === 'success').length
  const progressPct = Math.round((completedCount / PIPELINE_ORDER.length) * 100)
  const activeStage = stageModels.find((n) => n.status === 'running')
    ?? [...stageModels].reverse().find((n) => Boolean(n.step))
  const selectedKey = selectedNodeKey ?? activeStage?.key ?? null
  const selectedNode = stageModels.find((n) => n.key === selectedKey) ?? null
  const stageKeys = stageModels.map((n) => n.key)
  const canRetry = Boolean(latestRun && selectedNode && selectedNode.step)

  const retryStageMut = useMutation({
    mutationFn: (payload: { source_run_id: string; step: string }) => schedulerApi.retryStage(payload),
    onSuccess: (res) => {
      const data = res.data as RetryRunResponse
      setRetryResult(data)
      setRetryMsg(data.message)
      if (data.run_id) onOpenRun?.(data.run_id)
    },
    onError: (err: unknown) => {
      setRetryResult(null)
      setRetryMsg(`Retry failed: ${parseApiError(err, 'Unable to queue retry stage')}`)
    },
    onSettled: () => setActiveRetryAction(null),
  })

  const retryFromHereMut = useMutation({
    mutationFn: (payload: { source_run_id: string; step: string }) => schedulerApi.retryFromHere(payload),
    onSuccess: (res) => {
      const data = res.data as RetryRunResponse
      setRetryResult(data)
      setRetryMsg(data.message)
      if (data.run_id) onOpenRun?.(data.run_id)
    },
    onError: (err: unknown) => {
      setRetryResult(null)
      setRetryMsg(`Retry-from-here failed: ${parseApiError(err, 'Unable to queue retry-from-here')}`)
    },
    onSettled: () => setActiveRetryAction(null),
  })

  useEffect(() => {
    const keyToCenter = selectedKey ?? activeStage?.key
    if (!keyToCenter) return
    const node = nodeRefs.current[keyToCenter]
    if (node) {
      node.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
    }
  }, [selectedKey, activeStage?.key, canvasMode])

  useEffect(() => {
    if (!retryMsg) return
    const id = window.setTimeout(() => setRetryMsg(null), 2800)
    return () => window.clearTimeout(id)
  }, [retryMsg])

  const handleCanvasKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null
    const tag = (target?.tagName || '').toLowerCase()
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || target?.isContentEditable) return
    if (!stageKeys.length) return

    const currentIdx = Math.max(0, stageKeys.findIndex((k) => k === selectedKey))
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const nextIdx = Math.min(stageKeys.length - 1, currentIdx + 1)
      setSelectedNodeKey(stageKeys[nextIdx])
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prevIdx = Math.max(0, currentIdx - 1)
      setSelectedNodeKey(stageKeys[prevIdx])
    }
    if (e.key === 'Home') {
      e.preventDefault()
      setSelectedNodeKey(stageKeys[0])
    }
    if (e.key === 'End') {
      e.preventDefault()
      setSelectedNodeKey(stageKeys[stageKeys.length - 1])
    }
  }

  const boardTone = !latestRun
    ? 'border-slate-200 bg-slate-50'
    : isRunning
      ? 'border-blue-200 bg-gradient-to-br from-blue-50 via-white to-cyan-50'
      : latestRun.status === 'completed'
        ? 'border-green-200 bg-gradient-to-br from-green-50 via-white to-emerald-50'
        : latestRun.status === 'failed'
          ? 'border-red-200 bg-gradient-to-br from-red-50 via-white to-rose-50'
          : 'border-slate-200 bg-slate-50'

  const connectorClass = (status: string) =>
    status === 'completed' || status === 'success'
      ? 'bg-green-400'
      : status === 'running'
        ? 'bg-blue-400'
        : status === 'failed' || status === 'error'
          ? 'bg-red-400'
          : 'bg-slate-200'

  const nodeClass = (status: string) => {
    if (status === 'completed' || status === 'success') return 'border-green-300 bg-green-100 text-green-800'
    if (status === 'failed' || status === 'error') return 'border-red-300 bg-red-100 text-red-800'
    if (status === 'running') return 'border-blue-300 bg-blue-100 text-blue-800 ring-2 ring-blue-300/60'
    if (status === 'pending') return 'border-amber-200 bg-amber-50 text-amber-700'
    return 'border-slate-200 bg-white text-slate-500'
  }

  return (
    <div className={`card border-2 p-4 ${boardTone}`} tabIndex={0} onKeyDown={handleCanvasKeyDown}>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <p className="text-xs font-bold text-slate-700 uppercase tracking-wider">Workflow Execution Canvas</p>
          <p className="text-[11px] text-slate-500 mt-0.5">Node-style pipeline progression for real-time execution visibility with orchestration-style controls.</p>
          <p className="text-[10px] text-slate-400 mt-1">Keyboard: use ←/→ to move between nodes, Home/End for first/last.</p>
        </div>
        <div className="flex items-start gap-3">
          <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
            <button
              className={`px-2 py-1 text-[10px] font-semibold rounded ${canvasMode === 'compact' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
              onClick={() => setCanvasMode('compact')}
            >
              Compact
            </button>
            <button
              className={`px-2 py-1 text-[10px] font-semibold rounded ${canvasMode === 'expanded' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
              onClick={() => setCanvasMode('expanded')}
            >
              Expanded
            </button>
          </div>
          {latestRun ? (
            <div className="text-right">
              <p className="text-[11px] text-slate-500">Run ID</p>
              <p className="text-xs font-mono text-slate-700">{latestRun.run_id.slice(0, 14)}…</p>
            </div>
          ) : (
            <span className="text-xs text-slate-500">No run available yet</span>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 mb-4">
        <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1.5">
          <span>Execution progress</span>
          <span>{completedCount}/{PIPELINE_ORDER.length} stages · {progressPct}%</span>
        </div>
        <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${isRunning ? 'bg-blue-500' : latestRun?.status === 'completed' ? 'bg-green-500' : latestRun?.status === 'failed' ? 'bg-red-500' : 'bg-slate-400'}`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      <div className="sm:hidden rounded-lg border border-slate-200 bg-white px-3 py-2.5 mb-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider">Mini Map</p>
          {selectedNode && <span className="text-[10px] text-slate-500">Selected: {selectedNode.meta.label}</span>}
        </div>
        <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
          {stageModels.map((node, idx) => (
            <div key={`mini-${node.key}`} className="flex items-center gap-1">
              <button
                className={`w-5 h-5 rounded-full border text-[9px] font-bold ${nodeClass(node.status)} ${selectedKey === node.key ? 'ring-2 ring-primary-300' : ''}`}
                onClick={() => setSelectedNodeKey(node.key)}
                title={node.meta.label}
              >
                {idx + 1}
              </button>
              {idx < stageModels.length - 1 && (
                <div className={`w-4 h-0.5 rounded ${connectorClass(node.status)}`} />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto pb-2" ref={scrollRef}>
        <div className={`flex items-center gap-2 ${canvasMode === 'expanded' ? 'min-w-[980px]' : 'min-w-[760px]'}`}>
          {stageModels.map((node) => {
            return (
              <div key={node.key} className="contents">
                <button
                  ref={(el) => { nodeRefs.current[node.key] = el }}
                  className={`${canvasMode === 'expanded' ? 'w-[150px]' : 'w-[118px]'} rounded-xl border px-3 py-2.5 transition-all text-left ${nodeClass(node.status)} ${node.isActive ? 'shadow-md shadow-blue-200/70' : 'shadow-sm'} ${selectedKey === node.key ? 'ring-2 ring-primary-300' : ''}`}
                  onClick={() => setSelectedNodeKey((prev) => prev === node.key ? null : node.key)}
                  title={`Open details for ${node.meta.label}`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm">{node.meta.icon}</span>
                    <span className="text-[10px] font-mono opacity-60">{node.idx + 1}</span>
                  </div>
                  <p className="text-[11px] font-semibold leading-tight">{node.meta.label}</p>
                  <div className="mt-1.5 flex items-center gap-1 text-[10px]">
                    {node.status === 'completed' || node.status === 'success' ? <CheckCircle size={11} className="text-green-600" /> : null}
                    {node.status === 'failed' || node.status === 'error' ? <XCircle size={11} className="text-red-600" /> : null}
                    {node.status === 'running' ? <Loader2 size={11} className="text-blue-600 animate-spin" /> : null}
                    {node.status === 'pending' ? <AlertCircle size={11} className="text-amber-600" /> : null}
                    <span className="uppercase tracking-wide">{node.status}</span>
                  </div>
                  {canvasMode === 'expanded' && (
                    <p className="text-[10px] mt-1 opacity-80 truncate">
                      {node.step?.items_processed ? `${node.step.items_processed} items` : node.meta.description}
                    </p>
                  )}
                </button>
                {node.idx < stageModels.length - 1 && (
                  <div className={`h-1 rounded-full flex-1 min-w-[20px] ${connectorClass(node.status)} ${node.status === 'running' ? 'animate-pulse' : ''}`} />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {selectedNode && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-white p-3">
          <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
            <div>
              <p className="text-xs font-semibold text-slate-700">{selectedNode.meta.icon} {selectedNode.meta.label}</p>
              <p className="text-[11px] text-slate-500">One-click node inspector</p>
            </div>
            <span className={`text-[10px] font-semibold px-2 py-1 rounded-full ${nodeClass(selectedNode.status)}`}>
              {selectedNode.status.toUpperCase()}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
            <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
              <p className="text-slate-500">Started</p>
              <p className="font-medium text-slate-700">{fmtTime(selectedNode.step?.started_at ?? null)}</p>
            </div>
            <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
              <p className="text-slate-500">Finished</p>
              <p className="font-medium text-slate-700">{fmtTime(selectedNode.step?.finished_at ?? null)}</p>
            </div>
            <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
              <p className="text-slate-500">Duration</p>
              <p className="font-medium text-slate-700">{selectedNode.durationSeconds > 0 ? fmtDuration(selectedNode.durationSeconds) : '—'}</p>
            </div>
            <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
              <p className="text-slate-500">SLA</p>
              <p className={`font-medium ${selectedNode.slaBreached ? 'text-red-700' : 'text-slate-700'}`}>
                ≤ {selectedNode.slaTarget}s{selectedNode.slaBreached ? ' · Breached' : ''}
              </p>
            </div>
          </div>
          <div className="mt-2.5 rounded border border-slate-200 bg-slate-50 px-2.5 py-2">
            <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-wider mb-1">Logs / Message</p>
            <p className="text-xs text-slate-700">{selectedNode.step?.message || 'No detailed log message captured for this stage yet.'}</p>
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <button
              className="btn-secondary py-1.5 px-2.5 text-[11px]"
              disabled={!canRetry || retryStageMut.isPending || retryFromHereMut.isPending}
              onClick={() => {
                if (!latestRun || !selectedNode?.step) {
                  setRetryMsg('Retry unavailable for pending/idle stages. Select an executed stage.')
                  return
                }
                setActiveRetryAction({ mode: 'stage', step: selectedNode.step.step })
                retryStageMut.mutate({ source_run_id: latestRun.run_id, step: selectedNode.step.step })
              }}
            >
              {retryStageMut.isPending && activeRetryAction?.mode === 'stage' && activeRetryAction?.step === selectedNode?.step?.step
                ? <><Loader2 size={11} className="animate-spin" /> Queuing…</>
                : 'Retry Stage'}
            </button>
            <button
              className="btn-secondary py-1.5 px-2.5 text-[11px]"
              disabled={!canRetry || retryStageMut.isPending || retryFromHereMut.isPending}
              onClick={() => {
                if (!latestRun || !selectedNode?.step) {
                  setRetryMsg('Retry-from-here unavailable for pending/idle stages. Select an executed stage.')
                  return
                }
                setActiveRetryAction({ mode: 'from-here', step: selectedNode.step.step })
                retryFromHereMut.mutate({ source_run_id: latestRun.run_id, step: selectedNode.step.step })
              }}
            >
              {retryFromHereMut.isPending && activeRetryAction?.mode === 'from-here' && activeRetryAction?.step === selectedNode?.step?.step
                ? <><Loader2 size={11} className="animate-spin" /> Queuing…</>
                : 'Retry From Here'}
            </button>
            {!canRetry && <span className="text-[10px] text-slate-500">Select an executed stage to enable retry actions.</span>}
          </div>
          {retryMsg && (
            <div className="mt-2 rounded border border-indigo-200 bg-indigo-50 px-2.5 py-2 text-xs text-indigo-700">
              <p>{retryMsg}</p>
              {retryResult && (
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="font-semibold">Status: {retryResult.request_status}</span>
                  {retryResult.run_id && (
                    <button
                      className="text-primary-700 underline underline-offset-2"
                      onClick={() => onOpenRun?.(retryResult.run_id as string)}
                    >
                      Open run {retryResult.run_id.slice(0, 12)}…
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {latestRun && activeStage?.step && (
        <div className={`mt-4 rounded-lg border px-3 py-2.5 text-xs ${isRunning ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-slate-50 border-slate-200 text-slate-700'}`}>
          <p className="font-semibold mb-0.5">{isRunning ? 'Now executing' : 'Latest executed stage'}: {activeStage.meta.label}</p>
          <p>{activeStage.step.message || 'Stage update captured.'}</p>
        </div>
      )}
    </div>
  )
}


function StepPipeline({ steps, isRunning = false }: { steps: PipelineStep[]; isRunning?: boolean }) {
  // Always show all 6 pipeline steps — completed, running, or pending
  const stepMap: Record<string, PipelineStep> = {}
  steps.forEach((s) => { stepMap[s.step] = s })

  return (
    <div className="mt-4 space-y-1.5">
      {PIPELINE_ORDER.map((key, i) => {
        const meta   = stepMeta(key)
        const step   = stepMap[key]
        const status = step?.status ?? (isRunning ? 'pending' : 'waiting')
        const slaTarget = STEP_SLA_SECONDS[key]
        const hasDuration = Boolean(step?.duration_seconds && step.duration_seconds > 0)
        const isTerminal = status === 'completed' || status === 'success' || status === 'failed' || status === 'error'
        const slaBreached = Boolean(isTerminal && hasDuration && step && step.duration_seconds > slaTarget)

        const rowColor =
          status === 'completed' || status === 'success' ? 'border-green-200 bg-green-50' :
          status === 'failed'    || status === 'error'   ? 'border-red-200 bg-red-50' :
          status === 'running'                           ? 'border-blue-200 bg-blue-50' :
          status === 'pending'                           ? 'border-amber-100 bg-amber-50' :
                                                           'border-slate-200 bg-slate-50/40'

        const textColor =
          status === 'completed' || status === 'success' ? 'text-green-800' :
          status === 'failed'    || status === 'error'   ? 'text-red-800' :
          status === 'running'                           ? 'text-blue-800' :
          status === 'pending'                           ? 'text-amber-700' :
                                                           'text-slate-400'

        return (
          <div key={key} className={`rounded-lg border px-4 py-2.5 ${rowColor} ${status === 'running' ? 'ring-1 ring-blue-400' : ''}`}>
            <div className="flex items-start gap-3">
              {/* Step number + connector */}
              <div className="flex flex-col items-center pt-0.5 flex-shrink-0">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  status === 'completed' || status === 'success' ? 'bg-green-500 text-white' :
                  status === 'failed'    || status === 'error'   ? 'bg-red-500 text-white' :
                  status === 'running'                           ? 'bg-blue-500 text-white animate-pulse' :
                  status === 'pending'                           ? 'bg-amber-200 text-amber-700' :
                                                                   'bg-slate-200 text-slate-400'
                }`}>
                  {status === 'completed' || status === 'success' ? '✓' :
                   status === 'failed'    || status === 'error'   ? '✗' :
                   status === 'running'                           ? '…' : i + 1}
                </div>
                {i < PIPELINE_ORDER.length - 1 && (
                  <div className={`w-px flex-1 mt-0.5 ${
                    status === 'completed' || status === 'success' ? 'bg-green-300' : 'bg-slate-200'
                  }`} style={{ minHeight: 8 }} />
                )}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                  <span className={`text-xs font-semibold ${textColor}`}>
                    {meta.icon} {meta.label}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    SLA ≤ {slaTarget}s
                  </span>
                  {step?.items_processed != null && step.items_processed > 0 && (
                    <span className="text-xs text-slate-500">{step.items_processed} items</span>
                  )}
                  {isTerminal && hasDuration && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${slaBreached ? 'bg-red-100 text-red-700 border-red-200' : 'bg-green-100 text-green-700 border-green-200'}`}>
                      {slaBreached ? `SLA breached (${fmtDuration(step!.duration_seconds)})` : `Within SLA (${fmtDuration(step!.duration_seconds)})`}
                    </span>
                  )}
                  <span className={`text-[11px] font-medium ml-auto ${textColor}`}>
                    {status === 'pending' ? '⏳ Pending' :
                     status === 'waiting' ? '— Waiting' :
                     status === 'running' ? '⚡ Running…' :
                     `${status.toUpperCase()}${step?.duration_seconds && step.duration_seconds > 0 ? ` · ${fmtDuration(step.duration_seconds)}` : ''}`}
                  </span>
                </div>

                {/* Message (only for completed/failed/running steps) */}
                {step?.message && (
                  <p className={`text-xs mt-0.5 ${textColor} opacity-80`}>{step.message}</p>
                )}
                {!step && status === 'pending' && (
                  <p className="text-[11px] text-slate-400 mt-0.5">{meta.description}</p>
                )}

                {/* Timing */}
                {step && (
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    {fmtTime(step.started_at)}
                    {step.finished_at && ` → ${fmtTime(step.finished_at)}`}
                  </p>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Run card ───────────────────────────────────────────────────────────────────
function RunCard({ run, isHighlighted = false }: { run: PipelineRun; isHighlighted?: boolean }) {
  const [expanded, setExpanded] = useState(run.status === 'running')
  const isManual = run.triggered_by === 'manual'
  const duration = totalDuration(run)

  return (
    <div className={`card overflow-hidden ${isHighlighted ? 'ring-2 ring-primary-400 border-primary-300' : ''}`}>
      {/* Header row */}
      <div
        className="px-5 py-4 flex items-center gap-3 cursor-pointer hover:bg-slate-50 transition-colors"
        onClick={() => setExpanded((p) => !p)}
      >
        {/* Status icon */}
        <div className="flex-shrink-0">
          <StepIcon status={run.status} size={18} />
        </div>

        {/* Run info */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
              isManual
                ? 'bg-blue-100 text-blue-700'
                : 'bg-purple-100 text-purple-700'
            }`}>
              {isManual ? '▶ Manual' : '⏰ Scheduled'}
            </span>
            <span className="font-mono text-xs text-slate-500 truncate">{run.run_id.slice(0, 16)}…</span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1">
            <span className="flex items-center gap-1 text-xs text-slate-500">
              <Calendar size={10} /> {new Date(run.started_at).toLocaleString()}
            </span>
            {run.finished_at && (
              <span className="flex items-center gap-1 text-xs text-slate-500">
                <Clock size={10} /> {duration} total
              </span>
            )}
            <span className="flex items-center gap-1 text-xs text-slate-500">
              <Library size={10} /> {run.total_libraries ?? 0} SDKs
            </span>
            <span className="flex items-center gap-1 text-xs text-slate-500">
              <User size={10} /> {run.triggered_by}
            </span>
          </div>
        </div>

        {/* Status badge + step summary */}
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded ${
            run.status === 'completed' || run.status === 'success'
              ? 'bg-green-100 text-green-700'
              : run.status === 'failed' || run.status === 'error'
                ? 'bg-red-100 text-red-700'
                : run.status === 'running'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-slate-100 text-slate-600'
          }`}>
            {run.status}
          </span>
          {run.steps?.length > 0 && (
            <span className="text-[10px] text-slate-400">
              {run.steps.filter(s => s.status === 'completed' || s.status === 'success').length}
              /{run.steps.length} steps done
            </span>
          )}
        </div>

        <div className="flex-shrink-0 text-slate-400">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {/* Error bar */}
      {run.error && (
        <div className="px-5 py-2 bg-red-50 border-t border-red-200 text-xs text-red-700">
          ❌ {run.error}
        </div>
      )}

      {/* Expanded step pipeline — always shows all 6 steps */}
      {expanded && (
        <div className="px-5 pb-5 border-t border-slate-100 bg-slate-50/50">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mt-4 mb-2">
            Pipeline Steps
          </p>
          <StepPipeline steps={run.steps ?? []} isRunning={run.status === 'running'} />
        </div>
      )}
    </div>
  )
}

// ── Main Scheduler page ────────────────────────────────────────────────────────
export default function Scheduler() {
  const qc = useQueryClient()
  const { isAdmin } = useAuth()
  const [runMsg, setRunMsg] = useState<string | null>(null)
  const [quickRetryMsg, setQuickRetryMsg] = useState<string | null>(null)
  const [confirmPending, setConfirmPending] = useState(false)
  const [historyPage, setHistoryPage] = useState(1)
  const [historyPageSize, setHistoryPageSize] = useState(5)
  const [focusRunId, setFocusRunId] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<SchedulerCategory>('control')
  const [editingSchedule, setEditingSchedule] = useState(false)
  const [quickRetryPending, setQuickRetryPending] = useState<{ mode: 'stage' | 'from-here'; step: string } | null>(null)

  const { data: schedData } = useQuery({
    queryKey: ['schedule'],
    queryFn: () => schedulerApi.getSchedule(),
  })
  const { data: runsData, refetch, isFetching } = useQuery({
    queryKey: ['pipeline-runs'],
    queryFn: () => schedulerApi.getRuns(),
    refetchInterval: 5000,
  })
  const { data: llmCfgData } = useQuery({
    queryKey: ['settings-llm'],
    queryFn: () => settingsApi.getLlm(),
  })

  const runs: PipelineRun[] = Array.isArray(runsData?.data) ? (runsData!.data as PipelineRun[]) : []
  const latestRun = runs[0] ?? null
  const failedStepsInLatestRun = useMemo(
    () => (latestRun?.steps ?? []).filter((s) => s.status === 'failed' || s.status === 'error'),
    [latestRun]
  )

  // When the latest run transitions running → completed/failed, refresh all library-related caches
  const prevStatusRef = useRef<string | undefined>(undefined)
  useEffect(() => {
    const currentStatus = runs[0]?.status
    if (prevStatusRef.current === 'running' && currentStatus && currentStatus !== 'running') {
      qc.invalidateQueries({ queryKey: ['libraries'] })
      qc.invalidateQueries({ queryKey: ['sla-summary'] })
      qc.invalidateQueries({ queryKey: ['hitl-pending'] })
      qc.invalidateQueries({ queryKey: ['recommendations'] })
    }
    prevStatusRef.current = currentStatus
  }, [runs, qc])
  const schedule = schedData?.data as {
    cron?: string; enabled?: boolean; next_run?: string; last_run?: string
  } | undefined
  const llmCfg = (llmCfgData?.data ?? {}) as {
    provider?: string
    model_name?: string
    enabled?: boolean
    api_key_set?: boolean
    timeout_seconds?: number
    max_tokens?: number
  }
  const llmActive = Boolean(llmCfg.enabled && llmCfg.api_key_set)
  const historyTotalPages = Math.max(1, Math.ceil(runs.length / historyPageSize))
  const safeHistoryPage = Math.min(historyPage, historyTotalPages)
  const historyStart = (safeHistoryPage - 1) * historyPageSize
  const historyEnd = Math.min(historyStart + historyPageSize, runs.length)
  const pagedRuns = runs.slice(historyStart, historyEnd)
  const retryAnalytics = useMemo(() => {
    const retryRuns = runs.filter((r) => String(r.triggered_by ?? '').startsWith('retry_'))
    const total = retryRuns.length
    const completed = retryRuns.filter((r) => r.status === 'completed').length
    const partial = retryRuns.filter((r) => r.status === 'partial').length
    const failed = retryRuns.filter((r) => r.status === 'failed').length
    const terminal = completed + partial + failed
    const successRate = terminal > 0 ? Math.round((completed / terminal) * 100) : 0

    const byStage: Record<string, { attempts: number; completed: number; failed: number }> = {}
    const failedStageCount: Record<string, number> = {}
    const recoveryDurations: number[] = []

    for (const run of retryRuns) {
      const trigger = String(run.triggered_by ?? '')
      const stage = trigger.includes(':') ? trigger.split(':')[1] : 'unknown'
      byStage[stage] = byStage[stage] ?? { attempts: 0, completed: 0, failed: 0 }
      byStage[stage].attempts += 1
      if (run.status === 'completed') byStage[stage].completed += 1
      if (run.status === 'failed' || run.status === 'partial') byStage[stage].failed += 1

      const failedStep = run.steps?.find((s) => s.status === 'failed' || s.status === 'error')
      if (failedStep?.step) {
        failedStageCount[failedStep.step] = (failedStageCount[failedStep.step] ?? 0) + 1
      }

      if (run.status === 'completed' && run.started_at && run.finished_at) {
        const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
        if (ms > 0) recoveryDurations.push(ms / 1000)
      }
    }

    const stageRows = Object.entries(byStage)
      .map(([stage, v]) => ({
        stage,
        attempts: v.attempts,
        successPct: v.attempts > 0 ? Math.round((v.completed / v.attempts) * 100) : 0,
      }))
      .sort((a, b) => b.attempts - a.attempts)

    const topFailingStage = Object.entries(failedStageCount)
      .sort((a, b) => b[1] - a[1])[0]

    return {
      total,
      completed,
      partial,
      failed,
      successRate,
      meanTimeToRecoverSec: recoveryDurations.length
        ? Math.round(recoveryDurations.reduce((a, b) => a + b, 0) / recoveryDurations.length)
        : null,
      stageRows,
      topFailingStage: topFailingStage
        ? { stage: topFailingStage[0], count: topFailingStage[1] }
        : null,
    }
  }, [runs])

  useEffect(() => {
    if (!focusRunId) return
    const idx = runs.findIndex((r) => r.run_id === focusRunId)
    if (idx >= 0) {
      const targetPage = Math.floor(idx / historyPageSize) + 1
      setHistoryPage(targetPage)
    }
  }, [focusRunId, runs, historyPageSize])

  useEffect(() => {
    setHistoryPage(1)
  }, [historyPageSize])

  useEffect(() => {
    if (historyPage > historyTotalPages) setHistoryPage(historyTotalPages)
  }, [historyPage, historyTotalPages])

  const triggerMut = useMutation({
    mutationFn: () => schedulerApi.triggerRun(),
    onSuccess: (res) => {
      const id = (res.data as { run_id?: string })?.run_id ?? 'unknown'
      setRunMsg(`✅ Pipeline started — run ID: ${id}`)
      setConfirmPending(false)
      qc.invalidateQueries({ queryKey: ['pipeline-runs'] })
    },
    onError: () => {
      setRunMsg('❌ Failed to trigger pipeline. Ensure all services are running.')
      setConfirmPending(false)
    },
  })

  const updateScheduleMut = useMutation({
    mutationFn: ({ cron, enabled }: { cron: string; enabled: boolean }) =>
      schedulerApi.updateSchedule({ cron, enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schedule'] })
      setEditingSchedule(false)
      setRunMsg('✅ Schedule updated successfully')
    },
    onError: () => setRunMsg('❌ Failed to update schedule'),
  })

  const quickRetryStageMut = useMutation({
    mutationFn: (payload: { source_run_id: string; step: string }) => schedulerApi.retryStage(payload),
    onMutate: (payload) => setQuickRetryPending({ mode: 'stage', step: payload.step }),
    onSuccess: (res) => {
      const data = res.data as RetryRunResponse
      setQuickRetryMsg(data.message)
      if (data.run_id) {
        setRunMsg(`✅ Retry stage queued — run ID: ${data.run_id}`)
      }
      qc.invalidateQueries({ queryKey: ['pipeline-runs'] })
      refetch()
    },
    onError: (err: unknown) => {
      setQuickRetryMsg(`Retry failed: ${parseApiError(err, 'Unable to queue retry stage')}`)
    },
    onSettled: () => setQuickRetryPending(null),
  })

  const quickRetryFromHereMut = useMutation({
    mutationFn: (payload: { source_run_id: string; step: string }) => schedulerApi.retryFromHere(payload),
    onMutate: (payload) => setQuickRetryPending({ mode: 'from-here', step: payload.step }),
    onSuccess: (res) => {
      const data = res.data as RetryRunResponse
      setQuickRetryMsg(data.message)
      if (data.run_id) {
        setRunMsg(`✅ Retry-from-here queued — run ID: ${data.run_id}`)
      }
      qc.invalidateQueries({ queryKey: ['pipeline-runs'] })
      refetch()
    },
    onError: (err: unknown) => {
      setQuickRetryMsg(`Retry-from-here failed: ${parseApiError(err, 'Unable to queue retry-from-here')}`)
    },
    onSettled: () => setQuickRetryPending(null),
  })

  const cleanupHistoryMut = useMutation({
    mutationFn: () => schedulerApi.cleanupHistory({ retention_days: 30, include_partial: true }),
    onSuccess: (res) => {
      const d = (res.data ?? {}) as { runs_deleted?: number; details_deleted?: number }
      setRunMsg(`✅ History cleanup complete — deleted ${d.runs_deleted ?? 0} runs and ${d.details_deleted ?? 0} detail rows (older than 30 days).`)
      qc.invalidateQueries({ queryKey: ['pipeline-runs'] })
      refetch()
    },
    onError: (err: unknown) => {
      setRunMsg(`❌ History cleanup failed: ${parseApiError(err, 'Unable to clear old history')}`)
    },
  })

  const activeRuns = runs.filter(r => r.status === 'running').length
  const failedStep = latestRun?.steps?.find((s) => s.status === 'failed' || s.status === 'error')
  const showFailureStrip = Boolean(latestRun && (latestRun.status === 'failed' || latestRun.status === 'partial'))
  const failureCause = failedStep?.message || latestRun?.error || 'One or more steps failed without an explicit error message.'
  const failureStepLabel = failedStep ? stepMeta(failedStep.step).label : 'Pipeline'

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Pipeline Operations</h1>
          <p className="page-subtitle">
            Pipeline execution — {runs.length} run{runs.length !== 1 ? 's' : ''}
            {activeRuns > 0 && <span className="ml-2 text-blue-600 font-medium">● {activeRuns} active</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Refresh
          </button>
          {isAdmin && (confirmPending ? (
            <div className="flex items-center gap-2 bg-amber-50 border border-amber-300 rounded-lg px-3 py-1.5">
              <span className="text-xs text-amber-800 font-medium">Trigger pipeline now?</span>
              <button
                className="btn-primary py-1 px-3 text-xs"
                onClick={() => triggerMut.mutate()}
                disabled={triggerMut.isPending}
              >
                {triggerMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                Yes, Run
              </button>
              <button
                className="btn-secondary py-1 px-2 text-xs"
                onClick={() => setConfirmPending(false)}
                disabled={triggerMut.isPending}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              className="btn-primary"
              onClick={() => { setRunMsg(null); setConfirmPending(true) }}
              disabled={triggerMut.isPending || activeRuns > 0}
              title={activeRuns > 0 ? 'Pipeline already running' : 'Trigger pipeline manually'}
            >
              <Play size={14} /> Run Now
            </button>
          ))}
        </div>
      </div>

      <ExecutiveTriad
        impact={showFailureStrip ? `Latest run is ${latestRun?.status}; root-cause remediation is required before the next cycle.` : `Pipeline health is stable with ${activeRuns} active run${activeRuns === 1 ? '' : 's'}.`}
        owner="Release Operations Lead"
        nextAction={activeRuns > 0 ? 'Monitor current run steps and validate completion against SLA targets.' : 'Trigger a governed run and review runtime configuration readiness.'}
        tone={showFailureStrip ? 'critical' : activeRuns > 0 ? 'warning' : 'neutral'}
      />

      <SectionCard cardClassName="card p-4">
        <div className="mb-2">
          <p className="text-xs font-semibold text-slate-700">Pipeline Category Navigator</p>
          <p className="text-[11px] text-slate-500">Open one category at a time to keep operations review focused and low-scroll.</p>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {[
            { key: 'control' as const, label: 'Control Center' },
            { key: 'runtime' as const, label: 'Runtime Health' },
            { key: 'current' as const, label: 'Current Run' },
            { key: 'history' as const, label: 'Event History' },
          ].map((item) => (
            <button
              key={item.key}
              className={`px-3 py-2 rounded-lg border text-xs font-semibold transition ${
                activeCategory === item.key
                  ? 'bg-primary-50 border-primary-300 text-primary-700'
                  : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
              onClick={() => setActiveCategory(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </SectionCard>

      {/* Top failure root-cause strip */}
      {showFailureStrip && (
        <div className="px-4 py-3 rounded-lg border border-red-200 bg-red-50">
          <p className="text-xs font-semibold text-red-700 uppercase tracking-wider">Latest Failure Root Cause</p>
          <p className="text-sm text-red-800 mt-1">
            <span className="font-semibold">{failureStepLabel}:</span> {failureCause}
          </p>
          {latestRun && (
            <p className="text-[11px] text-red-600 mt-1">
              Run {latestRun.run_id.slice(0, 12)}… · status: {latestRun.status}
            </p>
          )}
        </div>
      )}

      {activeCategory === 'control' && (
        <>
          {/* Control */}
          <div className="px-1">
            <h2 className="text-sm font-semibold text-slate-800">Control</h2>
            <p className="text-xs text-slate-500">Run controls, schedule and execution configuration.</p>
          </div>

          {/* Trigger feedback */}
          {runMsg && (
            <div className={`px-4 py-3 rounded-lg text-sm flex justify-between items-center border ${
              runMsg.startsWith('✅')
                ? 'bg-green-50 border-green-200 text-green-700'
                : 'bg-red-50 border-red-200 text-red-700'
            }`}>
              {runMsg}
              <button onClick={() => setRunMsg(null)} className="text-xs opacity-60 hover:opacity-100 ml-4">✕</button>
            </div>
          )}

          {/* Schedule config — view or edit inline */}
          {schedule && !editingSchedule && (
            <div className="card p-4">
          <div className="flex flex-wrap gap-6 items-start">
            <div className="flex items-start gap-3 flex-1 min-w-[240px]">
              <Clock size={16} className="text-slate-400 mt-1 flex-shrink-0" />
              <div>
                <p className="text-xs text-slate-500 mb-0.5">Schedule</p>
                <p className="font-mono text-sm font-bold text-slate-900 tracking-wide">
                  {schedule.cron ?? 'Not configured'}
                </p>
                {schedule.cron && (
                  <p className="text-xs text-primary-600 font-medium mt-0.5">
                    🕐 {parseCron(schedule.cron)}
                  </p>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-0.5">Status</p>
              <p className="text-sm font-semibold">{schedule.enabled ? '✅ Enabled' : '❌ Disabled'}</p>
            </div>
            {schedule.next_run && (
              <div>
                <p className="text-xs text-slate-500 mb-0.5">Next Run</p>
                <p className="text-sm font-medium text-slate-800">
                  {new Date(schedule.next_run).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
                </p>
                <p className="text-xs text-slate-500">
                  {new Date(schedule.next_run).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
            )}
            {schedule.last_run && (
              <div>
                <p className="text-xs text-slate-500 mb-0.5">Last Run</p>
                <p className="text-sm font-medium text-slate-800">
                  {new Date(schedule.last_run).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
                </p>
                <p className="text-xs text-slate-500">
                  {new Date(schedule.last_run).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
            )}
            <div className="ml-auto">
              <button
                className="btn-secondary py-1.5 text-xs"
                onClick={() => setEditingSchedule(true)}
              >
                ✏️ Edit Schedule
              </button>
            </div>
          </div>
            </div>
          )}

          {schedule && editingSchedule && (
            <ScheduleEditor
              current={{ cron: schedule.cron ?? '0 2 * * *', enabled: schedule.enabled ?? true }}
              onSave={async (cron, enabled) => {
                await updateScheduleMut.mutateAsync({ cron, enabled })
              }}
              onCancel={() => setEditingSchedule(false)}
            />
          )}
        </>
      )}

      {activeCategory === 'runtime' && (
        <>
          <div className="px-1">
            <h2 className="text-sm font-semibold text-slate-800">Runtime Health</h2>
            <p className="text-xs text-slate-500">Current recommendation engine mode and model readiness.</p>
          </div>

          {/* LLM runtime status */}
          <div className="card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs text-slate-500">Recommendation Engine</p>
            <h3 className="text-sm font-semibold text-slate-800">LLM Runtime Configuration</h3>
            <p className={`text-xs mt-0.5 font-medium ${llmActive ? 'text-green-600' : 'text-amber-600'}`}>
              {llmActive ? '✅ LLM configured and active' : '⚠️ LLM unavailable or disabled — rule-based fallback will be used'}
            </p>
          </div>
          <span className={`text-xs px-2 py-1 rounded-full font-semibold ${llmActive ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
            {llmActive ? 'AI Enabled' : 'Fallback Mode'}
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[11px] text-slate-500">Provider</p>
            <p className="text-sm font-medium text-slate-800">{llmCfg.provider || 'Not set'}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[11px] text-slate-500">Model</p>
            <p className="text-sm font-medium text-slate-800">{llmCfg.model_name || 'Not set'}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[11px] text-slate-500">Key</p>
            <p className="text-sm font-medium text-slate-800">{llmCfg.api_key_set ? 'Configured' : 'Missing'}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[11px] text-slate-500">Enabled</p>
            <p className="text-sm font-medium text-slate-800">{llmCfg.enabled ? 'Yes' : 'No'}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[11px] text-slate-500">Timeout</p>
            <p className="text-sm font-medium text-slate-800">{llmCfg.timeout_seconds ? `${llmCfg.timeout_seconds}s` : '—'}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[11px] text-slate-500">Max Tokens</p>
            <p className="text-sm font-medium text-slate-800">{llmCfg.max_tokens ?? '—'}</p>
          </div>
        </div>
          </div>
        </>
      )}

      {activeCategory === 'current' && (
        <>
          {/* Current run */}
          <div className="px-1">
            <h2 className="text-sm font-semibold text-slate-800">Current Run</h2>
            <p className="text-xs text-slate-500">Live pipeline stage progression and latest execution snapshot.</p>
          </div>

          {latestRun && (
            <div className="card p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <p className="text-[11px] text-slate-500">Run ID</p>
              <p className="text-sm font-mono text-slate-800">{latestRun.run_id.slice(0, 12)}…</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500">Status</p>
              <p className="text-sm font-semibold text-slate-800">{latestRun.status}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500">Started</p>
              <p className="text-sm font-medium text-slate-800">{latestRun.started_at ? new Date(latestRun.started_at).toLocaleTimeString() : '—'}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500">Duration</p>
              <p className="text-sm font-medium text-slate-800">{totalDuration(latestRun) ?? 'Running…'}</p>
            </div>
          </div>
            </div>
          )}

          {latestRun && failedStepsInLatestRun.length > 0 && (
            <SectionCard cardClassName="card p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-800">Failed Steps Quick Rerun</h3>
                <span className="text-[11px] text-slate-500">Run {latestRun.run_id.slice(0, 12)}…</span>
              </div>

              <div className="space-y-2">
                {failedStepsInLatestRun.map((step) => (
                  <div key={`${latestRun.run_id}-${step.step}`} className="rounded-lg border border-red-200 bg-red-50 p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-xs font-semibold text-red-800">{stepMeta(step.step).icon} {stepMeta(step.step).label}</p>
                        <p className="text-[11px] text-red-700 mt-0.5">{step.message || 'Stage failed without explicit message.'}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          className="btn-secondary py-1.5 px-2.5 text-[11px]"
                          disabled={quickRetryStageMut.isPending || quickRetryFromHereMut.isPending}
                          onClick={() => {
                            setQuickRetryMsg(null)
                            quickRetryStageMut.mutate({ source_run_id: latestRun.run_id, step: step.step })
                          }}
                        >
                          {quickRetryStageMut.isPending && quickRetryPending?.mode === 'stage' && quickRetryPending?.step === step.step
                            ? <><Loader2 size={11} className="animate-spin" /> Queuing…</>
                            : 'Retry Stage'}
                        </button>
                        <button
                          className="btn-secondary py-1.5 px-2.5 text-[11px]"
                          disabled={quickRetryStageMut.isPending || quickRetryFromHereMut.isPending}
                          onClick={() => {
                            setQuickRetryMsg(null)
                            quickRetryFromHereMut.mutate({ source_run_id: latestRun.run_id, step: step.step })
                          }}
                        >
                          {quickRetryFromHereMut.isPending && quickRetryPending?.mode === 'from-here' && quickRetryPending?.step === step.step
                            ? <><Loader2 size={11} className="animate-spin" /> Queuing…</>
                            : 'Retry From Here'}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {quickRetryMsg && (
                <div className="mt-3 rounded border border-indigo-200 bg-indigo-50 px-2.5 py-2 text-xs text-indigo-700">
                  {quickRetryMsg}
                </div>
              )}
            </SectionCard>
          )}

          {/* Live pipeline stages */}
          <LivePipelineStatus
            runs={runs}
            onOpenRun={(runId) => {
              setFocusRunId(runId)
              setActiveCategory('history')
            }}
          />
        </>
      )}

      {activeCategory === 'history' && (
        <>
          {/* Run history */}
          <div className="px-1">
            <h2 className="text-sm font-semibold text-slate-800">Run History</h2>
            <p className="text-xs text-slate-500">Past executions with stage-level traces, reliability outcomes, and operational context.</p>
          </div>

          {isAdmin && (
            <SectionCard cardClassName="card p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-800">History Retention</p>
                  <p className="text-xs text-slate-500">Delete completed/failed/partial runs older than 30 days from persistent DB history.</p>
                </div>
                <button
                  className="btn-secondary"
                  onClick={() => cleanupHistoryMut.mutate()}
                  disabled={cleanupHistoryMut.isPending}
                  title="Clear old run history (30d+)"
                >
                  {cleanupHistoryMut.isPending
                    ? <><Loader2 size={14} className="animate-spin" /> Cleaning…</>
                    : <><RefreshCw size={14} /> Clear History (30d+)</>}
                </button>
              </div>
            </SectionCard>
          )}

          <SectionCard cardClassName="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-800">Retry Outcome Analytics</h3>
              <span className="text-[11px] text-slate-500">Derived from retry-tagged runs</span>
            </div>

            {retryAnalytics.total === 0 ? (
              <p className="text-xs text-slate-500">No retry runs recorded yet.</p>
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
                  {[
                    { label: 'Retry Runs', value: retryAnalytics.total, tone: 'text-slate-800', bg: 'bg-slate-100' },
                    { label: 'Completed', value: retryAnalytics.completed, tone: 'text-green-700', bg: 'bg-green-100' },
                    { label: 'Partial', value: retryAnalytics.partial, tone: 'text-amber-700', bg: 'bg-amber-100' },
                    { label: 'Failed', value: retryAnalytics.failed, tone: 'text-red-700', bg: 'bg-red-100' },
                    { label: 'Success %', value: `${retryAnalytics.successRate}%`, tone: retryAnalytics.successRate >= 70 ? 'text-green-700' : retryAnalytics.successRate >= 40 ? 'text-amber-700' : 'text-red-700', bg: retryAnalytics.successRate >= 70 ? 'bg-green-100' : retryAnalytics.successRate >= 40 ? 'bg-amber-100' : 'bg-red-100' },
                  ].map((item) => (
                    <div key={item.label} className="rounded-lg border border-slate-200 px-2.5 py-2 text-center bg-white">
                      <p className={`text-base font-bold ${item.tone}`}>{item.value}</p>
                      <p className="text-[10px] text-slate-500">{item.label}</p>
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-2">Stage-level retry success</p>
                    <div className="space-y-1.5">
                      {retryAnalytics.stageRows.slice(0, 4).map((row) => (
                        <div key={row.stage} className="flex items-center justify-between text-xs">
                          <span className="text-slate-700">{stepMeta(row.stage).label}</span>
                          <span className="font-semibold text-slate-800">{row.successPct}% ({row.attempts})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-2">Top failing stage</p>
                    {retryAnalytics.topFailingStage ? (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-700">{stepMeta(retryAnalytics.topFailingStage.stage).label}</span>
                        <span className="font-semibold text-red-700">{retryAnalytics.topFailingStage.count} failures</span>
                      </div>
                    ) : (
                      <p className="text-xs text-green-700">No failed stage observed in retry runs.</p>
                    )}
                    <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                      <span className="text-slate-500">Mean Time To Recover</span>
                      <span className="font-semibold text-slate-800">
                        {retryAnalytics.meanTimeToRecoverSec == null ? 'N/A' : `${retryAnalytics.meanTimeToRecoverSec}s`}
                      </span>
                    </div>
                  </div>
                </div>
              </>
            )}
          </SectionCard>

          {runs.length === 0 ? (
            <div className="card p-12 text-center">
              <Play size={36} className="text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500 font-medium">No pipeline runs yet</p>
              <p className="text-slate-400 text-sm mt-1">Click "Run Now" to execute the pipeline manually.</p>
            </div>
          ) : (
            <SectionCard
              bandTitle="Pipeline Event History"
              bandSubtitle="Enterprise ledger view for run diagnostics, failure analysis, and execution governance."
              cardClassName="card p-4"
            >
              <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
                <span>Showing {runs.length ? historyStart + 1 : 0}-{historyEnd} of {runs.length} runs</span>
                <RowsPerPageControl
                  pageSize={historyPageSize}
                  options={[5, 10, 15]}
                  onChange={(value) => {
                    setHistoryPageSize(value)
                    setHistoryPage(1)
                  }}
                />
              </div>
              <div className="space-y-3">
                {pagedRuns.map((run) => (
                  <RunCard key={run.run_id} run={run} isHighlighted={focusRunId === run.run_id} />
                ))}
              </div>
              <PaginatedSectionFooter
                page={safeHistoryPage}
                totalPages={historyTotalPages}
                onPrev={() => setHistoryPage((p) => Math.max(1, p - 1))}
                onNext={() => setHistoryPage((p) => Math.min(historyTotalPages, p + 1))}
              />
            </SectionCard>
          )}
        </>
      )}
    </div>
  )
}
