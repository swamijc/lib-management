import { useState, useMemo, useRef, useEffect, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, Filter, ChevronDown, ChevronUp, ExternalLink, X, RefreshCw, Loader2, Tag, Link2, BookOpen, Plus, Trash2, Download, ArrowUpDown, ArrowUp, ArrowDown, Pencil, Power, GitMerge, CheckCircle2, Clock, Rocket, MessageSquare, Bot, Send, Sparkles } from 'lucide-react'
import StatusBadge from '../components/StatusBadge'
import ExecutiveTriad from '../components/ExecutiveTriad'
import { PaginatedSectionFooter, PaginatedSectionHeader } from '../components/PaginatedSectionControls'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import { libraryApi, lifecycleApi, parseApiError, recApi } from '../api/client'
import { useAuth } from '../context/AuthContext'
import type { Library, Recommendation, RecommendationChatRequest, RecommendationChatResult, RecommendationChatTurn } from '../api/types'
import { pickLatestLifecycleByLibrary } from '../utils/lifecycleSelection'

const PLATFORMS: ('Android' | 'iOS')[] = ['Android', 'iOS']
const PRIORITIES = ['All', 'critical', 'high', 'moderate', 'low', 'none', 'mandatory']

// ── Platform SVG icons ────────────────────────────────────────────────────────
function AndroidIcon({ size = 22, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M6.18 15.64a2.18 2.18 0 0 1-2.18-2.18V9.77a2.18 2.18 0 0 1 4.36 0v3.69a2.18 2.18 0 0 1-2.18 2.18M17.82 15.64a2.18 2.18 0 0 1-2.18-2.18V9.77a2.18 2.18 0 0 1 4.36 0v3.69a2.18 2.18 0 0 1-2.18 2.18M5.26 4.07 3.35 2.16l1.24-1.24 2.21 2.21A8.37 8.37 0 0 1 12 2c1.33 0 2.58.3 3.7.83l2.2-2.2 1.24 1.24-1.9 1.9A7.92 7.92 0 0 1 20 9H4a7.92 7.92 0 0 1 1.26-4.93M9 6.5a.5.5 0 1 0 0-1 .5.5 0 0 0 0 1m6 0a.5.5 0 1 0 0-1 .5.5 0 0 0 0 1M4 10v7a2 2 0 0 0 2 2h.5v3.5a1.5 1.5 0 0 0 3 0V19h5v3.5a1.5 1.5 0 0 0 3 0V19H18a2 2 0 0 0 2-2v-7H4z" />
    </svg>
  )
}

function AppleIcon({ size = 22, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
    </svg>
  )
}

function buildWhyNotes(lib: Library): string {
  const parts: string[] = []
  if (lib.deprecation_notes) parts.push(`⛔ ${lib.deprecation_notes}`)
  if (lib.comments) parts.push(`💬 ${lib.comments}`)
  if (lib.deadline_notes) parts.push(`📅 ${lib.deadline_notes}`)
  return parts.join(' | ') || '—'
}

type AssistChatMessage = {
  role: 'user' | 'assistant'
  text: string
}

type AssistUsage = {
  calls: number
  promptTokens: number
  completionTokens: number
  totalTokens: number
  lastModel: string | null
  lastLatencyMs: number | null
}

// ── Lifecycle Review Panel (inline per-library upgrade queue) ────────────────
const LC_STATUS_META: Record<string, { label: string; color: string }> = {
  awaiting_review: { label: 'Awaiting Review', color: 'bg-amber-100 text-amber-700 border-amber-300' },
  Acknowledged:    { label: 'Acknowledged',    color: 'bg-blue-100 text-blue-700 border-blue-300' },
  'In Progress':   { label: 'In Progress',     color: 'bg-indigo-100 text-indigo-700 border-indigo-300' },
  Scheduled:       { label: 'Scheduled',       color: 'bg-purple-100 text-purple-700 border-purple-300' },
  Completed:       { label: 'Completed ✓',     color: 'bg-green-100 text-green-700 border-green-300' },
  Skipped:         { label: 'Skipped',         color: 'bg-slate-100 text-slate-500 border-slate-300' },
  Pending:         { label: 'Pending',         color: 'bg-yellow-100 text-yellow-700 border-yellow-300' },
}

