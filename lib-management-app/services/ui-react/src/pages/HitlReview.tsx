import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle, RefreshCw, Loader2,
  ChevronDown, ChevronUp, TrendingUp, TrendingDown, BookOpen, Filter,
  CheckSquare, Square, AlertTriangle, Rocket, Zap,
} from 'lucide-react'
import StatusBadge from '../components/StatusBadge'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import { RowsPerPageControl, PaginatedSectionFooter } from '../components/PaginatedSectionControls'
import { lifecycleApi, slaApi } from '../api/client'
import { useAuth } from '../context/AuthContext'
import type { Lifecycle } from '../api/types'

type HitlCategory = 'snapshot' | 'controls' | 'ledger'

interface PendingItem extends Omit<Lifecycle, 'created_at' | 'updated_at'> {
  lifecycle_id: number
  ai_recommendation?: string
  ai_summary?: string
  upgrade_pros?: string[]
  upgrade_cons?: string[]
  no_upgrade_pros?: string[]
  alert_priority?: string
  deadline_date?: string | null
  deprecation_notes?: string
  created_at?: string | undefined
  updated_at?: string | undefined
}

function confidenceScore(item: PendingItem): { score: number; band: 'High' | 'Medium' | 'Low' } {
  if (typeof item.confidence_score === 'number' && item.confidence_band) {
    return {
      score: Math.max(0, Math.min(100, item.confidence_score)),
      band: item.confidence_band,
    }
  }

  let score = 45
  const urgency = (item.update_needed ?? '').toLowerCase()

  if (['mandatory', 'critical'].includes(urgency)) score += 20
  else if (urgency === 'high') score += 14
  else if (urgency === 'moderate') score += 8

  if (item.current_version && item.latest_version && item.current_version !== item.latest_version) score += 12
  if ((item.ai_summary ?? '').trim().length >= 40) score += 10
  if ((item.upgrade_pros?.length ?? 0) > 0) score += 6
  if ((item.upgrade_cons?.length ?? 0) > 0) score += 5
  if ((item.no_upgrade_pros?.length ?? 0) > 0) score += 4
  if ((item.deprecation_notes ?? '').trim().length > 0) score += 8

  const bounded = Math.max(0, Math.min(100, score))
  if (bounded >= 75) return { score: bounded, band: 'High' }
  if (bounded >= 55) return { score: bounded, band: 'Medium' }
  return { score: bounded, band: 'Low' }
}