function LifecycleReviewPanel({ libId, latestVersion, currentVersion, suggestedVersion, onActiveSet, onDecline }: {
  libId: number
  latestVersion?: string | null
  currentVersion?: string | null
  suggestedVersion?: string | null
  onActiveSet?: () => void
  onDecline?: () => void
}) {
  const { isAdmin, user } = useAuth()
  const qc = useQueryClient()
  const username = user?.username ?? 'admin'

  const { data: lcData, isLoading: lcLoading } = useQuery({
    queryKey: ['lc-by-lib', libId],
    queryFn: () => lifecycleApi.get(libId),
    staleTime: 0,
  })

  type LcRecord = {
    id: number; status: string; target_version?: string | null
    completed_version?: string | null; actioned_by?: string | null
    updated_at?: string | null
  }
  const lc = lcData?.data as LcRecord | null | undefined
  // Normalise: DB stores 'Pending' for the initial state; UI calls it 'awaiting_review'
  const lcStatus = lc ? (lc.status === 'Pending' ? 'awaiting_review' : lc.status) : null
  const normalizedSuggested = (suggestedVersion ?? '').trim()
  const normalizedLifecycleTarget = (lc?.target_version ?? '').trim()
  const targetChangedWhileInProgress =
    lcStatus === 'In Progress'
    && normalizedSuggested.length > 0
    && normalizedLifecycleTarget.length > 0
    && normalizedSuggested !== normalizedLifecycleTarget

  // Target version is already the installed current version — review should be completable in one click
  const targetAlreadyInstalled =
    !!lc?.target_version
    && !!currentVersion
    && lc.target_version.trim() === currentVersion.trim()

  const [comment, setComment]         = useState('')
  const [commentErr, setCommentErr]   = useState('')
  const [targetVer, setTargetVer]     = useState(suggestedVersion ?? '')
  const [ipComment, setIpComment]     = useState('')
  const [ipCommentErr, setIpCommentErr] = useState('')
  const [actionMsg, setActionMsg]     = useState<{ text: string; ok: boolean } | null>(null)

  // Keep targetVer in sync if suggestedVersion changes (user picks different version)
  // Also reset all form state so stale messages from previous version selection are cleared
  useEffect(() => {
    if (suggestedVersion) {
      setTargetVer(suggestedVersion)
      setComment('')
      setCommentErr('')
      setIpComment('')
      setIpCommentErr('')
      setActionMsg(null)
    }
  }, [suggestedVersion])

  const invalidate = () => {
    qc.refetchQueries({ queryKey: ['libraries'] })
    qc.refetchQueries({ queryKey: ['lifecycle-list-all'] })
    qc.refetchQueries({ queryKey: ['lc-by-lib', libId] })
    qc.invalidateQueries({ queryKey: ['hitl-pending-full'] })
    qc.invalidateQueries({ queryKey: ['lifecycle-pending'] })
  }

  // Start / reset review (only triggered when user selects a version on a completed lifecycle)
  const initMut = useMutation({
    mutationFn: () => lifecycleApi.init({ library_id: libId, actioned_by: username }),
    onSuccess: () => { setActionMsg({ text: '✅ Review started', ok: true }); invalidate() },
    onError: (e) => setActionMsg({ text: `❌ ${parseApiError(e)}`, ok: false }),
  })

  // Acknowledge
  const ackMut = useMutation({
    mutationFn: (id: number) =>
      lifecycleApi.update(id, { status: 'Acknowledged', actioned_by: username }),
    onSuccess: () => { setActionMsg({ text: '✅ Acknowledged', ok: true }); invalidate() },
    onError: (e) => setActionMsg({ text: `❌ ${parseApiError(e)}`, ok: false }),
  })

  // Mark In Progress
  const inProgressMut = useMutation({
    mutationFn: ({ id, cmt, targetVer }: { id: number; cmt: string; targetVer?: string }) =>
      lifecycleApi.markInProgress(id, {
        status: 'In Progress',
        actioned_by: username,
        skip_reason: cmt,
        ...(targetVer ? { target_version: targetVer } : {}),
      }),
    onSuccess: () => { setActionMsg({ text: '✅ Marked In Progress', ok: true }); setIpComment(''); setIpCommentErr(''); invalidate() },
    onError: (e) => setActionMsg({ text: `❌ ${parseApiError(e)}`, ok: false }),
  })

  // Decline In Progress — dedicated endpoint validates In Progress state, clears target_version
  const declineMut = useMutation({
    mutationFn: (id: number) => lifecycleApi.decline(id, { actioned_by: username }),
    onSuccess: () => {
      setActionMsg({ text: '↩ Upgrade declined — moved back to Acknowledged', ok: true })
      setTargetVer('')
      setComment('')
      onDecline?.()
      invalidate()
    },
    onError: (e) => setActionMsg({ text: `❌ ${parseApiError(e)}`, ok: false }),
  })

  // Set Active (mandatory comment)
  const setActiveMut = useMutation({
    mutationFn: ({ id, ver, cmt }: { id: number; ver: string; cmt: string }) =>
      lifecycleApi.setActive(id, { target_version: ver, comment: cmt, actioned_by: username }),
    onSuccess: () => {
      setComment(''); setTargetVer(''); setCommentErr('')
      qc.invalidateQueries({ queryKey: ['recommendations'] })
      invalidate()
      onActiveSet?.()
    },
    onError: (e) => setActionMsg({ text: `❌ ${parseApiError(e)}`, ok: false }),
  })

  const handleSetActive = (id: number) => {
    setCommentErr('')
    const ver = targetVer.trim() || latestVersion || ''
    if (!comment.trim()) { setCommentErr('Comment is required to set a version as Active'); return }
    if (!ver) { setCommentErr('Target version is required'); return }
    if (lcStatus === 'In Progress' && lc?.target_version && ver !== lc.target_version) {
      setCommentErr('Target version changed. Wait for reset to Awaiting Review, then Acknowledge and mark In Progress again.')
      return
    }
    setActiveMut.mutate({ id, ver, cmt: comment.trim() })
  }

  if (lcLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
        <Loader2 size={12} className="animate-spin" /> Loading upgrade review…
      </div>
    )
  }

  const statusMeta = lc ? (LC_STATUS_META[lcStatus!] ?? { label: lcStatus ?? lc.status, color: 'bg-slate-100 text-slate-600 border-slate-200' }) : null
  const isDone = lcStatus === 'Completed' || lcStatus === 'Skipped'

  return (
    <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/60">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <GitMerge size={13} className="text-primary-600" />
          <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Upgrade Review Queue</p>
        </div>
        {statusMeta && (
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${statusMeta.color}`}>
            {statusMeta.label}
          </span>
        )}
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Feedback message */}
        {actionMsg && (
          <div className={`px-3 py-2 rounded-lg text-xs border ${
            actionMsg.ok ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'
          }`}>
            {actionMsg.text}
          </div>
        )}

        {/* No lifecycle yet — read-only message */}
        {!lc && (
          <p className="text-xs text-slate-400 italic">No upgrade review record. Select a version from Version History to begin.</p>
        )}

        {/* Completed / Skipped — show summary; if user selected a new version, offer to start a new review */}
        {lc && isDone && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-3 text-xs text-slate-600">
              {lc.completed_version && (
                <span>Completed version: <code className="font-mono bg-white px-1 rounded border border-slate-200">{lc.completed_version}</code></span>
              )}
              {lc.actioned_by && <span>By: <strong>{lc.actioned_by}</strong></span>}
              {lc.updated_at && <span className="text-slate-400">{new Date(lc.updated_at).toLocaleDateString()}</span>}
            </div>
            {isAdmin && suggestedVersion && (
              <button
                className="btn-primary py-1.5 text-xs"
                onClick={() => { setActionMsg(null); initMut.mutate() }}
                disabled={initMut.isPending}
              >
                {initMut.isPending
                  ? <><Loader2 size={11} className="animate-spin" /> Starting…</>
                  : <><Rocket size={11} /> Start Review for v{suggestedVersion}</>}
              </button>
            )}
          </div>
        )}

        {/* Active workflow — Pending/awaiting_review / Acknowledged / In Progress */}
        {lc && !isDone && (
          <div className="space-y-3">

            {/* Already-installed escape hatch — target version is already the current version */}
            {targetAlreadyInstalled && isAdmin && (
              <div className="rounded-lg border border-green-300 bg-green-50 p-3 space-y-2">
                <p className="text-[11px] font-semibold text-green-700 flex items-center gap-1.5">
                  <CheckCircle2 size={13} /> Version Already Installed
                </p>
                <p className="text-[11px] text-green-700 leading-relaxed">
                  <strong>v{lc.target_version}</strong> is already the current installed version.
                  You can complete this review immediately — no deployment needed.
                </p>
                <button
                  className="btn-primary w-full justify-center py-2 text-xs font-semibold"
                  disabled={setActiveMut.isPending}
                  onClick={() => {
                    setActiveMut.mutate({
                      id: lc.id,
                      ver: lc.target_version!,
                      cmt: `Version ${lc.target_version} was already installed as current version — review closed automatically.`,
                    })
                  }}
                >
                  {setActiveMut.isPending
                    ? <><Loader2 size={12} className="animate-spin" /> Completing…</>
                    : <><CheckCircle2 size={12} /> Complete Review — Already Installed</>}
                </button>
              </div>
            )}

            {/* Step indicators */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {(['awaiting_review', 'Acknowledged', 'In Progress', 'Completed'] as const).map((step, i) => {
                const steps = ['awaiting_review', 'Acknowledged', 'In Progress', 'Completed']
                const currentIdx = steps.indexOf(lcStatus!)
                const stepIdx = i
                const done = stepIdx < currentIdx
                const active = step === lcStatus
                return (
                  <Fragment key={step}>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${
                      active  ? 'bg-primary-100 text-primary-700 border-primary-300' :
                      done    ? 'bg-green-100 text-green-600 border-green-200' :
                      'bg-white text-slate-400 border-slate-200'
                    }`}>
                      {done && '✓ '}{LC_STATUS_META[step]?.label ?? step}
                    </span>
                    {i < 3 && <span className="text-slate-300 text-[10px]">›</span>}
                  </Fragment>
                )
              })}
            </div>

            {/* Acknowledge button */}
            {lcStatus === 'awaiting_review' && isAdmin && (
              <button
                className="btn-secondary py-1.5 text-xs"
                onClick={() => { setActionMsg(null); ackMut.mutate(lc.id) }}
                disabled={ackMut.isPending}
              >
                {ackMut.isPending
                  ? <><Loader2 size={11} className="animate-spin" /> Acknowledging…</>
                  : <><CheckCircle2 size={11} /> Acknowledge</>}
              </button>
            )}

            {/* Mark In Progress — mandatory comment */}
            {lcStatus === 'Acknowledged' && isAdmin && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 space-y-2">
                <p className="text-[11px] font-semibold text-blue-700 flex items-center gap-1">
                  <Clock size={11} /> Mark In Progress
                </p>
                <p className="text-[10px] text-blue-600 leading-relaxed">
                  Confirm the upgrade has been assigned and work has started. Include the team/engineer handling it, target sprint or timeline, and any known blockers or dependencies.
                </p>
                <textarea
                  className={`input text-xs resize-none h-20 w-full ${
                    ipCommentErr ? 'border-red-400 bg-red-50' : ''
                  }`}
                  placeholder="e.g. Assigned to iOS Platform team — targeting Sprint 42 (2026-07-15). Dependency on XCTest compatibility check in CI. No breaking API changes expected based on release notes review."
                  value={ipComment}
                  onChange={(e) => { setIpComment(e.target.value); setIpCommentErr('') }}
                />
                {ipCommentErr && (
                  <p className="text-[10px] text-red-600">{ipCommentErr}</p>
                )}
                <button
                  className="btn-secondary w-full justify-center py-2 text-xs font-semibold"
                  onClick={() => {
                    if (!ipComment.trim()) { setIpCommentErr('Comment is required to mark as In Progress'); return }
                    setActionMsg(null)
                    inProgressMut.mutate({ id: lc.id, cmt: ipComment.trim(), targetVer: targetVer.trim() || suggestedVersion || undefined })
                  }}
                  disabled={inProgressMut.isPending}
                >
                  {inProgressMut.isPending
                    ? <><Loader2 size={11} className="animate-spin" /> Updating…</>
                    : <><Clock size={11} /> Mark In Progress</>}
                </button>
              </div>
            )}

            {targetChangedWhileInProgress && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-1">
                <p className="text-[11px] font-semibold text-amber-700">Version re-selection detected</p>
                <p className="text-[11px] text-amber-700">
                  A different target version was selected. Upgrade review is being reset to Awaiting Review to enforce re-acknowledgement.
                </p>
              </div>
            )}

            {/* Set Active — mandatory comment, only allowed after In Progress */}
            {lcStatus === 'In Progress' && isAdmin && !targetChangedWhileInProgress && (
              <div className="rounded-lg border border-green-200 bg-green-50 p-3 space-y-2">
                <p className="text-[11px] font-semibold text-green-700 flex items-center gap-1">
                  <Rocket size={11} /> Set Version as Active
                </p>
                <p className="text-[10px] text-green-700 leading-relaxed">
                  Confirm the upgraded version has been validated and is live in production. Provide evidence of testing, sign-off authority, and deployment reference for audit trail.
                </p>
                <input
                  className="input text-xs font-mono w-full"
                  placeholder={`Version to activate (e.g. ${latestVersion ?? lc.target_version ?? 'x.y.z'})`}
                  value={targetVer}
                  onChange={(e) => { setTargetVer(e.target.value); setCommentErr('') }}
                />
                <textarea
                  className={`input text-xs resize-none h-20 w-full ${
                    commentErr ? 'border-red-400 bg-red-50' : ''
                  }`}
                  placeholder="e.g. Upgraded to v2.10.0 — regression suite passed (100% green), signed off by @tech-lead. Deployed to production on 2026-07-01 via PR #4821. No issues reported in 24 h smoke monitoring."
                  value={comment}
                  onChange={(e) => { setComment(e.target.value); setCommentErr('') }}
                />
                {commentErr && (
                  <p className="text-[10px] text-red-600">{commentErr}</p>
                )}
                <button
                  className="btn-primary w-full justify-center py-2 text-xs font-semibold"
                  onClick={() => handleSetActive(lc.id)}
                  disabled={setActiveMut.isPending || declineMut.isPending}
                >
                  {setActiveMut.isPending
                    ? <><Loader2 size={12} className="animate-spin" /> Setting Active…</>
                    : <><CheckCircle2 size={12} /> Set as Active</>}
                </button>
                <button
                  className="w-full justify-center py-2 text-xs font-semibold rounded-lg border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 transition-colors flex items-center gap-1.5"
                  onClick={() => { setActionMsg(null); declineMut.mutate(lc.id) }}
                  disabled={declineMut.isPending || setActiveMut.isPending}
                  title="Decline this upgrade — moves back to Acknowledged state"
                >
                  {declineMut.isPending
                    ? <><Loader2 size={11} className="animate-spin" /> Declining…</>
                    : <>✕ Decline Upgrade — Move Back to Acknowledged</>}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Version History Panel ─────────────────────────────────────────────────────
function VersionHistoryPanel({ libId, currentVersion, latestVersion, onVersionSet, lcStatus, lcTargetVersion }: {
  libId: number; currentVersion?: string | null; latestVersion?: string | null
  onVersionSet?: (version: string) => void
  lcStatus?: string | null; lcTargetVersion?: string | null
}) {
  const { isAdmin, user } = useAuth()
  const qc = useQueryClient()
  const username = user?.username ?? 'admin'
  const { data, isLoading } = useQuery({
    queryKey: ['lib-versions', libId],
    queryFn: () => libraryApi.versions(libId),
  })
  const fetchMut = useMutation({
    mutationFn: () => libraryApi.fetchVersions(libId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['lib-versions', libId] })
      // Also refresh library table so latest_version column updates
      qc.refetchQueries({ queryKey: ['libraries'] })
    },
  })
  // Only restore selected version on mount if lifecycle is active and has a target
  const isDoneOnMount = lcStatus === 'Completed' || lcStatus === 'Skipped'
  const [selectedVersion, setSelectedVersion] = useState<string | null>(
    isDoneOnMount ? null : (lcTargetVersion ?? null)
  )

  // Clear selected version when lifecycle reaches a terminal state OR when target_version is cleared (e.g. after decline)
  useEffect(() => {
    if (lcStatus === 'Completed' || lcStatus === 'Skipped') {
      setSelectedVersion(null)
    }
  }, [lcStatus])

  useEffect(() => {
    if (!lcTargetVersion) {
      setSelectedVersion(null)
    }
  }, [lcTargetVersion])

  // Persist version selection to backend — isPending guard prevents rapid-click races
  const selectForReviewMut = useMutation({
    mutationFn: (version: string) =>
      lifecycleApi.init({ library_id: libId, actioned_by: username, target_version: version }),
    onSuccess: () => {
      qc.refetchQueries({ queryKey: ['lifecycle-list-all'] })
      qc.refetchQueries({ queryKey: ['lc-by-lib', libId] })
    },
    onError: () => {},
  })

  interface VersionItem {
    id: number; version: string; release_date: string | null
    release_notes: string | null; maven_url: string | null
    changelog_url: string | null; is_latest: boolean; is_current: boolean
  }
  const vdata = data?.data as { total?: number; versions?: VersionItem[]; package?: string; registry?: string; current_version?: string; latest_version?: string } | undefined
  const versions: VersionItem[] = vdata?.versions ?? []

  return (
    <div className="mt-1">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
            Version History
            {vdata?.total !== undefined && (
              <span className="ml-2 normal-case font-normal text-slate-400">
                {vdata.total} versions from {vdata.registry ?? 'registry'}
              </span>
            )}
          </p>
        </div>
        <button
          className="btn-secondary py-1 text-xs"
          onClick={() => fetchMut.mutate()}
          disabled={fetchMut.isPending}
          title="Fetch all versions from Maven Central / CocoaPods"
        >
          {fetchMut.isPending
            ? <><Loader2 size={11} className="animate-spin" /> {versions.length === 0 ? 'Fetching\u2026' : 'Refreshing\u2026'}</>
            : <><RefreshCw size={11} /> {versions.length === 0 ? 'Fetch Versions' : 'Refresh'}</>}
        </button>
      </div>

      {fetchMut.data && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-green-50 border border-green-200 text-xs text-green-700">
          ✅ Fetched {(fetchMut.data as { data?: { stored?: number } })?.data?.stored ?? 0} versions from registry
        </div>
      )}
      {selectedVersion
        && lcStatus !== 'Completed'
        && lcStatus !== 'Skipped'
        && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-primary-50 border border-primary-200 text-xs text-primary-700">
          ℹ️ <strong>v{selectedVersion}</strong> selected for upgrade review — use the Upgrade Review Queue below to proceed.
        </div>
      )}
      {fetchMut.isError && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
          ❌ Failed to fetch — check network access to Maven Central
        </div>
      )}

      {isLoading && (
        <div className="text-xs text-slate-400 py-4 text-center">
          <Loader2 size={14} className="animate-spin inline mr-1" /> Loading versions\u2026
        </div>
      )}

      {!isLoading && versions.length === 0 && (
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-4 text-center">
          <Tag size={24} className="text-slate-300 mx-auto mb-2" />
          <p className="text-xs font-medium text-slate-500">No versions fetched yet</p>
          <p className="text-xs text-slate-400 mt-1">
            Click "Fetch Versions" to pull all historical versions from Maven Central / CocoaPods
          </p>
        </div>
      )}

      {versions.length > 0 && (
        <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
          {versions.map((v) => {
            const isCurrent = v.version === currentVersion || v.is_current
            const isLatest  = v.version === latestVersion  || v.is_latest
            return (
              <div
                key={v.id}
                className={`rounded-lg border px-3 py-2 flex items-start gap-3 ${
                  isCurrent && isLatest ? 'border-green-300 bg-green-50' :
                  isCurrent ? 'border-blue-300 bg-blue-50' :
                  isLatest  ? 'border-amber-300 bg-amber-50' :
                  'border-slate-100 bg-white'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono text-xs font-bold text-slate-800">v{v.version}</span>
                    {isLatest  && <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-semibold">Latest</span>}
                    {isCurrent && <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full font-semibold">Current</span>}
                    {/* Only show In Progress badge if version is NOT already current — avoids confusing triple-badge */}
                    {lcStatus === 'In Progress' && lcTargetVersion && v.version === lcTargetVersion && !isCurrent && (
                      <span className="text-[10px] bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded-full font-semibold border border-orange-200">🔧 In Progress</span>
                    )}
                    {v.release_date && (
                      <span className="text-[10px] text-slate-400">📅 {v.release_date}</span>
                    )}
                    <div className="ml-auto flex items-center gap-2 flex-shrink-0">
                      {/* Right-side version state indicator */}
                      {selectedVersion === v.version
                        && lcStatus !== 'In Progress'
                        && lcStatus !== 'Completed'
                        && lcStatus !== 'Skipped' && (
                        <span className="text-[10px] font-bold px-2 py-1 rounded-lg bg-primary-600 text-white whitespace-nowrap">
                          🔍 Selected
                        </span>
                      )}
                      {/* Only show In Progress right-side pill if version is NOT already current */}
                      {lcStatus === 'In Progress' && lcTargetVersion && v.version === lcTargetVersion && !isCurrent && (
                        <span className="text-[10px] font-bold px-2 py-1 rounded-lg bg-orange-500 text-white whitespace-nowrap">
                          🔧 In Progress: v{v.version}
                        </span>
                      )}
                      {isAdmin && (() => {
                        const isInProgressTarget = lcStatus === 'In Progress' && lcTargetVersion === v.version
                        const isSelected = selectedVersion === v.version && !isInProgressTarget
                        return (
                          <button
                            className={`text-[10px] font-semibold px-2 py-0.5 rounded border transition-colors ${
                              isCurrent
                                ? 'bg-blue-100 text-blue-700 border-blue-200 cursor-default'
                                : isInProgressTarget
                                ? 'bg-orange-100 text-orange-700 border-orange-200 cursor-default'
                                : isSelected
                                ? 'bg-primary-100 text-primary-700 border-primary-300'
                                : 'bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200'
                            }`}
                            disabled={isCurrent || isInProgressTarget || selectForReviewMut.isPending}
                            onClick={() => {
                              if (isCurrent || isInProgressTarget || selectForReviewMut.isPending) return
                              setSelectedVersion(v.version)
                              selectForReviewMut.mutate(v.version)
                              onVersionSet?.(v.version)
                            }}
                            title={isCurrent ? 'Already the current active version' : isInProgressTarget ? 'Currently in upgrade review' : `Select v${v.version} for upgrade review`}
                          >
                            {isCurrent ? 'Current Active'
                              : isInProgressTarget ? '🔧 In Review'
                              : isSelected ? 'Selected ✓'
                              : 'Select for Review'}
                          </button>
                        )
                      })()}
                      {v.changelog_url && (
                        <a href={v.changelog_url} target="_blank" rel="noreferrer"
                          className="text-[10px] text-green-600 hover:underline flex items-center gap-0.5">
                          <BookOpen size={9} /> Release Notes ↗
                        </a>
                      )}
                      {v.maven_url && (
                        <a href={v.maven_url} target="_blank" rel="noreferrer"
                          className="text-[10px] text-primary-500 hover:underline flex items-center gap-0.5">
                          <ExternalLink size={9} />
                          {v.maven_url.includes('cocoapods.org') ? 'CocoaPods ↗'
                            : v.maven_url.includes('github.com') ? 'GitHub ↗'
                            : v.maven_url.includes('mvnrepository.com') ? 'MVN ↗'
                            : 'View ↗'}
                        </a>
                      )}
                    </div>
                  </div>
                  {v.release_notes && (
                    <p className="text-xs text-slate-500 mt-1 leading-relaxed">{v.release_notes}</p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

    </div>
  )
}

// ── Add / Edit Library Modal ──────────────────────────────────────────────────
const EMPTY_FORM = {
  package: '', sdk_name: '', platform: 'Android' as 'Android' | 'iOS' | 'Both',
  current_version: '', latest_version: '',
  update_needed: 'none' as 'critical' | 'high' | 'moderate' | 'low' | 'mandatory' | 'recommended' | 'optional' | 'none',
  status: 'Active' as 'Active' | 'Inactive' | 'Deprecated' | 'Legacy' | 'Maintenance' | 'Unknown',
  priority: 'Medium' as 'High' | 'Medium' | 'Low',
  alert_priority: 'Normal' as 'Normal' | 'High' | 'Critical',
  registry: '', repo_url: '', framework_language: '',
  comments: '', deprecation_notes: '', deadline_date: '', deadline_notes: '',
}

function AddLibraryModal({ onClose, editLib }: {
  onClose: () => void
  editLib?: Library | null
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState(() =>
    editLib
      ? {
          package:           editLib.package ?? '',
          sdk_name:          editLib.sdk_name ?? '',
          platform:          (editLib.platform as 'Android' | 'iOS' | 'Both') ?? 'Android',
          current_version:   editLib.current_version ?? '',
          latest_version:    editLib.latest_version ?? '',
          update_needed:     (editLib.update_needed?.toLowerCase() as 'critical' | 'high' | 'moderate' | 'low' | 'mandatory' | 'recommended' | 'optional' | 'none') ?? 'none',
          status:            (editLib.status as 'Active' | 'Inactive' | 'Deprecated' | 'Legacy' | 'Maintenance' | 'Unknown') ?? 'Active',
          priority:          (editLib.priority as 'High' | 'Medium' | 'Low') ?? 'Medium',
          alert_priority:    (editLib.alert_priority as 'Normal' | 'High' | 'Critical') ?? 'Normal',
          registry:          editLib.registry ?? '',
          repo_url:          editLib.repo_url ?? '',
          framework_language: editLib.framework_language ?? '',
          comments:          editLib.comments ?? '',
          deprecation_notes: editLib.deprecation_notes ?? '',
          deadline_date:     editLib.deadline_date ?? '',
          deadline_notes:    editLib.deadline_notes ?? '',
        }
      : { ...EMPTY_FORM }
  )
  const [error, setError] = useState('')

  const saveMut = useMutation({
    mutationFn: () => {
      const payload = {
        ...form,
        package:         form.package.trim(),
        sdk_name:        form.sdk_name.trim() || null,
        current_version: form.current_version.trim() || null,
        latest_version:  form.latest_version.trim() || null,
        registry:        form.registry.trim() || null,
        repo_url:        form.repo_url.trim() || null,
        framework_language: form.framework_language.trim() || null,
        comments:        form.comments.trim() || null,
        deprecation_notes: form.deprecation_notes.trim() || null,
        deadline_date:   form.deadline_date || null,
        deadline_notes:  form.deadline_notes.trim() || null,
        ecosystem: 'mobile',
      }
      return editLib
        ? libraryApi.update(editLib.id, payload)
        : libraryApi.create(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['libraries'] })
      onClose()
    },
    onError: (e: unknown) => {
      setError(parseApiError(e, 'Failed to save library'))
    },
  })

  const set = (k: keyof typeof form, v: string) =>
    setForm((f) => ({ ...f, [k]: v }))

  const fieldCls = 'input text-sm'
  const labelCls = 'block text-xs font-medium text-slate-600 mb-0.5'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="text-base font-semibold text-slate-800">
            {editLib ? `Edit \u2014 ${editLib.sdk_name ?? editLib.package}` : '\u2795 Add New SDK'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>

        <div className="overflow-y-auto px-6 py-5 space-y-4 flex-1">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className={labelCls}>Package Identifier <span className="text-red-500">*</span></label>
              <input className={fieldCls} placeholder="e.g. com.squareup.retrofit2:retrofit"
                value={form.package} onChange={(e) => set('package', e.target.value)} />
              <p className="text-[11px] text-slate-400 mt-0.5">Maven: group:artifact \u2014 iOS: pod name</p>
            </div>
            <div>
              <label className={labelCls}>SDK Name / Display Name</label>
              <input className={fieldCls} placeholder="e.g. Retrofit"
                value={form.sdk_name} onChange={(e) => set('sdk_name', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Platform <span className="text-red-500">*</span></label>
              <select className="select text-sm w-full" value={form.platform} onChange={(e) => set('platform', e.target.value)}>
                <option>Android</option><option>iOS</option><option>Both</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Current Version</label>
              <input className={fieldCls} placeholder="e.g. 2.9.0" value={form.current_version} onChange={(e) => set('current_version', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Latest Version</label>
              <input className={fieldCls} placeholder="e.g. 3.0.1" value={form.latest_version} onChange={(e) => set('latest_version', e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Upgrade Needed</label>
              <select className="select text-sm w-full" value={form.update_needed} onChange={(e) => set('update_needed', e.target.value)}>
                <option value="none">None (Up to Date)</option>
                <option value="low">🔵 Low</option>
                <option value="moderate">🟡 Moderate</option>
                <option value="high">🟠 High</option>
                <option value="critical">🔴 Critical</option>
                <option value="optional">Optional (legacy)</option>
                <option value="recommended">Recommended (legacy)</option>
                <option value="mandatory">Mandatory (legacy)</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>SDK Status</label>
              <select className="select text-sm w-full" value={form.status} onChange={(e) => set('status', e.target.value)}>
                <option>Active</option><option>Inactive</option><option>Deprecated</option><option>Legacy</option>
                <option>Maintenance</option><option>Unknown</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Priority</label>
              <select className="select text-sm w-full" value={form.priority} onChange={(e) => set('priority', e.target.value)}>
                <option>High</option><option>Medium</option><option>Low</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Alert Priority</label>
              <select className="select text-sm w-full" value={form.alert_priority} onChange={(e) => set('alert_priority', e.target.value)}>
                <option>Normal</option><option>High</option><option>Critical</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Registry</label>
              <input className={fieldCls} placeholder="e.g. cocoapods, maven, github" value={form.registry} onChange={(e) => set('registry', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Framework / Language</label>
              <input className={fieldCls} placeholder="e.g. Kotlin, Swift, Java" value={form.framework_language} onChange={(e) => set('framework_language', e.target.value)} />
            </div>
            <div className="col-span-2">
              <label className={labelCls}>Repository / Release URL</label>
              <input className={fieldCls} placeholder="https://github.com/..." value={form.repo_url} onChange={(e) => set('repo_url', e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Deadline Date</label>
              <input type="date" className={fieldCls} value={form.deadline_date} onChange={(e) => set('deadline_date', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Deadline Notes</label>
              <input className={fieldCls} placeholder="e.g. SLA Q3 2026" value={form.deadline_notes} onChange={(e) => set('deadline_notes', e.target.value)} />
            </div>
            <div className="col-span-2">
              <label className={labelCls}>Deprecation / Upgrade Reason</label>
              <textarea className={`${fieldCls} resize-none`} rows={2}
                placeholder="Reason for upgrade or deprecation notice\u2026"
                value={form.deprecation_notes} onChange={(e) => set('deprecation_notes', e.target.value)} />
            </div>
            <div className="col-span-2">
              <label className={labelCls}>Comments</label>
              <textarea className={`${fieldCls} resize-none`} rows={2}
                placeholder="Additional context or notes\u2026"
                value={form.comments} onChange={(e) => set('comments', e.target.value)} />
            </div>
          </div>

          {error && (
            <div className="px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">❌ {error}</div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-3">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => { setError(''); saveMut.mutate() }}
            disabled={!form.package.trim() || saveMut.isPending}>
            {saveMut.isPending ? <><Loader2 size={14} className="animate-spin" /> Saving\u2026</> : editLib ? 'Save Changes' : 'Add SDK'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Delete Confirmation Modal ──────────────────────────────────────────────────
function DeleteConfirmModal({
  name, isPending, onConfirm, onCancel,
}: { name: string; isPending: boolean; onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onCancel}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
            <Trash2 size={18} className="text-red-600" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-800">Delete SDK</h2>
            <p className="text-xs text-slate-500">This action cannot be undone</p>
          </div>
        </div>
        <p className="text-sm text-slate-600 mb-5">
          Are you sure you want to delete <span className="font-semibold text-slate-800">{name}</span>?
          All associated recommendations, version history and lifecycle records will also be removed.
        </p>
        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={onCancel} disabled={isPending}>
            Cancel
          </button>
          <button
            className="px-4 py-2 text-sm font-semibold bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors flex items-center gap-2 disabled:opacity-60"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? <><Loader2 size={13} className="animate-spin" /> Deleting…</> : <><Trash2 size={13} /> Delete</>}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Export Menu ─────────────────────────────────────────────────────────────
function ExportMenu({ libraries, platform, recMap, lcMap }: {
  libraries: Library[]
  platform: string
  recMap: Record<number, { recommendation_summary?: string | null; upgrade_recommended?: string | null }>
  lcMap: Record<string, { status: string; target_version?: string | null }>
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useMemo(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filename = (ext: string) =>
    `libraries_${platform.toLowerCase()}_${new Date().toISOString().slice(0, 10)}.${ext}`

  const exportInProgressReport = () => {
    const inProgressLibs = libraries.filter(l => lcMap[String(l.id)]?.status === 'In Progress')
    if (inProgressLibs.length === 0) { alert('No In Progress upgrades found in the current platform view.'); setOpen(false); return }
    const escape = (v: unknown) => {
      const s = v == null ? '' : String(v).replace(/\r?\n/g, ' ')
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? `"${s.replace(/"/g, '""')}"` : s
    }
    const header = 'SDK / Package,Package ID,Current Version,Latest Version,Priority,Status,In Progress Target Ver.,Upgrade Rationale'
    const rows = inProgressLibs.map((l) => {
      const rec = recMap[l.id]
      const rawSummary = rec?.recommendation_summary ?? ''
      const rationale = rawSummary.replace(/^\[\w+\]\s*/, '').replace(/^[^:]+:\s*/, '') || 'No recommendation yet — run pipeline'
      return [
        escape(l.sdk_name || l.package),
        escape(l.package),
        escape(l.current_version ?? '—'),
        escape(l.latest_version ?? '—'),
        escape((l.update_needed ?? 'none').toUpperCase()),
        escape(l.status ?? 'Active'),
        escape(lcMap[String(l.id)]?.target_version ?? '—'),
        escape(rationale),
      ].join(',')
    })
    const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `in_progress_${platform.toLowerCase()}_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    setOpen(false)
  }

  const exportReport = () => {
    const escape = (v: unknown) => {
      const s = v == null ? '' : String(v).replace(/\r?\n/g, ' ')
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? `"${s.replace(/"/g, '""')}"` : s
    }
    const header = 'SDK / Package,Package ID,Current Version,Latest Version,Priority,Status,Upgrade Rationale'
    const rows = libraries.map((l) => {
      const rec = recMap[l.id]
      const rawSummary = rec?.recommendation_summary ?? ''
      const rationale = rawSummary.replace(/^\[\w+\]\s*/, '').replace(/^[^:]+:\s*/, '') || 'No recommendation yet — run pipeline'
      return [
        escape(l.sdk_name || l.package),
        escape(l.package),
        escape(l.current_version ?? '—'),
        escape(l.latest_version ?? '—'),
        escape((l.update_needed ?? 'none').toUpperCase()),
        escape(l.status ?? 'Active'),
        escape(rationale),
      ].join(',')
    })
    const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename('report.csv')
    a.click()
    setOpen(false)
  }

  const exportCSV = () => {
    const COLS = [
      'id', 'sdk_name', 'package', 'library_active_state', 'platform', 'registry',
      'current_version', 'latest_version', 'update_needed', 'status',
      'alert_priority', 'deadline_date', 'framework_language', 'comments',
    ] as const
    const header = COLS.join(',')
    const escape = (v: unknown) => {
      const s = v == null ? '' : String(v)
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? `"${s.replace(/"/g, '""')}"` : s
    }
    const rows = libraries.map((l) => {
      const csvObj = {
        ...l,
        library_active_state: (l.status ?? '').toLowerCase() === 'inactive' ? 'Inactive' : 'Active',
      }
      return COLS.map((c) => escape(csvObj[c as keyof typeof csvObj])).join(',')
    })
    const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename('csv')
    a.click()
    setOpen(false)
  }

  const exportJSON = () => {
    const data = libraries.map((l) => ({
      id:               l.id,
      sdk_name:         l.sdk_name,
      package:          l.package,
      library_active_state: (l.status ?? '').toLowerCase() === 'inactive' ? 'Inactive' : 'Active',
      platform:         l.platform,
      registry:         l.registry,
      current_version:  l.current_version,
      latest_version:   l.latest_version,
      update_needed:    l.update_needed,
      status:           l.status,
      alert_priority:   l.alert_priority,
      deadline_date:    l.deadline_date,
      framework_language: l.framework_language,
      comments:         l.comments,
    }))
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename('json')
    a.click()
    setOpen(false)
  }

  return (
    <div className="relative ml-auto" ref={ref}>
      <button
        className="btn-secondary py-1.5 text-xs flex items-center gap-1.5"
        onClick={() => setOpen((o) => !o)}
        title={`Export ${libraries.length} SDKs`}
      >
        <Download size={12} />
        Export ({libraries.length})
        <ChevronDown size={10} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 bg-white border border-slate-200 rounded-xl shadow-lg z-30 overflow-hidden">
          <div className="px-3 py-2 border-b border-slate-100">
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
              Export {libraries.length} SDKs
            </p>
          </div>
          <button
            className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
            onClick={exportInProgressReport}
          >
            <span className="text-base">🔧</span>
            <div className="text-left">
              <p className="font-medium text-xs">In Progress Report</p>
              <p className="text-[10px] text-slate-400">Only In Progress + 6 cols</p>
            </div>
          </button>
          <button
            className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
            onClick={exportReport}
          >
            <span className="text-base">📊</span>
            <div className="text-left">
              <p className="font-medium text-xs">Portfolio Report</p>
              <p className="text-[10px] text-slate-400">6 columns incl. rationale</p>
            </div>
          </button>
          <button
            className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
            onClick={exportCSV}
          >
            <span className="text-base">📄</span>
            <div className="text-left">
              <p className="font-medium text-xs">CSV</p>
              <p className="text-[10px] text-slate-400">Excel / Sheets</p>
            </div>
          </button>
          <button
            className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
            onClick={exportJSON}
          >
            <span className="text-base">🗂</span>
            <div className="text-left">
              <p className="font-medium text-xs">JSON</p>
              <p className="text-[10px] text-slate-400">API / developer use</p>
            </div>
          </button>
        </div>
      )}
    </div>
  )
}