// ── Release notes panel ───────────────────────────────────────────────────────
function ReleaseNotes({ libId, currentVersion, latestVersion }: {
  libId: number; currentVersion?: string | null; latestVersion?: string | null
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['release-notes', libId],
    queryFn: () => slaApi.releaseNotes(libId),
  })
  const rn = data?.data as {
    release_notes?: { version: string; date?: string; notes?: string; url?: string }[]
    source?: string; notes_count?: number; error?: string | null
  } | undefined

  const notes = rn?.release_notes ?? []

  return (
    <div className="mt-3 space-y-1.5">
      <div className="flex items-center gap-2 mb-2">
        <BookOpen size={12} className="text-slate-400" />
        <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Release Notes</p>
        {currentVersion && latestVersion && (
          <span className="text-xs text-slate-400 font-mono">
            {currentVersion} → {latestVersion}
          </span>
        )}
        {rn?.source && rn.source !== 'none' && (
          <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
            Source: {rn.source}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
          <Loader2 size={12} className="animate-spin" /> Fetching release notes…
        </div>
      )}

      {!isLoading && notes.length === 0 && (
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-xs text-slate-500">
          <p className="font-medium mb-1">📭 No release notes available</p>
          <p className="text-slate-400">
            Release notes are fetched from the package registry (Maven/CocoaPods/npm).
            {rn?.error && <span className="text-red-500"> Error: {rn.error}</span>}
          </p>
          {currentVersion && latestVersion && currentVersion !== latestVersion && (
            <p className="mt-1 text-slate-500">
              Upgrading from <code className="bg-white px-1 rounded">{currentVersion}</code> →{' '}
              <code className="bg-white px-1 rounded">{latestVersion}</code>
            </p>
          )}
        </div>
      )}

      {notes.map((note, i) => (
        <div key={i} className="rounded-lg bg-white border border-slate-200 px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-xs font-bold text-primary-700 bg-primary-50 px-2 py-0.5 rounded">
              v{note.version}
            </span>
            {note.date && <span className="text-[10px] text-slate-400">{note.date}</span>}
            {note.url && (
              <a href={note.url} target="_blank" rel="noreferrer"
                className="text-[10px] text-primary-500 hover:underline ml-auto">
                Changelog ↗
              </a>
            )}
          </div>
          {note.notes && (
            <p className="text-xs text-slate-600 whitespace-pre-wrap leading-relaxed">{note.notes}</p>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Item card — Approve / Deployment Progress only ───────────────────────────
function ReviewCard({
  lc, onApprove, isBusy, selected, onSelect,
}: {
  lc: PendingItem
  onApprove: (id: number, note: string, tv: string) => void
  isBusy: boolean
  selected: boolean
  onSelect: (id: number, checked: boolean) => void
}) {
  const { isAdmin } = useAuth()
  const id = lc.lifecycle_id
  const [expanded, setExpanded] = useState(false)
  const [activeTab, setActiveTab] = useState<'ai' | 'notes'>('ai')
  const [note, setNote] = useState('')
  const [tv, setTv] = useState('')

  const isMandatory = ['mandatory','critical','high'].includes(
    (lc.alert_priority ?? '').toLowerCase()
  ) || ['mandatory','critical','high'].includes((lc.update_needed ?? '').toLowerCase()) || Boolean(lc.business_critical)
  const confidence = confidenceScore(lc)
  // Was this version updated after the lifecycle was first created? (newer version detected)
  const versionUpdated = !!(lc.updated_at && lc.created_at && lc.updated_at > lc.created_at)

  return (
    <div className={`card overflow-hidden border-l-4 ${
      isMandatory ? 'border-l-red-500' : 'border-l-green-400'
    } ${selected ? 'ring-2 ring-primary-400' : ''}`}>
      {/* ⚡ Version-override banner */}
      {versionUpdated && (
        <div className="bg-amber-50 border-b border-amber-200 px-5 py-1.5 flex items-center gap-2">
          <Zap size={12} className="text-amber-600 flex-shrink-0" />
          <p className="text-xs text-amber-700 font-medium">
            ⚡ New version detected — this approval has been updated with the latest version (previous pending version superseded)
          </p>
        </div>
      )}
      {/* Summary row */}
      <div className="px-5 py-4">
        <div className="flex flex-wrap gap-3 items-start">
          {/* Checkbox */}
          <button
            className="mt-0.5 flex-shrink-0 text-slate-400 hover:text-primary-600 transition-colors"
            onClick={() => onSelect(id, !selected)}
            title={selected ? 'Deselect' : 'Select for bulk action'}
          >
            {selected
              ? <CheckSquare size={16} className="text-primary-600" />
              : <Square size={16} />}
          </button>
          {/* Left: library info */}
          <div className="flex-1 min-w-[220px]">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <p className="font-semibold text-slate-900 text-sm">
                {lc.package ?? `SDK #${lc.library_id}`}
              </p>
              {lc.sdk_name && <span className="text-xs text-slate-400">{lc.sdk_name}</span>}
              <StatusBadge status={lc.platform ?? 'unknown'} size="sm" />
            </div>

            {/* Version banner */}
            {lc.current_version === lc.latest_version ? (
              <div className="flex items-center gap-2 my-1.5">
                <span className="font-mono text-sm font-bold text-slate-700">{lc.current_version ?? '?'}</span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-700">🗑 Deprecated — migrate</span>
                {lc.update_needed && <StatusBadge status={lc.update_needed} size="sm" />}
              </div>
            ) : (
              <div className="flex items-center gap-2 my-1.5">
                <span className="font-mono text-sm font-bold text-slate-700">{lc.current_version ?? '?'}</span>
                <span className="text-slate-400">→</span>
                <span className="font-mono text-sm font-bold text-green-700">{lc.latest_version ?? '?'}</span>
                {lc.update_needed && <StatusBadge status={lc.update_needed} size="sm" />}
              </div>
            )}

            {/* AI summary line */}
            {lc.ai_summary && (
              <p className="text-xs text-slate-600 mt-1 line-clamp-2">
                🤖 {lc.ai_summary}
              </p>
            )}

            <div className="mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold border bg-white border-slate-200 text-slate-700">
              Confidence {confidence.score}% · {confidence.band}
            </div>

            {/* Deadline warning */}
            {lc.deadline_date && (
              <p className="text-xs text-red-600 mt-1 font-medium">
                ⏰ Deadline: {lc.deadline_date}
              </p>
            )}
          </div>

          {/* Right: action panel */}
          <div className="flex flex-col gap-2 min-w-[260px]">
            <input
              className="input text-xs font-mono"
              placeholder={`Target version (e.g. ${lc.latest_version ?? 'x.y.z'})`}
              value={tv}
              onChange={(e) => setTv(e.target.value)}
            />
            <textarea
              className="input text-xs resize-none h-14"
              placeholder="Decision notes / reason (optional)…"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2.5">
              <p className="text-[11px] text-blue-600 font-semibold mb-2 flex items-center gap-1">
                <Rocket size={11} /> Approval / Deployment Progress
              </p>
              {isAdmin ? (
                <button
                  className="btn-primary w-full justify-center py-2 text-xs font-semibold"
                  onClick={() => onApprove(id, note, tv)}
                  disabled={isBusy}
                  title="Approve this upgrade and send to deployment pipeline"
                >
                  {isBusy
                    ? <><Loader2 size={12} className="animate-spin" /> Processing…</>
                    : <><CheckCircle size={13} /> Approve / In Deployment</>}
                </button>
              ) : (
                <p className="text-[11px] text-slate-400 text-center py-1">👁 View only — admin approval required</p>
              )}
            </div>
          </div>
        </div>

        {/* Expand toggle */}
        <button
          className="mt-2 flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
          onClick={() => setExpanded((p) => !p)}
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Hide details' : 'Show AI analysis & release notes'}
        </button>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50/50 px-5 pb-5">
          {/* Tabs */}
          <div className="flex gap-0 mt-3 mb-3 border-b border-slate-200">
            {(['ai', 'notes'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors -mb-px ${
                  activeTab === tab
                    ? 'border-primary-600 text-primary-700'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {tab === 'ai' ? '🤖 AI Analysis' : '📰 Release Notes'}
              </button>
            ))}
          </div>

          {activeTab === 'ai' && (
            <div className="space-y-3">
              {/* AI recommendation decision */}
              {lc.ai_recommendation && (
                <div className={`rounded-lg px-4 py-3 border ${
                  lc.ai_recommendation === 'Yes'
                    ? 'bg-green-50 border-green-200'
                    : 'bg-amber-50 border-amber-200'
                }`}>
                  <p className={`text-xs font-bold mb-1 ${
                    lc.ai_recommendation === 'Yes' ? 'text-green-700' : 'text-amber-700'
                  }`}>
                    {lc.ai_recommendation === 'Yes' ? '✅ AI Recommends Upgrade' : '⚠️ AI Does NOT Recommend Upgrade'}
                  </p>
                  {lc.ai_summary && (
                    <p className="text-xs text-slate-700">{lc.ai_summary}</p>
                  )}
                </div>
              )}

              {/* Deprecation notes */}
              {lc.deprecation_notes && (
                <div className="rounded-lg px-4 py-3 border border-red-200 bg-red-50">
                  <p className="text-xs font-semibold text-red-700 mb-1">⛔ Deprecation Notes</p>
                  <p className="text-xs text-red-800">{lc.deprecation_notes}</p>
                </div>
              )}

              {/* Pros / Cons grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {lc.upgrade_pros && lc.upgrade_pros.length > 0 && (
                  <div className="rounded-lg bg-white border border-green-200 p-3">
                    <p className="text-xs font-semibold text-green-700 flex items-center gap-1 mb-2">
                      <TrendingUp size={11} /> Pros of Upgrading
                    </p>
                    <ul className="text-xs text-slate-700 space-y-1">
                      {lc.upgrade_pros.map((p, i) => (
                        <li key={i} className="flex gap-1.5">
                          <span className="text-green-500 flex-shrink-0">✓</span>{p}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {lc.upgrade_cons && lc.upgrade_cons.length > 0 && (
                  <div className="rounded-lg bg-white border border-red-200 p-3">
                    <p className="text-xs font-semibold text-red-700 flex items-center gap-1 mb-2">
                      <TrendingDown size={11} /> Cons of Upgrading
                    </p>
                    <ul className="text-xs text-slate-700 space-y-1">
                      {lc.upgrade_cons.map((c, i) => (
                        <li key={i} className="flex gap-1.5">
                          <span className="text-red-400 flex-shrink-0">✗</span>{c}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {lc.no_upgrade_pros && lc.no_upgrade_pros.length > 0 && (
                  <div className="rounded-lg bg-white border border-slate-200 p-3 md:col-span-2">
                    <p className="text-xs font-semibold text-slate-600 mb-2">
                      💡 Pros of Staying on Current Version
                    </p>
                    <ul className="text-xs text-slate-600 space-y-1">
                      {lc.no_upgrade_pros.map((p, i) => (
                        <li key={i} className="flex gap-1.5">
                          <span className="text-slate-400 flex-shrink-0">•</span>{p}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'notes' && (
            <ReleaseNotes
              libId={lc.library_id}
              currentVersion={lc.current_version}
              latestVersion={lc.latest_version}
            />
          )}
        </div>
      )}
    </div>
  )
}

// ── Main HITL Review page ─────────────────────────────────────────────────────
export default function HitlReview() {
  const qc = useQueryClient()
  const { isAdmin } = useAuth()
  const [actionMsg, setActionMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [filterPriority, setFilterPriority] = useState('mandatory')
  const [filterPlatform, setFilterPlatform] = useState('all')
  const [filterConfidence, setFilterConfidence] = useState('all')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkNote, setBulkNote] = useState('')
  const [bulkInProgress, setBulkInProgress] = useState(false)
  const [queuePage, setQueuePage] = useState(1)
  const [queuePageSize, setQueuePageSize] = useState(6)
  const [activeCategory, setActiveCategory] = useState<HitlCategory>('ledger')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['hitl-pending-full'],
    queryFn: () => lifecycleApi.pendingReview(),
  })
  const pending: PendingItem[] = Array.isArray(data?.data) ? (data!.data as PendingItem[]) : []

  const filtered = useMemo(() => pending.filter((lc) => {
    const un = (lc.update_needed ?? '').toLowerCase()
    // Default: show critical + high + mandatory (legacy) items needing approval
    const matchP  = filterPriority === 'all'
      || (filterPriority === 'mandatory' && ['mandatory','critical','high'].includes(un))
      || un === filterPriority
    const matchPl = filterPlatform === 'all' || (lc.platform ?? '').toLowerCase() === filterPlatform
    const conf = confidenceScore(lc).score
    const matchC = filterConfidence === 'all'
      || (filterConfidence === 'high' && conf >= 75)
      || (filterConfidence === 'medium' && conf >= 55 && conf < 75)
      || (filterConfidence === 'low' && conf < 55)
    return matchP && matchPl && matchC
  }), [pending, filterPriority, filterPlatform, filterConfidence])

  const queueTotalPages = Math.max(1, Math.ceil(filtered.length / queuePageSize))
  const safeQueuePage = Math.min(queuePage, queueTotalPages)
  const queueStart = (safeQueuePage - 1) * queuePageSize
  const queueEnd = Math.min(queueStart + queuePageSize, filtered.length)
  const pagedFiltered = filtered.slice(queueStart, queueEnd)

  useEffect(() => {
    setQueuePage(1)
  }, [filterPriority, filterPlatform, filterConfidence, queuePageSize])

  useEffect(() => {
    if (queuePage > queueTotalPages) setQueuePage(queueTotalPages)
  }, [queuePage, queueTotalPages])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['hitl-pending-full'] })
    qc.invalidateQueries({ queryKey: ['hitl-pending'] })
    qc.invalidateQueries({ queryKey: ['lifecycle-pending'] })
    qc.invalidateQueries({ queryKey: ['libraries'] })
  }

  const approveMut = useMutation({
    mutationFn: ({ id, note, tv }: { id: number; note: string; tv: string }) =>
      lifecycleApi.update(id, {
        status: 'Acknowledged',
        actioned_by: 'admin',
        ...(note && { skip_reason: note }),
        ...(tv   && { target_version: tv }),
      }),
    onSuccess: () => { setActionMsg({ text: '✅ Approved — upgrade acknowledged & queued for deployment', ok: true }); invalidate() },
    onError:   () => setActionMsg({ text: '❌ Approve failed — please try again', ok: false }),
  })

  const isBusy = approveMut.isPending || bulkInProgress

  // ── Selection helpers ──────────────────────────────────────────────────────
  const toggleSelect = (id: number, checked: boolean) =>
    setSelectedIds((prev) => { const s = new Set(prev); checked ? s.add(id) : s.delete(id); return s })

  const selectAll  = () => setSelectedIds(new Set(filtered.map(l => l.lifecycle_id)))
  const selectNone = () => setSelectedIds(new Set())
  const allSelected = filtered.length > 0 && filtered.every(l => selectedIds.has(l.lifecycle_id))
  const someSelected = selectedIds.size > 0

  // ── Bulk approve only ──────────────────────────────────────────
  const runBulkApprove = async () => {
    const ids = [...selectedIds]
    if (ids.length === 0) return
    setBulkInProgress(true)
    setActionMsg(null)
    let ok = 0; let fail = 0
    await Promise.allSettled(
      ids.map((id) =>
        lifecycleApi.update(id, {
          status: 'Acknowledged',
          actioned_by: 'admin',
          ...(bulkNote && { skip_reason: bulkNote }),
        })
      )
    ).then((results) => results.forEach((r) => r.status === 'fulfilled' ? ok++ : fail++))
    setBulkInProgress(false)
    setSelectedIds(new Set())
    setBulkNote('')
    setActionMsg({ text: `✅ Bulk Approved: ${ok} queued for deployment${fail ? `, ${fail} failed` : ''}`, ok: fail === 0 })
    invalidate()
  }

  // Stats — include new priority values
  const _hun = (l: PendingItem) => (l.update_needed ?? '').toLowerCase()
  const mandatory      = pending.filter(l => ['mandatory','critical','high'].includes(_hun(l))).length
  const versionUpdated = pending.filter(l => l.updated_at && l.created_at && l.updated_at > l.created_at).length
  const androidPending = pending.filter((l) => (l.platform ?? '').toLowerCase() === 'android').length
  const iosPending = pending.filter((l) => (l.platform ?? '').toLowerCase() === 'ios').length



  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Approval Queue</h1>
          <p className="page-subtitle">
            Approval / Deployment Progress — {mandatory} mandatory upgrade{mandatory !== 1 ? 's' : ''} pending
            {versionUpdated > 0 && <span className="ml-2 text-amber-600 font-semibold">⚡ {versionUpdated} version updated</span>}
            <span className="ml-2 text-slate-400 font-normal text-xs">({pending.length} total in queue, showing mandatory)</span>
          </p>
        </div>
        <button className="btn-secondary" onClick={() => refetch()} disabled={isLoading}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Workflow info banner */}
      <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 flex items-start gap-3">
        <Rocket size={15} className="text-blue-600 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-blue-700">
          <p className="font-semibold mb-0.5">Approval / Deployment Workflow</p>
          <p className="text-blue-600 leading-relaxed">
            Each item requires your approval before the upgrade enters the deployment pipeline.
            If the pipeline detects a newer version before you approve, the item is automatically
            updated to show the latest version (⚡ version updated badge). Approved items reappear
            only when a newer version is released.
          </p>
        </div>
      </div>

      <SectionCard cardClassName="card p-4">
        <SectionBand
          title="Approval Queue Category Navigator"
          subtitle="Switch between summary, controls, and ledger views to reduce long-scroll review fatigue."
          className="mb-3"
        />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {[
            { key: 'snapshot' as const, label: 'Governance Snapshot' },
            { key: 'controls' as const, label: 'Queue Controls' },
            { key: 'ledger' as const, label: 'Approval Ledger' },
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

      {activeCategory === 'snapshot' && <SectionBand
        title="Approval Governance Snapshot"
        subtitle="Business-critical queue posture and deployment readiness by platform."
      />}

      {activeCategory === 'snapshot' && <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="card p-4 text-center border border-amber-200 bg-amber-50">
          <p className="text-2xl font-bold text-amber-700">{mandatory}</p>
          <p className="text-xs text-amber-700 mt-1">Critical + High Queue</p>
        </div>
        <div className="card p-4 text-center border border-slate-200 bg-slate-50">
          <p className="text-2xl font-bold text-slate-800">{pending.length}</p>
          <p className="text-xs text-slate-600 mt-1">Total Pending Items</p>
        </div>
        <div className="card p-4 text-center border border-green-200 bg-green-50">
          <p className="text-2xl font-bold text-green-700">{androidPending}</p>
          <p className="text-xs text-green-700 mt-1">Android Queue</p>
        </div>
        <div className="card p-4 text-center border border-sky-200 bg-sky-50">
          <p className="text-2xl font-bold text-sky-700">{iosPending}</p>
          <p className="text-xs text-sky-700 mt-1">iOS Queue</p>
        </div>
      </div>}

      {/* Action feedback */}
      {activeCategory !== 'snapshot' && actionMsg && (
        <div className={`px-4 py-3 rounded-lg text-sm flex justify-between items-center border ${
          actionMsg.ok
            ? 'bg-green-50 border-green-200 text-green-700'
            : 'bg-red-50 border-red-200 text-red-700'
        }`}>
          {actionMsg.text}
          <button onClick={() => setActionMsg(null)} className="text-xs opacity-60 hover:opacity-100 ml-4">✕</button>
        </div>
      )}

      {/* Filter bar */}
      {activeCategory === 'controls' && pending.length > 0 && (
        <div className="card p-3 flex flex-wrap gap-3 items-center">
          {/* Select all checkbox */}
          <button
            className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-primary-700 transition-colors"
            onClick={allSelected ? selectNone : selectAll}
            title={allSelected ? 'Deselect all' : 'Select all visible'}
          >
            {allSelected
              ? <CheckSquare size={14} className="text-primary-600" />
              : <Square size={14} />}
            {allSelected ? 'Deselect all' : 'Select all'}
          </button>
          <div className="w-px h-4 bg-slate-200" />
          <Filter size={13} className="text-slate-400" />
          <select className="select w-auto text-xs"
            value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)}>
            <option value="all">All</option>
            <option value="mandatory">🔴 Critical + High</option>
            <option value="critical">🔴 Critical only</option>
            <option value="high">🟠 High only</option>
            <option value="moderate">🟡 Moderate</option>
            <option value="low">🔵 Low</option>
          </select>
          <select className="select w-auto text-xs"
            value={filterPlatform} onChange={(e) => setFilterPlatform(e.target.value)}>
            <option value="all">All platforms</option>
            <option value="android">Android</option>
            <option value="ios">iOS</option>
          </select>
          <select className="select w-auto text-xs"
            value={filterConfidence} onChange={(e) => setFilterConfidence(e.target.value)}>
            <option value="all">All confidence</option>
            <option value="high">High (≥75)</option>
            <option value="medium">Medium (55-74)</option>
            <option value="low">Low (&lt;55)</option>
          </select>
          <span className="text-xs text-slate-400 ml-auto">
            {someSelected && <span className="text-primary-600 font-semibold mr-2">{selectedIds.size} selected</span>}
            Showing {filtered.length} of {pending.length}
          </span>
        </div>
      )}

      {/* Bulk action bar — Approve only */}
      {activeCategory === 'controls' && someSelected && (
        <div className="card p-3 border-2 border-primary-300 bg-primary-50">
          <div className="flex flex-wrap gap-3 items-center">
            <Rocket size={14} className="text-primary-600 flex-shrink-0" />
            <span className="text-sm font-semibold text-primary-800">
              {selectedIds.size} item{selectedIds.size > 1 ? 's' : ''} selected for approval
            </span>
            <input
              className="input text-xs flex-1 min-w-[200px] max-w-xs"
              placeholder="Deployment notes / sprint reference (optional)"
              value={bulkNote}
              onChange={(e) => setBulkNote(e.target.value)}
            />
            <div className="flex gap-2 flex-wrap">
              {isAdmin && (
                <button
                  className="btn-primary py-1.5 px-4 text-xs font-semibold"
                  onClick={runBulkApprove}
                  disabled={bulkInProgress}
                  title="Approve all selected upgrades for deployment"
                >
                  {bulkInProgress
                    ? <><Loader2 size={12} className="animate-spin" /> Processing…</>
                    : <><CheckCircle size={12} /> Approve All ({selectedIds.size}) / In Deployment</>}
                </button>
              )}
              <button
                className="btn-secondary py-1.5 px-2 text-xs"
                onClick={selectNone}
                disabled={bulkInProgress}
              >
                ✕ Clear
              </button>
            </div>
          </div>
          {bulkInProgress && (
            <div className="mt-2 flex items-center gap-2 text-xs text-primary-700">
              <Loader2 size={12} className="animate-spin" />
              Processing {selectedIds.size} items…
            </div>
          )}
        </div>
      )}

      {/* Content */}
      {activeCategory === 'ledger' && (isLoading ? (
        <div className="card p-8 text-center">
          <Loader2 size={24} className="animate-spin text-slate-400 mx-auto mb-2" />
          <p className="text-slate-400 text-sm">Loading pending reviews…</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-12 text-center">
          <CheckCircle size={40} className="text-green-400 mx-auto mb-3" />
          <p className="text-slate-600 font-medium text-lg">
            {pending.length === 0 ? 'All approvals done! No pending items.' : 'No items match your filters.'}
          </p>
          <p className="text-slate-400 text-sm mt-1">
            {pending.length === 0
              ? 'Run the pipeline to generate new approval items when new versions are detected.'
              : 'Try changing the filter options above.'}
          </p>
        </div>
      ) : (
        <SectionCard
          bandTitle="Approval Queue Ledger"
          bandSubtitle="Paginated enterprise queue to reduce scroll fatigue and improve decision throughput."
          cardClassName="card p-4"
        >
          <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
            <span>Showing {filtered.length ? queueStart + 1 : 0}-{queueEnd} of {filtered.length}</span>
            <RowsPerPageControl
              pageSize={queuePageSize}
              options={[6, 10, 15]}
              onChange={(value) => {
                setQueuePageSize(value)
                setQueuePage(1)
              }}
            />
          </div>
          <div className="space-y-3">
            {pagedFiltered.map((lc) => (
              <ReviewCard
                key={lc.lifecycle_id}
                lc={lc}
                onApprove={(id, note, tv) => approveMut.mutate({ id, note, tv })}
                isBusy={isBusy}
                selected={selectedIds.has(lc.lifecycle_id)}
                onSelect={toggleSelect}
              />
            ))}
          </div>
          <PaginatedSectionFooter
            page={safeQueuePage}
            totalPages={queueTotalPages}
            onPrev={() => setQueuePage((p) => Math.max(1, p - 1))}
            onNext={() => setQueuePage((p) => Math.min(queueTotalPages, p + 1))}
          />
        </SectionCard>
      ))}
    </div>
  )
}