// ── Main Libraries Page ────────────────────────────────────────────────────────
function LibraryMain() {
  const { isAdmin, user } = useAuth()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [platform, setPlatform] = useState<'Android' | 'iOS'>('Android')
  const [priority, setPriority] = useState('All')
  const [activeState, setActiveState] = useState<'All' | 'Active' | 'Inactive'>('All')
  const [lifecycleFilter, setLifecycleFilter] = useState<'All' | 'In Progress'>('All')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [reviewVersionMap, setReviewVersionMap] = useState<Record<number, string>>({})
  const [activeTab, setActiveTab] = useState<'info' | 'recommendation' | 'release_notes'>('info')
  const [sortKey, setSortKey] = useState<string>('sdk_name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editLib, setEditLib] = useState<Library | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [hiddenQueues, setHiddenQueues] = useState<Set<number>>(new Set())
  const [assistInputMap, setAssistInputMap] = useState<Record<number, string>>({})
  const [assistChatMap, setAssistChatMap] = useState<Record<number, AssistChatMessage[]>>({})
  const [assistLoadingMap, setAssistLoadingMap] = useState<Record<number, boolean>>({})
  const [assistUsageMap, setAssistUsageMap] = useState<Record<number, AssistUsage>>({})
  const [assistErrorMap, setAssistErrorMap] = useState<Record<number, string | null>>({})

  // Admin bulk mutations
  const syncUrlsMut = useMutation({
    mutationFn: () => libraryApi.syncMavenUrls(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['libraries'] }),
  })
  const bulkFetchMut = useMutation({
    mutationFn: () => libraryApi.bulkFetchVersions(),
    onSuccess: () => refetchBulkStatus(),
  })
  const { data: bulkStatusRes, refetch: refetchBulkStatus } = useQuery({
    queryKey: ['bulk-fetch-status'],
    queryFn: () => libraryApi.bulkFetchStatus(),
    refetchInterval: (query) => {
      const d = query.state.data?.data as { running?: boolean } | undefined
      return d?.running ? 3000 : false
    },
  })
  const bulkStatus = bulkStatusRes?.data as {
    running?: boolean; done?: number; total?: number; errors?: number; last_run?: string
  } | undefined

  const deleteMut = useMutation({
    mutationFn: (id: number) => libraryApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['libraries'] }); setDeleteConfirmId(null) },
  })

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'Active' | 'Inactive' }) =>
      libraryApi.update(id, {
        status,
        updated_by: user?.username ?? 'admin',
        reason: status === 'Inactive' ? 'SDK deactivated by admin' : 'SDK reactivated by admin',
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['libraries'] }),
  })

  const { data: libRes, isLoading } = useQuery({
    queryKey: ['libraries'], queryFn: () => libraryApi.list(),
  })
  const libs: Library[] = (libRes?.data as { libraries?: Library[] })?.libraries ?? []

  // Pre-fetch all lifecycle records — must be declared BEFORE filtered so inprogress_ver sort can use lcMap
  const { data: lcListRes } = useQuery({
    queryKey: ['lifecycle-list-all'],
    queryFn: () => lifecycleApi.list(),
    staleTime: 0,
    refetchInterval: 10_000,
  })
  const lcMap: Record<string, { status: string; target_version?: string | null; updated_at?: string | null }> = useMemo(() => {
    const rows = Array.isArray(lcListRes?.data)
      ? (lcListRes!.data as { id?: number | null; library_id: number; status: string; target_version?: string | null; updated_at?: string | null }[])
      : []
    return pickLatestLifecycleByLibrary(rows)
  }, [lcListRes])

  const filtered = useMemo(() => {
    const PRIORITY_ORDER: Record<string, number> = {
      critical: 0, mandatory: 1, high: 2, moderate: 3, low: 4, recommended: 5, optional: 6, none: 7, '': 8,
    }
    const base = libs.filter((l) => {
      const matchPlatform = l.platform === platform
      const matchSearch = !search ||
        (l.package ?? '').toLowerCase().includes(search.toLowerCase()) ||
        (l.sdk_name ?? '').toLowerCase().includes(search.toLowerCase())
      const matchPriority = priority === 'All'
        || (priority === 'none' && ['none', 'optional', ''].includes((l.update_needed ?? '').toLowerCase()))
        || (priority !== 'All' && (l.update_needed ?? '').toLowerCase() === priority.toLowerCase())
      const isInactive = (l.status ?? '').toLowerCase() === 'inactive'
      const matchActiveState = activeState === 'All'
        || (activeState === 'Active' && !isInactive)
        || (activeState === 'Inactive' && isInactive)
      const matchLifecycle = lifecycleFilter === 'All'
        || (lifecycleFilter === 'In Progress' && lcMap[String(l.id)]?.status === 'In Progress')
      return matchPlatform && matchSearch && matchPriority && matchActiveState && matchLifecycle
    })

    return [...base].sort((a, b) => {
      let av: string | number = ''
      let bv: string | number = ''
      switch (sortKey) {
        case 'sdk_name':
          av = (a.sdk_name || a.package || '').toLowerCase()
          bv = (b.sdk_name || b.package || '').toLowerCase()
          break
        case 'registry':
          av = (a.registry ?? '').toLowerCase()
          bv = (b.registry ?? '').toLowerCase()
          break
        case 'current_version':
          av = a.current_version ?? ''
          bv = b.current_version ?? ''
          break
        case 'latest_version':
          av = a.latest_version ?? ''
          bv = b.latest_version ?? ''
          break
        case 'update_needed':
          av = PRIORITY_ORDER[(a.update_needed ?? '').toLowerCase()] ?? 9
          bv = PRIORITY_ORDER[(b.update_needed ?? '').toLowerCase()] ?? 9
          break
        case 'status':
          av = (a.status ?? '').toLowerCase()
          bv = (b.status ?? '').toLowerCase()
          break
        case 'inprogress_ver':
          av = (lcMap[String(a.id)]?.status === 'In Progress' ? lcMap[String(a.id)]?.target_version : null) ?? 'zzz'
          bv = (lcMap[String(b.id)]?.status === 'In Progress' ? lcMap[String(b.id)]?.target_version : null) ?? 'zzz'
          break
        case 'deadline_date':
          av = a.deadline_date ?? 'z'
          bv = b.deadline_date ?? 'z'
          break
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [libs, search, platform, priority, activeState, lifecycleFilter, sortKey, sortDir, lcMap])

  const handleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const SortIcon = ({ col }: { col: string }) => {
    if (sortKey !== col) return <ArrowUpDown size={11} className="text-slate-300 ml-1 inline" />
    return sortDir === 'asc'
      ? <ArrowUp size={11} className="text-primary-500 ml-1 inline" />
      : <ArrowDown size={11} className="text-primary-500 ml-1 inline" />
  }

  const platformKpi = useMemo(() => {
    const pl = libs.filter((l) => l.platform === platform)
    const _pun = (l: Library) => (l.update_needed ?? '').toLowerCase()
    const critHigh = pl.filter((l) => ['critical','high','mandatory'].includes(_pun(l))).length
    const mod      = pl.filter((l) => _pun(l) === 'moderate').length
    const upToDate = pl.filter((l) => ['none','optional','','low'].includes(_pun(l))).length
    return { total: pl.length, critHigh, moderate: mod, upToDate }
  }, [libs, platform])
  const portfolioCriticalHigh = libs.filter((l) => ['critical', 'high', 'mandatory'].includes((l.update_needed ?? '').toLowerCase())).length

  const { data: recRes } = useQuery({
    queryKey: ['recommendations'],
    queryFn: () => recApi.list(),
    enabled: libs.length > 0,   // always fetch when libraries are loaded
    staleTime: 60_000,
  })
  const recMap: Record<number, Recommendation> = useMemo(() => {
    const recs: Recommendation[] = Array.isArray(recRes?.data) ? (recRes!.data as Recommendation[]) : []
    return Object.fromEntries(recs.map((r) => [r.library_id, r]))
  }, [recRes])

  const { data: llmStatusRes } = useQuery({
    queryKey: ['rec-llm-status'],
    queryFn: () => recApi.llmStatus(),
    staleTime: 60_000,
    refetchInterval: 60_000,
  })
  const llmStatus = (llmStatusRes?.data as { success?: boolean; llm_enabled?: boolean } | undefined)
  const llmConnected = !!(llmStatus?.success && llmStatus?.llm_enabled)

  // Pre-fetch all lifecycle records once → composite status column
  // NOTE: lcMap declared earlier (before filtered) to allow inprogress_ver sorting

  const normalizeLifecycleStatus = (status?: string | null) =>
    status === 'Pending' ? 'awaiting_review' : status

  const isLifecycleQueueVisible = (libraryId: number): boolean => {
    const normalized = normalizeLifecycleStatus(lcMap[String(libraryId)]?.status)
    return normalized === 'awaiting_review' || normalized === 'Acknowledged' || normalized === 'In Progress'
  }

  const toggleExpand = (id: number) => {
    if (expandedId === id) {
      // Collapse: just hide the row — keep reviewVersionMap & hiddenQueues so
      // re-expanding the same row restores the queue state exactly as left
      setExpandedId(null)
    } else {
      // Expanding a different row: reset queue state for clean context
      setExpandedId(id)
      setActiveTab('info')
      setReviewVersionMap((prev) => {
        // Keep In Progress entries so the queue auto-shows on expand
        const next: Record<number, string> = {}
        if (prev[id]) next[id] = prev[id]
        return next
      })
      setHiddenQueues(new Set())
    }
  }

  const submitAssistQuestion = async (lib: Library, forcedQuestion?: string) => {
    if (assistLoadingMap[lib.id]) return
    const question = (forcedQuestion ?? assistInputMap[lib.id] ?? '').trim()
    if (!question) return

    const rec = recMap[lib.id]
    const existing = assistChatMap[lib.id] || []
    const history: RecommendationChatTurn[] = existing.slice(-6).map((m) => ({ role: m.role, text: m.text }))

    setAssistErrorMap((prev) => ({ ...prev, [lib.id]: null }))
    setAssistLoadingMap((prev) => ({ ...prev, [lib.id]: true }))
    setAssistChatMap((prev) => {
      const current = prev[lib.id] || []
      const next: AssistChatMessage[] = [...current, { role: 'user', text: question }]
      return { ...prev, [lib.id]: next.slice(-8) }
    })
    setAssistInputMap((prev) => ({ ...prev, [lib.id]: '' }))

    const payload: RecommendationChatRequest = {
      library_id: lib.id,
      package: lib.package,
      sdk_name: lib.sdk_name,
      platform: lib.platform,
      current_version: lib.current_version,
      latest_version: lib.latest_version,
      update_needed: lib.update_needed,
      status: lib.status,
      recommendation_summary: rec?.recommendation_summary,
      upgrade_recommended: rec?.upgrade_recommended,
      upgrade_pros: rec?.upgrade_pros ?? [],
      upgrade_cons: rec?.upgrade_cons ?? [],
      question,
      history,
    }

    try {
      const res = await recApi.chatAsk(payload)
      const data = (res.data || {}) as RecommendationChatResult
      setAssistChatMap((prev) => {
        const current = prev[lib.id] || []
        const next: AssistChatMessage[] = [...current, { role: 'assistant', text: data.answer || 'No response from LLM.' }]
        return { ...prev, [lib.id]: next.slice(-8) }
      })
      setAssistUsageMap((prev) => {
        const current = prev[lib.id] || {
          calls: 0,
          promptTokens: 0,
          completionTokens: 0,
          totalTokens: 0,
          lastModel: null,
          lastLatencyMs: null,
        }
        return {
          ...prev,
          [lib.id]: {
            calls: current.calls + 1,
            promptTokens: current.promptTokens + (data.prompt_tokens || 0),
            completionTokens: current.completionTokens + (data.completion_tokens || 0),
            totalTokens: current.totalTokens + (data.total_tokens || 0),
            lastModel: data.model || current.lastModel,
            lastLatencyMs: data.latency_ms ?? current.lastLatencyMs,
          },
        }
      })
    } catch (error) {
      const raw = parseApiError(error, 'LLM chat failed')
      const normalized = raw.toLowerCase()
      const msg = normalized.includes('429') || normalized.includes('too many requests')
        ? 'LLM quota/rate limit reached (429). Retry after a short wait or use a model/account with available quota.'
        : normalized.includes('certificate_verify_failed')
          ? 'LLM SSL certificate verification failed. Check runtime cert trust or SSL verification settings.'
          : normalized.includes('connection error')
            ? 'LLM connection failed. Check provider endpoint, network egress, or proxy/firewall settings.'
            : raw

      setAssistErrorMap((prev) => ({ ...prev, [lib.id]: msg }))
      setAssistChatMap((prev) => {
        const current = prev[lib.id] || []
        const next: AssistChatMessage[] = [...current, { role: 'assistant', text: `I could not answer right now: ${msg}` }]
        return { ...prev, [lib.id]: next.slice(-8) }
      })
    } finally {
      setAssistLoadingMap((prev) => ({ ...prev, [lib.id]: false }))
    }
  }

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const safePage = Math.min(page, totalPages)
  const startIndex = (safePage - 1) * pageSize
  const endIndex = Math.min(startIndex + pageSize, filtered.length)
  const pageItems = filtered.slice(startIndex, endIndex)

  useEffect(() => {
    setPage(1)
  }, [search, platform, priority, activeState, lifecycleFilter, sortKey, sortDir, pageSize])

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  useEffect(() => {
    if (expandedId !== null && !pageItems.some((l) => l.id === expandedId)) {
      setExpandedId(null)
    }
  }, [expandedId, pageItems])

  const registryLabel = (reg: string | null | undefined) => {
    if (!reg) return '\u2014'
    if (reg === 'cocoapods') return 'CocoaPods'
    if (reg === 'github') return 'GitHub'
    if (reg === 'spm') return 'SPM'
    if (reg === 'custom') return 'Custom'
    if (reg.toLowerCase().includes('maven')) return 'Maven'
    return reg
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">SDK Portfolio</h1>
          <p className="page-subtitle">
            {libs.length} SDK records with upgrade posture and lifecycle context
            {(() => {
              const inProg = Object.values(lcMap).filter(l => l.status === 'In Progress').length
              return inProg > 0 ? <span className="ml-2 text-[11px] font-semibold text-orange-600 bg-orange-50 border border-orange-200 px-2 py-0.5 rounded-full">🔧 {inProg} In Progress</span> : null
            })()}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {isAdmin && (
            <button
              className="btn-secondary py-1.5 px-3 text-xs sm:text-sm whitespace-nowrap"
              onClick={() => syncUrlsMut.mutate()}
              disabled={syncUrlsMut.isPending || bulkFetchMut.isPending || Boolean(bulkStatus?.running)}
              title="Sync Maven/registry URLs for all SDKs"
            >
              {syncUrlsMut.isPending
                ? <><Loader2 size={12} className="animate-spin" /> Syncing URLs…</>
                : <><RefreshCw size={12} /> Sync Registry URLs</>}
            </button>
          )}
          {isAdmin && (
            <button
              className="btn-secondary py-1.5 px-3 text-xs sm:text-sm whitespace-nowrap"
              onClick={() => bulkFetchMut.mutate()}
              disabled={bulkFetchMut.isPending || syncUrlsMut.isPending || Boolean(bulkStatus?.running)}
              title="Fetch versions for all SDKs in the selected portfolio"
            >
              {bulkFetchMut.isPending || bulkStatus?.running
                ? <><Loader2 size={12} className="animate-spin" /> Fetching Versions…</>
                : <><RefreshCw size={12} /> Bulk Fetch Versions</>}
            </button>
          )}
          {isAdmin && (
            <button className="btn-primary py-1.5 px-3 text-xs sm:text-sm whitespace-nowrap" onClick={() => { setEditLib(null); setShowAddModal(true) }}>
              <Plus size={14} /> Add SDK
            </button>
          )}
          <button
            className="btn-secondary py-1.5 px-3 text-xs sm:text-sm whitespace-nowrap"
            disabled={isRefreshing}
            onClick={async () => {
              setIsRefreshing(true)
              await Promise.all([
                qc.refetchQueries({ queryKey: ['libraries'] }),
                qc.refetchQueries({ queryKey: ['lifecycle-list-all'] }),
              ])
              setIsRefreshing(false)
            }}
            title="Force-refresh library table and lifecycle status"
          >
            {isRefreshing
              ? <><Loader2 size={12} className="animate-spin" /> Refreshing…</>
              : <><RefreshCw size={12} /> Refresh Table</>}
          </button>
        </div>
      </div>

      <ExecutiveTriad
        impact={`${portfolioCriticalHigh} SDKs across the portfolio are marked critical/high/mandatory.`}
        owner={`${platform} SDK Domain Leads`}
        nextAction={filtered.length > 0 ? `Triage the top ${Math.min(5, filtered.length)} visible SDKs and confirm target versions.` : 'Clear filters and resume platform-level remediation planning.'}
        tone={portfolioCriticalHigh > 0 ? 'warning' : 'positive'}
      />

      {/* Portfolio KPI stats row */}
      {libs.length > 0 && (() => {
        const _un = (l: Library) => (l.update_needed ?? '').toLowerCase()
        const critical  = libs.filter(l => ['critical','mandatory'].includes(_un(l))).length
        const high      = libs.filter(l => _un(l) === 'high').length
        const moderate  = libs.filter(l => ['moderate','low'].includes(_un(l))).length
        const upToDate  = libs.filter(l => ['none','optional',''].includes(_un(l))).length
        const inProg    = Object.values(lcMap).filter(l => l.status === 'In Progress').length
        const awaiting  = Object.values(lcMap).filter(l => l.status === 'Pending' || l.status === 'awaiting_review' || l.status === 'Acknowledged').length
        const stats = [
          { label: 'Total SDKs',        value: libs.length,  color: 'text-slate-800',  bg: 'bg-slate-50  border-slate-200'  },
          { label: '🔴 Critical / Mandatory', value: critical,  color: 'text-red-700',    bg: 'bg-red-50    border-red-200'    },
          { label: '🟠 High',            value: high,         color: 'text-orange-700', bg: 'bg-orange-50 border-orange-200' },
          { label: '🟡 Moderate',        value: moderate,     color: 'text-amber-700',  bg: 'bg-amber-50  border-amber-200'  },
          { label: '✅ Up to Date',      value: upToDate,     color: 'text-green-700',  bg: 'bg-green-50  border-green-200'  },
          { label: '🔧 In Progress',     value: inProg,       color: 'text-orange-600', bg: 'bg-orange-50 border-orange-200' },
          { label: '⏳ Awaiting Review', value: awaiting,     color: 'text-yellow-700', bg: 'bg-yellow-50 border-yellow-200' },
        ]
        return (
          <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-3">
            {stats.map(s => (
              <div key={s.label} className={`rounded-xl border px-4 py-3 ${s.bg}`}>
                <p className="text-[11px] text-slate-500 mb-0.5">{s.label}</p>
                <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              </div>
            ))}
          </div>
        )
      })()}

      {/* Bulk fetch progress — still shown if running in background */}
      {bulkStatus?.running && (
        <div className="card p-3">
          <div className="flex items-center gap-3 mb-1.5">
            <Loader2 size={12} className="animate-spin text-primary-600" />
            <p className="text-xs font-medium text-slate-700">Fetching version history\u2026 {bulkStatus.done}/{bulkStatus.total} SDKs</p>
            {!!bulkStatus.errors && <span className="text-xs text-red-500">{bulkStatus.errors} errors</span>}
          </div>
          <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
            <div className="h-full bg-primary-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.round(((bulkStatus.done ?? 0) / (bulkStatus.total || 1)) * 100)}%` }} />
          </div>
        </div>
      )}

      {/* Platform Tabs — Android | iOS */}
      <div className="flex gap-0 border-b-2 border-slate-200">
        {PLATFORMS.map((p) => {
          const count  = libs.filter((l) => l.platform === p).length
          const active = platform === p
          const isAndroid = p === 'Android'
          return (
            <button key={p}
              onClick={() => { setPlatform(p); setSearch(''); setPriority('All'); setExpandedId(null) }}
              className={`px-6 py-3 text-sm font-semibold border-b-2 -mb-0.5 transition-all flex items-center gap-3 ${
                active
                  ? isAndroid
                    ? 'border-green-600 text-green-700 bg-green-50'
                    : 'border-sky-600 text-sky-700 bg-sky-50'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
              }`}>
              {/* Icon badge */}
              <span className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 transition-all ${
                active
                  ? isAndroid ? 'bg-green-600 shadow-md' : 'bg-sky-600 shadow-md'
                  : 'bg-slate-100'
              }`}>
                {isAndroid
                  ? <AndroidIcon size={22} className={active ? 'text-white' : 'text-slate-400'} />
                  : <AppleIcon  size={22} className={active ? 'text-white' : 'text-slate-400'} />
                }
              </span>
              <span className="font-bold">{p}</span>
              <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold ${
                active
                  ? isAndroid ? 'bg-green-200 text-green-900' : 'bg-sky-200 text-sky-900'
                  : 'bg-slate-200 text-slate-500'
              }`}>{count}</span>
            </button>
          )
        })}
      </div>

      {/* Per-platform KPI strip */}
      <div className={`rounded-xl p-4 grid grid-cols-4 gap-3 ${
        platform === 'Android' ? 'bg-green-50 border border-green-200' : 'bg-sky-50 border border-sky-200'
      }`}>
        {([
          { label: 'Total',           value: platformKpi.total,    color: 'text-slate-800' },
          { label: '🔴+🟠 Critical/High', value: platformKpi.critHigh, color: 'text-red-600'   },
          { label: '🟡 Moderate',     value: platformKpi.moderate, color: 'text-amber-600' },
          { label: '✅ Up to Date',   value: platformKpi.upToDate, color: 'text-green-700' },
        ] as { label: string; value: number; color: string }[]).map(({ label, value, color }) => (
          <div key={label} className="text-center">
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
            <p className="text-xs text-slate-500 mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input pl-9"
            placeholder={`Search ${platform} SDK name or package\u2026`}
            value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-slate-400" />
          <select className="select w-auto" value={priority} onChange={(e) => setPriority(e.target.value)}>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p === 'All' ? 'All Priorities'
                  : p === 'critical' ? '🔴 Critical'
                  : p === 'high' ? '🟠 High'
                  : p === 'moderate' ? '🟡 Moderate'
                  : p === 'low' ? '🔵 Low'
                  : p === 'none' ? '✅ Up to Date'
                  : p === 'mandatory' ? '⚠️ Mandatory (legacy)'
                  : p.charAt(0).toUpperCase() + p.slice(1)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
          {(['All', 'Active', 'Inactive'] as const).map((st) => (
            <button
              key={st}
              className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                activeState === st
                  ? st === 'Inactive'
                    ? 'bg-slate-700 text-white'
                    : 'bg-emerald-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
              onClick={() => setActiveState(st)}
              title={`Filter by ${st} SDKs`}
            >
              {st}
            </button>
          ))}
        </div>
        {/* Lifecycle In Progress filter */}
        <button
          className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border font-semibold transition-colors ${
            lifecycleFilter === 'In Progress'
              ? 'bg-orange-500 text-white border-orange-500'
              : 'bg-white text-slate-600 border-slate-200 hover:border-orange-300 hover:text-orange-600'
          }`}
          onClick={() => setLifecycleFilter(f => f === 'In Progress' ? 'All' : 'In Progress')}
          title="Show only SDKs with an active upgrade In Progress"
        >
          🔧 In Progress only
        </button>
        {(search || priority !== 'All' || activeState !== 'All' || lifecycleFilter !== 'All') && (
          <button className="btn-secondary py-1 text-xs" onClick={() => { setSearch(''); setPriority('All'); setActiveState('All'); setLifecycleFilter('All') }}>
            <X size={12} /> Clear
          </button>
        )}
        <span className="text-xs text-slate-400">{filtered.length} results</span>
        {/* Export dropdown */}
        <ExportMenu libraries={filtered} platform={platform} recMap={recMap} lcMap={lcMap} />
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="card overflow-hidden">
          <div className="p-8 text-center text-slate-400 text-sm">Loading SDKs\u2026</div>
        </div>
      ) : (
        <SectionCard
          bandTitle="Portfolio Operations"
          bandSubtitle="Platform posture, filter controls, and sortable SDK inventory with enterprise pagination."
          cardClassName="card overflow-hidden"
          header={{
            title: 'SDK Inventory Ledger',
            totalItems: filtered.length,
            startIndex,
            endIndex,
            pageSize,
            pageSizeOptions: [10, 20, 50, 100],
            onPageSizeChange: (value) => setPageSize(value),
          }}
          footer={filtered.length > 0 ? {
            page: safePage,
            totalPages,
            onPrev: () => setPage((p) => Math.max(1, p - 1)),
            onNext: () => setPage((p) => Math.min(totalPages, p + 1)),
          } : undefined}
        >
            <div className="overflow-x-auto">
            <table className="w-full table-base table-fixed">
              <thead>
                <tr>
                  <th className="w-[220px] cursor-pointer select-none" onClick={() => handleSort('sdk_name')}>
                    SDK / Package <SortIcon col="sdk_name" />
                  </th>
                  <th className="w-24 cursor-pointer select-none" onClick={() => handleSort('registry')}>
                    Registry <SortIcon col="registry" />
                  </th>
                  <th className="w-28 cursor-pointer select-none" onClick={() => handleSort('current_version')}>
                    Current <SortIcon col="current_version" />
                  </th>
                  <th className="w-28 cursor-pointer select-none" onClick={() => handleSort('latest_version')}>
                    Latest <SortIcon col="latest_version" />
                  </th>
                  <th className="w-28 cursor-pointer select-none" onClick={() => handleSort('update_needed')}>
                    Priority <SortIcon col="update_needed" />
                  </th>
                  <th className="w-32 cursor-pointer select-none" onClick={() => handleSort('inprogress_ver')}>
                    In Progress Ver. <SortIcon col="inprogress_ver" />
                  </th>
                  <th className="w-36">SDK Active State</th>
                  <th className="w-[260px]">Upgrade Rationale</th>
                  <th className="w-28 cursor-pointer select-none" onClick={() => handleSort('status')}>
                    Status <SortIcon col="status" />
                  </th>
                  <th className="w-28 cursor-pointer select-none" onClick={() => handleSort('deadline_date')}>
                    Deadline <SortIcon col="deadline_date" />
                  </th>
                  <th className="w-28"></th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((lib) => (
                  <Fragment key={lib.id}>
                    <tr className="cursor-pointer" onClick={() => toggleExpand(lib.id)}>
                      <td className="align-top">
                        <p className="font-semibold text-slate-900">{lib.sdk_name || lib.package}</p>
                        {lib.sdk_name && (
                          <p className="text-[11px] text-slate-400 font-mono truncate max-w-[220px]" title={lib.package}>{lib.package}</p>
                        )}
                      </td>
                      <td className="text-xs text-slate-500 whitespace-nowrap">{registryLabel(lib.registry)}</td>
                      <td className="font-mono text-xs">{lib.current_version ?? '\u2014'}</td>
                      <td className="font-mono text-xs font-medium">
                        {lib.latest_version && lib.latest_version !== lib.current_version
                          ? <span className="text-amber-600 font-semibold">{lib.latest_version}</span>
                          : <span className="text-slate-600">{lib.latest_version ?? '\u2014'}</span>}
                      </td>
                      <td><StatusBadge status={lib.update_needed ?? 'none'} /></td>
                      <td className="align-top">
                        {(() => {
                          const lc = lcMap[String(lib.id)]
                          const lcs = lc?.status === 'Pending' ? 'awaiting_review' : lc?.status
                          if (lcs === 'In Progress' && lc?.target_version) {
                            return (
                              <span className="inline-flex items-center gap-1 text-[10px] font-bold font-mono px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 border border-orange-300">
                                🔧 v{lc.target_version}
                              </span>
                            )
                          }
                          return <span className="text-xs text-slate-300">—</span>
                        })()}
                      </td>
                      <td className="align-top">
                        <StatusBadge
                          status={(lib.status ?? '').toLowerCase() === 'inactive' ? 'inactive' : 'active'}
                          size="sm"
                        />
                      </td>
                      <td className="align-top">
                        {(() => {
                          // Prefer DB-sourced recommendation summary over frontend-computed reason
                          const rec = recMap[lib.id]
                          const rawSummary = rec?.recommendation_summary ?? ''
                          // Strip the [PRIORITY] prefix from summary e.g. "[HIGH] pkg: reason"
                          const cleanSummary = rawSummary.replace(/^\[\w+\]\s*/, '').replace(/^[^:]+:\s*/, '')

                          if (cleanSummary && cleanSummary.length > 5) {
                            // Derive bump type tag from summary text
                            const bumptag =
                              rawSummary.includes('major') ? { t: 'Major Upgrade',   c: 'bg-red-100 text-red-700' } :
                              rawSummary.includes('minor') ? { t: 'Minor Upgrade',   c: 'bg-orange-100 text-orange-700' } :
                              rawSummary.includes('patch') ? { t: 'Patch Update',    c: 'bg-amber-100 text-amber-700' } :
                              rawSummary.includes('deprecated') ? { t: 'Deprecated',c: 'bg-slate-200 text-slate-700' } :
                              rawSummary.includes('up-to-date') ? { t: 'Up to Date', c: 'bg-emerald-100 text-emerald-700' } :
                              { t: 'Update Available', c: 'bg-blue-100 text-blue-700' }
                            const pros = rec?.upgrade_pros?.slice(0, 2) ?? []
                            return (
                              <div className="max-w-[240px] space-y-0.5">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${bumptag.c}`}>{bumptag.t}</span>
                                </div>
                                <p className="text-[11px] text-slate-600 leading-snug">{cleanSummary}</p>
                                {pros.length > 0 && (
                                  <p className="text-[10px] text-slate-400 italic">✓ {pros[0]}</p>
                                )}
                              </div>
                            )
                          }
                          // Fallback: avoid embedding recommendation business logic in UI.
                          const versionLine = [lib.current_version, lib.latest_version].filter(Boolean).join(' → ') || '—'
                          return (
                            <div className="max-w-[240px] space-y-0.5">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">Awaiting Recommendation</span>
                                <span className="font-mono text-[10px] text-slate-500">{versionLine}</span>
                              </div>
                              <p className="text-[11px] text-slate-600 leading-snug">No generated recommendation yet for this SDK.</p>
                              <p className="text-[10px] text-slate-400 italic">↳ Run scheduler pipeline to generate recommendation.</p>
                            </div>
                          )
                        })()}
                      </td>
                      <td className="align-top">
                        <div className="flex flex-col gap-1">
                          {/* Library operational status */}
                          <StatusBadge status={lib.status ?? 'unknown'} size="sm" />
                          {/* Lifecycle review state */}
                          {lcMap[String(lib.id)] && (() => {
                            const raw = lcMap[String(lib.id)].status
                            const lcs = raw === 'Pending' ? 'awaiting_review' : raw
                            const meta: Record<string, { label: string; cls: string }> = {
                              awaiting_review: { label: '⏳ Awaiting Review', cls: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
                              Acknowledged:    { label: '👁 Acknowledged',    cls: 'bg-blue-50 text-blue-700 border-blue-200' },
                              'In Progress':   { label: '🔧 In Progress',     cls: 'bg-orange-50 text-orange-700 border-orange-200' },
                              Completed:       { label: '🗸 Upgrade Done',    cls: 'bg-green-50 text-green-700 border-green-200' },
                              Skipped:         { label: '⏭ Skipped',          cls: 'bg-slate-50 text-slate-500 border-slate-200' },
                            }
                            const m = meta[lcs]
                            if (!m) return null
                            return (
                              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border whitespace-nowrap ${m.cls}`}>
                                {m.label}
                              </span>
                            )
                          })()}
                          {/* New version alert flag */}
                          {lib.latest_version && lib.current_version &&
                            lib.latest_version !== lib.current_version && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full border bg-amber-50 text-amber-700 border-amber-300 whitespace-nowrap">
                              🆕 v{lib.latest_version}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="align-top text-xs text-slate-500">{lib.deadline_date ?? '\u2014'}</td>
                      <td className="align-top">
                        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                          {isAdmin && (
                            <button className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-primary-600"
                              title="Edit" onClick={() => { setEditLib(lib); setShowAddModal(true) }}><Pencil size={13} /></button>
                          )}
                          {isAdmin && (
                            <button
                              className="p-1 rounded hover:bg-amber-50 text-slate-400 hover:text-amber-600"
                              title={(lib.status ?? '').toLowerCase() === 'inactive' ? 'Reactivate' : 'Deactivate'}
                              onClick={() => statusMut.mutate({
                                id: lib.id,
                                status: (lib.status ?? '').toLowerCase() === 'inactive' ? 'Active' : 'Inactive',
                              })}
                              disabled={statusMut.isPending}
                            >
                              <Power size={13} />
                            </button>
                          )}
                          {isAdmin && (deleteConfirmId === lib.id ? (
                            <DeleteConfirmModal
                              name={lib.sdk_name || lib.package || `SDK #${lib.id}`}
                              isPending={deleteMut.isPending}
                              onConfirm={() => deleteMut.mutate(lib.id)}
                              onCancel={() => setDeleteConfirmId(null)}
                            />
                          ) : (
                            <button className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500"
                              title="Delete" onClick={() => setDeleteConfirmId(lib.id)}>
                              <Trash2 size={13} />
                            </button>
                          ))}
                          {expandedId === lib.id
                            ? <ChevronUp size={14} className="text-slate-400" onClick={() => toggleExpand(lib.id)} />
                            : <ChevronDown size={14} className="text-slate-400" onClick={() => toggleExpand(lib.id)} />}
                        </div>
                      </td>
                    </tr>

                    {expandedId === lib.id && (
                      <tr>
                        <td colSpan={11} className="bg-slate-50 p-0">
                          <div className="p-5">
                            <div className="flex gap-1 mb-4 border-b border-slate-200">
                              {(['info', 'recommendation', 'release_notes'] as const).map((t) => (
                                <button key={t}
                                  onClick={(e) => { e.stopPropagation(); setActiveTab(t) }}
                                  className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
                                    activeTab === t ? 'border-primary-600 text-primary-600' : 'border-transparent text-slate-500 hover:text-slate-700'
                                  }`}>
                                  {t === 'info' ? '\u2139\ufe0f Info' : t === 'recommendation' ? '\ud83e\udd16 AI Recommendation' : '\ud83d\udce6 Version History'}
                                </button>
                              ))}
                            </div>

                            {activeTab === 'info' && (
                              <div className="space-y-4">
                                {lib.update_needed?.toLowerCase() === 'mandatory' && (
                                  <div className="col-span-full px-4 py-3 rounded-lg bg-red-50 border border-red-200">
                                    <p className="text-xs font-semibold text-red-700 mb-1">\u26d4 Mandatory Upgrade Reason</p>
                                    <p className="text-sm text-red-800">{lib.deprecation_notes ?? lib.comments ?? 'Security/compliance requirement'}</p>
                                  </div>
                                )}
                                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                                    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-3">Business View</p>
                                    <div className="space-y-2.5">
                                      <div className="flex items-center justify-between gap-2">
                                        <span className="text-xs text-slate-500">Upgrade Needed</span>
                                        <StatusBadge status={lib.update_needed ?? 'none'} size="sm" />
                                      </div>
                                      <div className="flex items-center justify-between gap-2">
                                        <span className="text-xs text-slate-500">SDK State</span>
                                        <StatusBadge status={(lib.status ?? '').toLowerCase() === 'inactive' ? 'inactive' : 'active'} size="sm" />
                                      </div>
                                      <div className="flex items-center justify-between gap-2">
                                        <span className="text-xs text-slate-500">Operational Status</span>
                                        <StatusBadge status={lib.status ?? 'unknown'} size="sm" />
                                      </div>
                                      <div className="pt-2 border-t border-slate-100">
                                        <p className="text-xs text-slate-500">Deadline</p>
                                        <p className="text-sm font-medium text-slate-800">{lib.deadline_date ?? 'Not set'}</p>
                                        {lib.deadline_notes && <p className="text-xs text-slate-500 mt-0.5">{lib.deadline_notes}</p>}
                                      </div>
                                    </div>
                                  </div>

                                  <div className="rounded-lg border border-slate-200 bg-white p-4 lg:col-span-2">
                                    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-3">Technical View</p>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                      {([
                                        ['SDK Name',       lib.sdk_name || '\u2014'],
                                        ['Package',        lib.package || '\u2014'],
                                        ['Platform',       lib.platform || '\u2014'],
                                        ['Registry',       lib.registry || '\u2014'],
                                        ['Framework',      lib.framework_language || '\u2014'],
                                        ['Current Version', lib.current_version || '\u2014'],
                                        ['Latest Version',  lib.latest_version || '\u2014'],
                                        ['Alert Priority',  lib.alert_priority || '\u2014'],
                                      ] as [string, string][]).map(([k, v]) => (
                                        <div key={k} className="rounded-md bg-slate-50 border border-slate-100 px-3 py-2">
                                          <p className="text-[11px] text-slate-500">{k}</p>
                                          <p className="text-sm font-medium text-slate-800 break-all">{v}</p>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                </div>

                                <div className="rounded-lg border border-slate-200 bg-white p-4">
                                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Notes & Context</p>
                                  <p className="text-sm text-slate-700">{buildWhyNotes(lib)}</p>
                                </div>
                                {lib.repo_url && (
                                  <div className="col-span-full">
                                    <p className="text-xs text-slate-400 mb-0.5">Repository / Release URL</p>
                                    <a href={lib.repo_url} target="_blank" rel="noreferrer"
                                      className="inline-flex items-center gap-1 text-xs text-primary-600 hover:underline break-all">
                                      <ExternalLink size={11} /> {lib.repo_url}
                                    </a>
                                  </div>
                                )}
                              </div>
                            )}

                            {activeTab === 'recommendation' && (
                              <div>
                                {recMap[lib.id] ? (
                                  <div className="space-y-3">
                                    <div className={`px-4 py-3 rounded-lg ${recMap[lib.id].upgrade_recommended === 'Yes' ? 'bg-green-50 border border-green-200' : 'bg-amber-50 border border-amber-200'}`}>
                                      <p className="text-sm font-semibold">
                                        {recMap[lib.id].upgrade_recommended === 'Yes' ? '\u2705 Upgrade Recommended' : '\u26a0\ufe0f Upgrade Not Recommended'}
                                      </p>
                                      <p className="text-xs text-slate-600 mt-1">{recMap[lib.id].recommendation_summary}</p>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                      {([
                                        ['\u2705 Pros of Upgrading', recMap[lib.id].upgrade_pros],
                                        ['\u274c Cons of Upgrading', recMap[lib.id].upgrade_cons],
                                      ] as [string, string[]][]).map(([title, items]) => (
                                        <div key={title}>
                                          <p className="text-xs font-semibold text-slate-600 mb-1">{title}</p>
                                          <ul className="text-xs text-slate-600 list-disc pl-4 space-y-0.5">
                                            {items.map((item, idx) => <li key={idx}>{item}</li>)}
                                          </ul>
                                        </div>
                                      ))}
                                    </div>

                                    <div className="rounded-xl border border-slate-200 bg-white p-3">
                                      <div className="flex items-center justify-between gap-2 mb-2">
                                        <div className="flex items-center gap-2">
                                          <MessageSquare size={14} className="text-primary-600" />
                                          <p className="text-xs font-semibold text-slate-700 uppercase tracking-wide">Ask Doubt (This SDK)</p>
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                          <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${
                                            llmConnected
                                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                              : 'bg-red-50 text-red-700 border-red-200'
                                          }`}>
                                            {llmConnected ? 'LLM: Connected' : 'LLM: Unavailable'}
                                          </span>
                                          <span className="text-[10px] px-2 py-0.5 rounded-full border border-slate-200 bg-slate-50 text-slate-500">Non-persistent chat</span>
                                        </div>
                                      </div>

                                      <div className="flex flex-wrap gap-1.5 mb-3">
                                        {[
                                          'What is the main risk if we skip this upgrade?',
                                          'Give me a 3-step action plan for this SDK.',
                                          'How urgent is this based on current vs latest version?',
                                        ].map((suggestion) => (
                                          <button
                                            key={suggestion}
                                            type="button"
                                            className="text-[10px] px-2 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100"
                                            onClick={() => submitAssistQuestion(lib, suggestion)}
                                            disabled={assistLoadingMap[lib.id]}
                                          >
                                            <Sparkles size={10} className="inline mr-1" />
                                            {suggestion}
                                          </button>
                                        ))}
                                      </div>

                                      <div className="space-y-2 max-h-56 overflow-y-auto pr-1 rounded-xl border border-slate-100 bg-slate-50/60 p-2">
                                        {(assistChatMap[lib.id] || []).length === 0 ? (
                                          <p className="text-xs text-slate-500 bg-white border border-slate-200 rounded-lg px-3 py-2">
                                            Ask anything about this SDK recommendation. This works like a lightweight ChatGPT assistant and is not stored.
                                          </p>
                                        ) : (
                                          (assistChatMap[lib.id] || []).map((msg, idx) => (
                                            <div
                                              key={`${lib.id}-${idx}`}
                                              className={`rounded-lg px-3 py-2 text-xs ${
                                                msg.role === 'user'
                                                  ? 'bg-primary-600 text-white ml-7'
                                                  : 'bg-white border border-slate-200 text-slate-700 mr-7'
                                              }`}
                                            >
                                              <p className="font-semibold mb-0.5 flex items-center gap-1">
                                                {msg.role === 'user' ? 'You' : <><Bot size={11} /> Assist</>}
                                              </p>
                                              <p className="leading-relaxed">{msg.text}</p>
                                            </div>
                                          ))
                                        )}
                                        {assistLoadingMap[lib.id] && (
                                          <div className="rounded-lg px-3 py-2 text-xs bg-white border border-slate-200 text-slate-700 mr-7 animate-pulse">
                                            <p className="font-semibold mb-0.5 flex items-center gap-1">
                                              <Bot size={11} /> Assist
                                            </p>
                                            <p className="leading-relaxed">Typing...</p>
                                          </div>
                                        )}
                                      </div>

                                      <div className="mt-2 text-[10px] text-slate-500 flex flex-wrap gap-x-3 gap-y-1">
                                        {(() => {
                                          const m = assistUsageMap[lib.id]
                                          if (!m && assistErrorMap[lib.id]) return <span>No token usage recorded yet because the latest LLM call failed.</span>
                                          if (!m) return <span>Token usage will appear after first successful response.</span>
                                          return (
                                            <>
                                              <span>Calls: <strong className="text-slate-700">{m.calls}</strong></span>
                                              <span>Total Tokens: <strong className="text-slate-700">{m.totalTokens}</strong></span>
                                              <span>Prompt: <strong className="text-slate-700">{m.promptTokens}</strong></span>
                                              <span>Completion: <strong className="text-slate-700">{m.completionTokens}</strong></span>
                                              <span>Model: <strong className="text-slate-700">{m.lastModel ?? '—'}</strong></span>
                                              <span>Latency: <strong className="text-slate-700">{m.lastLatencyMs ?? '—'} ms</strong></span>
                                            </>
                                          )
                                        })()}
                                      </div>
                                      {assistErrorMap[lib.id] && (
                                        <p className="mt-1 text-[10px] text-red-600">{assistErrorMap[lib.id]}</p>
                                      )}

                                      <div className="mt-3 flex gap-2">
                                        <input
                                          className="input text-xs flex-1"
                                          value={assistInputMap[lib.id] || ''}
                                          onChange={(e) => setAssistInputMap((prev) => ({ ...prev, [lib.id]: e.target.value }))}
                                          placeholder="Ask a doubt about this SDK..."
                                          onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                              e.preventDefault()
                                              submitAssistQuestion(lib)
                                            }
                                          }}
                                        />
                                        <button
                                          type="button"
                                          className="btn-primary py-1.5 px-3 text-xs"
                                          onClick={() => submitAssistQuestion(lib)}
                                          disabled={!(assistInputMap[lib.id] || '').trim() || !!assistLoadingMap[lib.id]}
                                        >
                                          {assistLoadingMap[lib.id]
                                            ? <><Loader2 size={12} className="animate-spin" /> Asking...</>
                                            : <><Send size={12} /> Ask</>}
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                ) : (
                                  <p className="text-xs text-slate-400 text-center py-8">No recommendation yet \u2014 run the pipeline to generate AI recommendations.</p>
                                )}
                              </div>
                            )}

                            {activeTab === 'release_notes' && (
                              <VersionHistoryPanel
                                libId={lib.id}
                                currentVersion={lib.current_version}
                                latestVersion={lib.latest_version}
                                onVersionSet={(ver) => {
                                  setReviewVersionMap((prev) => ({ ...prev, [lib.id]: ver }))
                                }}
                                lcStatus={lcMap[String(lib.id)]?.status}
                                lcTargetVersion={lcMap[String(lib.id)]?.target_version}
                              />
                            )}
                          </div>

                          {/* Upgrade Review Queue — shows after explicit version selection OR when already In Progress */}
                          {(Boolean(reviewVersionMap[lib.id]) || lcMap[String(lib.id)]?.status === 'In Progress') && !hiddenQueues.has(lib.id) && (
                            <div className="mt-2 border-t border-slate-200 pt-3">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                                  <GitMerge size={11} /> Upgrade Review Queue
                                  {lcMap[String(lib.id)]?.status === 'In Progress' && !reviewVersionMap[lib.id] && (
                                    <span className="text-[10px] font-semibold text-orange-600 bg-orange-50 border border-orange-200 px-1.5 py-0.5 rounded-full ml-1">🔧 In Progress</span>
                                  )}
                                </span>
                                <button
                                  className="text-[10px] text-slate-400 hover:text-slate-600 px-1.5 py-0.5 rounded hover:bg-slate-100 transition-colors"
                                  onClick={() => setHiddenQueues(prev => new Set([...prev, lib.id]))}
                                  title="Hide upgrade review queue"
                                >
                                  ✕ Hide
                                </button>
                              </div>
                              <LifecycleReviewPanel
                                key={`lc-${lib.id}-${reviewVersionMap[lib.id] ?? lcMap[String(lib.id)]?.target_version ?? 'default'}`}
                                libId={lib.id}
                                latestVersion={lib.latest_version}
                                currentVersion={lib.current_version}
                                suggestedVersion={reviewVersionMap[lib.id] ?? lcMap[String(lib.id)]?.target_version ?? undefined}
                                onActiveSet={() => {
                                  setReviewVersionMap((prev) => { const n = { ...prev }; delete n[lib.id]; return n })
                                  setHiddenQueues(prev => { const n = new Set(prev); n.delete(lib.id); return n })
                                }}
                                onDecline={() => {
                                  setReviewVersionMap((prev) => { const n = { ...prev }; delete n[lib.id]; return n })
                                }}
                              />
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="p-12 text-center">
                <p className="text-slate-400 text-sm font-medium">No {platform} SDKs match your filters.</p>
                <button className="mt-2 text-xs text-primary-600 hover:underline"
                  onClick={() => { setSearch(''); setPriority('All') }}>Clear filters</button>
              </div>
            )}
          </div>
        </SectionCard>
      )}

      {showAddModal && (
        <AddLibraryModal editLib={editLib} onClose={() => { setShowAddModal(false); setEditLib(null) }} />
      )}
    </div>
  )
}

export default function Libraries() { return <LibraryMain /> }
