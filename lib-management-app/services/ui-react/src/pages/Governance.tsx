import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronUp, Search, CheckCircle, Clock, User, ArrowRight, AlertTriangle, ShieldCheck, Briefcase, CalendarClock } from 'lucide-react'
import StatusBadge from '../components/StatusBadge'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import { RowsPerPageControl, PaginatedSectionFooter } from '../components/PaginatedSectionControls'
import { lifecycleApi } from '../api/client'
import type { Lifecycle } from '../api/types'

type GovernanceCategory = 'executive' | 'sla' | 'portfolio'

const STATUSES = ['awaiting_review', 'Acknowledged', 'In Progress', 'Completed']
const STATUS_LABELS: Record<string, string> = {
  awaiting_review: 'Pending Approval',
  Acknowledged:    'Approved / In Deployment',
  'In Progress':   'In Progress',
  Completed:       'Completed',
}
const STATUS_COLORS: Record<string, string> = {
  awaiting_review: 'bg-amber-100 text-amber-800 border border-amber-200',
  Acknowledged:    'bg-blue-100 text-blue-800 border border-blue-200',
  'In Progress':   'bg-purple-100 text-purple-800 border border-purple-200',
  Completed:       'bg-green-100 text-green-800 border border-green-200',
}

function fmt(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

function isBusinessCritical(entry: Lifecycle): boolean {
  if (typeof entry.business_critical === 'boolean') return entry.business_critical
  const impact = (entry.update_needed ?? '').toLowerCase()
  const priority = (entry.priority ?? '').toLowerCase()
  return impact === 'mandatory' || impact === 'critical' || impact === 'high' || priority === 'high'
}

function confidenceFromLifecycle(entry: Lifecycle): { score: number; band: 'High' | 'Medium' | 'Low' } {
  if (typeof entry.confidence_score === 'number' && entry.confidence_band) {
    return {
      score: Math.max(0, Math.min(100, entry.confidence_score)),
      band: entry.confidence_band,
    }
  }

  let score = 45
  const urgency = (entry.update_needed ?? '').toLowerCase()

  if (['mandatory', 'critical'].includes(urgency)) score += 20
  else if (urgency === 'high') score += 14
  else if (urgency === 'moderate') score += 8

  if (entry.current_version && entry.latest_version && entry.current_version !== entry.latest_version) score += 12
  if ((entry.ai_summary ?? '').trim().length >= 40) score += 12
  if ((entry.priority ?? '').toLowerCase() === 'high') score += 6

  const bounded = Math.max(0, Math.min(100, score))
  if (bounded >= 75) return { score: bounded, band: 'High' }
  if (bounded >= 55) return { score: bounded, band: 'Medium' }
  return { score: bounded, band: 'Low' }
}

function isOverdue(entry: Lifecycle): boolean {
  if (!entry.target_date) return false
  const isDone = (entry.status ?? '').toLowerCase() === 'completed'
  if (isDone) return false
  const today = new Date()
  const due = new Date(entry.target_date)
  return due.getTime() < new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
}

function isDueInNextSevenDays(entry: Lifecycle): boolean {
  if (!entry.target_date) return false
  const isDone = (entry.status ?? '').toLowerCase() === 'completed'
  if (isDone) return false

  const today = new Date()
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const due = new Date(entry.target_date)
  const dueDay = new Date(due.getFullYear(), due.getMonth(), due.getDate())
  const sevenDaysMs = 7 * 24 * 60 * 60 * 1000
  const delta = dueDay.getTime() - startOfToday.getTime()

  return delta >= 0 && delta <= sevenDaysMs
}

function ownerOverdueSeverity(count: number): 'high' | 'medium' | 'none' {
  if (count >= 3) return 'high'
  if (count >= 1) return 'medium'
  return 'none'
}

// ── Per-SDK history row ────────────────────────────────────────────────────
function LibraryHistoryRow({ libId, entries }: { libId: number; entries: Lifecycle[] }) {
  const [expanded, setExpanded] = useState(false)

  const latest     = entries[0]
  const approvals  = entries.filter(e => e.status === 'Acknowledged' || e.status === 'Completed').length
  const isMandatory = isBusinessCritical(latest)
  const confidence = confidenceFromLifecycle(latest)
  const owner = latest.actioned_by ?? 'Unassigned'
  const targetWindow = latest.target_sprint || latest.target_date || 'Not committed'

  // Sort entries newest-first for the timeline
  const timeline = [...entries].sort((a, b) =>
    new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  )

  return (
    <div className={`border rounded-xl overflow-hidden ${isMandatory ? 'border-red-200' : 'border-slate-200'}`}>
      {/* Summary row */}
      <div
        className={`px-5 py-3.5 flex flex-wrap items-center gap-4 cursor-pointer hover:bg-slate-50 transition-colors ${
          isMandatory ? 'bg-red-50/40' : 'bg-white'
        }`}
        onClick={() => setExpanded(p => !p)}
      >
        {/* SDK name */}
        <div className="flex-1 min-w-[180px]">
          <p className="font-semibold text-slate-900 text-sm">
            {latest.sdk_name || latest.package || `SDK #${libId}`}
          </p>
          {latest.sdk_name && latest.package && (
            <p className="text-[11px] text-slate-400 font-mono truncate max-w-[200px]">{latest.package}</p>
          )}
        </div>

        {/* Platform */}
        <StatusBadge status={latest.platform ?? 'unknown'} size="sm" />

        {/* Latest version change */}
        <div className="flex items-center gap-1.5 font-mono text-xs text-slate-600 bg-slate-100 px-2.5 py-1 rounded-lg">
          <span>{latest.current_version ?? '?'}</span>
          <ArrowRight size={11} className="text-slate-400" />
          <span className="font-bold text-slate-800">{latest.latest_version ?? '?'}</span>
        </div>

        {/* Current status */}
        <span className={`text-[11px] font-semibold px-2.5 py-1 rounded-full ${STATUS_COLORS[latest.status] ?? 'bg-slate-100 text-slate-600'}`}>
          {STATUS_LABELS[latest.status] ?? latest.status}
        </span>

        <span className={`text-[11px] font-semibold px-2.5 py-1 rounded-full ${isMandatory ? 'bg-red-100 text-red-700 border border-red-200' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}>
          {isMandatory ? 'Business Critical' : 'Business Standard'}
        </span>

        <span className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border ${
          confidence.band === 'High'
            ? 'bg-green-100 text-green-700 border-green-200'
            : confidence.band === 'Medium'
              ? 'bg-amber-100 text-amber-700 border-amber-200'
              : 'bg-slate-100 text-slate-600 border-slate-200'
        }`}>
          Confidence {confidence.score}%
        </span>

        <span className="text-[11px] text-slate-600 bg-slate-50 border border-slate-200 px-2 py-1 rounded-lg">
          Owner: <span className="font-semibold">{owner}</span>
        </span>

        <span className="text-[11px] text-slate-600 bg-slate-50 border border-slate-200 px-2 py-1 rounded-lg">
          Target: <span className="font-semibold">{targetWindow}</span>
        </span>

        {/* Approval count badge */}
        <div className="flex items-center gap-1.5 text-xs">
          <CheckCircle size={13} className={approvals > 0 ? 'text-green-600' : 'text-slate-300'} />
          <span className={`font-bold ${approvals > 0 ? 'text-green-700' : 'text-slate-400'}`}>
            {approvals}×
          </span>
          <span className="text-slate-400">governance actions</span>
        </div>

        {/* Entry count + expand */}
        <div className="flex items-center gap-2 ml-auto">
          <span className="text-xs text-slate-400">{entries.length} entr{entries.length === 1 ? 'y' : 'ies'}</span>
          {expanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
        </div>
      </div>

      {/* Timeline */}
      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50 px-5 py-4">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-3">
            Decision Trail ({entries.length} entries)
          </p>
          <div className="space-y-2">
            {timeline.map((e, i) => (
              <div key={e.id}
                className={`rounded-lg border px-4 py-3 bg-white flex flex-wrap gap-x-6 gap-y-1 items-start ${
                  STATUS_COLORS[e.status] ? '' : 'border-slate-200'
                }`}>
                {/* Status pill */}
                <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${STATUS_COLORS[e.status] ?? 'bg-slate-100 text-slate-600'}`}>
                  {STATUS_LABELS[e.status] ?? e.status}
                </span>

                {/* Version change */}
                <div className="flex items-center gap-1 font-mono text-xs">
                  <span className="text-slate-500">{e.current_version ?? '?'}</span>
                  <ArrowRight size={10} className="text-slate-400" />
                  <span className="font-bold text-slate-800">
                    {e.target_version || e.latest_version || '?'}
                  </span>
                  {e.target_version && e.target_version !== e.latest_version && (
                    <span className="text-[10px] text-slate-400 ml-1">(target)</span>
                  )}
                </div>

                {/* Who */}
                <div className="flex items-center gap-1 text-xs text-slate-600">
                  <User size={11} className="text-slate-400" />
                  <span>{e.actioned_by ?? '—'}</span>
                </div>

                {/* When */}
                <div className="flex items-center gap-1 text-xs text-slate-400">
                  <Clock size={11} />
                  <span>{fmt(e.updated_at)}</span>
                </div>

                {/* Notes */}
                {e.skip_reason && (
                  <p className="w-full text-xs text-slate-500 italic">📝 Decision note: {e.skip_reason}</p>
                )}

                {/* Latest badge */}
                {i === 0 && (
                  <span className="text-[10px] bg-primary-100 text-primary-700 px-1.5 py-0.5 rounded ml-auto">current</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Governance page ───────────────────────────────────────────────────────
export default function Governance() {
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterConfidence, setFilterConfidence] = useState('all')
  const [activeCategory, setActiveCategory] = useState<GovernanceCategory>('portfolio')
  const [portfolioPage, setPortfolioPage] = useState(1)
  const [portfolioPageSize, setPortfolioPageSize] = useState(8)

  const { data, isLoading } = useQuery({
    queryKey: ['lifecycle-all'],
    queryFn: () => lifecycleApi.list({ limit: 500 }),
  })
  const entries: Lifecycle[] = Array.isArray(data?.data) ? (data!.data as Lifecycle[]) : []

  const grouped = STATUSES.reduce<Record<string, Lifecycle[]>>((acc, s) => {
    acc[s] = entries.filter((e) => e.status === s)
    return acc
  }, {})

  // Group all entries by library_id
  const byLibrary = useMemo(() => {
    const map: Record<number, Lifecycle[]> = {}
    for (const e of entries) {
      if (!map[e.library_id]) map[e.library_id] = []
      map[e.library_id].push(e)
    }
    // Sort each library's entries newest-first
    for (const k of Object.keys(map)) {
      map[+k].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    }
    return map
  }, [entries])

  const filteredLibIds = useMemo(() => {
    return Object.keys(byLibrary)
      .map(Number)
      .filter((libId) => {
        const libEntries = byLibrary[libId]
        const latest = libEntries[0]
        const matchSearch = !search ||
          (latest.sdk_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (latest.package  ?? '').toLowerCase().includes(search.toLowerCase())
        const matchStatus = filterStatus === 'all' || libEntries.some(e => e.status === filterStatus)
        const conf = confidenceFromLifecycle(latest).score
        const matchConfidence = filterConfidence === 'all'
          || (filterConfidence === 'high' && conf >= 75)
          || (filterConfidence === 'medium' && conf >= 55 && conf < 75)
          || (filterConfidence === 'low' && conf < 55)
        return matchSearch && matchStatus && matchConfidence
      })
      .sort((a, b) => {
        // Sort: mandatory first, then by most recent activity
        const am = (byLibrary[a][0].update_needed ?? '').toLowerCase() === 'mandatory' ? 0 : 1
        const bm = (byLibrary[b][0].update_needed ?? '').toLowerCase() === 'mandatory' ? 0 : 1
        return am !== bm ? am - bm : new Date(byLibrary[b][0].updated_at).getTime() - new Date(byLibrary[a][0].updated_at).getTime()
      })
  }, [byLibrary, search, filterStatus, filterConfidence])

  const portfolioTotalPages = Math.max(1, Math.ceil(filteredLibIds.length / portfolioPageSize))
  const safePortfolioPage = Math.min(portfolioPage, portfolioTotalPages)
  const portfolioStart = (safePortfolioPage - 1) * portfolioPageSize
  const portfolioEnd = Math.min(portfolioStart + portfolioPageSize, filteredLibIds.length)
  const pagedLibIds = filteredLibIds.slice(portfolioStart, portfolioEnd)

  useEffect(() => {
    setPortfolioPage(1)
  }, [search, filterStatus, filterConfidence, portfolioPageSize])

  useEffect(() => {
    if (portfolioPage > portfolioTotalPages) setPortfolioPage(portfolioTotalPages)
  }, [portfolioPage, portfolioTotalPages])

  const totalApprovals = entries.filter(e => e.status === 'Acknowledged' || e.status === 'Completed').length
  const latestItems = Object.values(byLibrary).map((x) => x[0])
  const criticalExposure = latestItems.filter(isBusinessCritical).length
  const pendingApprovals = latestItems.filter((x) => x.status === 'awaiting_review').length
  const assignedOwners = latestItems.filter((x) => (x.actioned_by ?? '').trim().length > 0).length
  const ownerCoverage = latestItems.length > 0 ? Math.round((assignedOwners / latestItems.length) * 100) : 0
  const overdueTargets = latestItems.filter(isOverdue).length
  const dueSoon = latestItems.filter(isDueInNextSevenDays).length
  const unassignedCritical = latestItems.filter((x) => isBusinessCritical(x) && (x.actioned_by ?? '').trim().length === 0).length
  const overdueByOwner = useMemo(() => {
    const counts = latestItems.filter(isOverdue).reduce<Record<string, number>>((acc, item) => {
      const owner = (item.actioned_by ?? '').trim() || 'Unassigned'
      acc[owner] = (acc[owner] ?? 0) + 1
      return acc
    }, {})
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
  }, [latestItems])

  return (
    <div className="space-y-4">
      <div className="page-header">
        <div>
          <h1 className="page-title">Upgrade Governance</h1>
          <p className="page-subtitle">
            Executive control plane for upgrade decisions — {Object.keys(byLibrary).length} SDKs · {entries.length} lifecycle events · {totalApprovals} approved decisions
          </p>
        </div>
      </div>

      <SectionCard cardClassName="card p-4">
        <SectionBand
          title="Governance Category Navigator"
          subtitle="Open one governance category at a time for focused enterprise review."
          className="mb-3"
        />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {[
            { key: 'executive' as const, label: 'Executive Snapshot' },
            { key: 'sla' as const, label: 'SLA & Risk Watchlist' },
            { key: 'portfolio' as const, label: 'Portfolio Ledger' },
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

      {/* Executive governance snapshot */}
      {activeCategory === 'executive' && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="card p-4 text-center border border-red-200 bg-red-50">
            <p className="text-2xl font-bold text-red-700">{criticalExposure}</p>
            <p className="text-xs font-medium text-red-600 mt-1 inline-flex items-center gap-1"><AlertTriangle size={12} /> Critical Exposure</p>
          </div>
          <div className="card p-4 text-center border border-amber-200 bg-amber-50">
            <p className="text-2xl font-bold text-amber-700">{pendingApprovals}</p>
            <p className="text-xs font-medium text-amber-700 mt-1 inline-flex items-center gap-1"><Briefcase size={12} /> Pending Decisions</p>
          </div>
          <div className="card p-4 text-center border border-green-200 bg-green-50">
            <p className="text-2xl font-bold text-green-700">{ownerCoverage}%</p>
            <p className="text-xs font-medium text-green-700 mt-1 inline-flex items-center gap-1"><ShieldCheck size={12} /> Ownership Coverage</p>
          </div>
          <div className="card p-4 text-center border border-rose-200 bg-rose-50">
            <p className="text-2xl font-bold text-rose-700">{overdueTargets}</p>
            <p className="text-xs font-medium text-rose-700 mt-1 inline-flex items-center gap-1"><CalendarClock size={12} /> Overdue Targets</p>
          </div>
        </div>
      )}

      {/* Governance SLA strip */}
      {activeCategory === 'sla' && <div className="card p-4 border border-slate-200 bg-slate-50/70">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 className="text-sm font-semibold text-slate-900">Governance SLA</h2>
          <p className="text-xs text-slate-500">Leadership watchlist for the next 7 days</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="rounded-lg border border-sky-200 bg-sky-50 p-3">
            <p className="text-xs font-medium text-sky-700">Due in 7 Days</p>
            <p className="text-2xl font-bold text-sky-800 mt-1">{dueSoon}</p>
            <p className="text-[11px] text-sky-700 mt-1">Open items with target dates in the next week</p>
          </div>

          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-medium text-rose-700">Overdue by Owner</p>
              <span className="text-[10px] text-slate-500">Red: 3+ · Amber: 1-2</span>
            </div>
            {overdueByOwner.length === 0 ? (
              <p className="text-[11px] text-rose-700 mt-2">No overdue items in the current portfolio.</p>
            ) : (
              <div className="mt-2 space-y-1.5">
                {overdueByOwner.map(([owner, count]) => (
                    <div
                      key={owner}
                      className={`flex items-center justify-between text-xs rounded px-2 py-1 border ${
                        ownerOverdueSeverity(count) === 'high'
                          ? 'bg-red-50 border-red-200'
                          : ownerOverdueSeverity(count) === 'medium'
                            ? 'bg-amber-50 border-amber-200'
                            : 'bg-slate-50 border-slate-200'
                      }`}
                    >
                      <span
                        className={`truncate pr-2 ${
                          ownerOverdueSeverity(count) === 'high'
                            ? 'text-red-700'
                            : ownerOverdueSeverity(count) === 'medium'
                              ? 'text-amber-700'
                              : 'text-slate-700'
                        }`}
                      >
                        {owner}
                      </span>
                      <span
                        className={`font-semibold ${
                          ownerOverdueSeverity(count) === 'high'
                            ? 'text-red-700'
                            : ownerOverdueSeverity(count) === 'medium'
                              ? 'text-amber-700'
                              : 'text-slate-600'
                        }`}
                      >
                        {count}
                      </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs font-medium text-amber-700">Unassigned Critical Items</p>
            <p className="text-2xl font-bold text-amber-800 mt-1">{unassignedCritical}</p>
            <p className="text-[11px] text-amber-700 mt-1">Critical decisions without accountable ownership</p>
          </div>
        </div>
      </div>}

      {/* Status summary — 4 workflow stages */}
      {activeCategory === 'portfolio' && <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {STATUSES.map((s) => (
          <div key={s}
            className={`card p-4 text-center cursor-pointer transition-all hover:shadow-md ${filterStatus === s ? 'ring-2 ring-primary-400' : ''}`}
            onClick={() => setFilterStatus(prev => prev === s ? 'all' : s)}>
            <p className="text-2xl font-bold text-slate-900">{grouped[s]?.length ?? 0}</p>
            <p className="text-xs font-medium text-slate-500 mt-1">{STATUS_LABELS[s]}</p>
          </div>
        ))}
      </div>}

      {/* Filters */}
      {activeCategory === 'portfolio' && <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input pl-9" placeholder="Search by SDK, package, or accountable owner…"
            value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="select w-auto text-xs" value={filterConfidence} onChange={(e) => setFilterConfidence(e.target.value)}>
          <option value="all">All confidence</option>
          <option value="high">High (≥75)</option>
          <option value="medium">Medium (55-74)</option>
          <option value="low">Low (&lt;55)</option>
        </select>
        {(search || filterStatus !== 'all' || filterConfidence !== 'all') && (
          <button className="btn-secondary py-1.5 text-xs"
            onClick={() => { setSearch(''); setFilterStatus('all'); setFilterConfidence('all') }}>
            ✕ Clear
          </button>
        )}
        <span className="text-xs text-slate-400 ml-auto">{filteredLibIds.length} portfolio items</span>
      </div>}

      {activeCategory === 'portfolio' && <SectionBand
        title="Governance Portfolio Ledger"
        subtitle="Paginated enterprise review queue with ownership, target windows, and full decision trails per SDK."
      />}

      {/* Per-SDK history list */}
      {activeCategory === 'portfolio' && (isLoading ? (
        <div className="card p-8 text-center text-slate-400">Loading…</div>
      ) : filteredLibIds.length === 0 ? (
        <div className="card p-8 text-center text-slate-400">No entries match your filters.</div>
      ) : (
        <SectionCard cardClassName="card p-4">
          <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
            <span>Showing {filteredLibIds.length ? portfolioStart + 1 : 0}-{portfolioEnd} of {filteredLibIds.length}</span>
            <RowsPerPageControl
              pageSize={portfolioPageSize}
              options={[8, 12, 20]}
              onChange={(value) => {
                setPortfolioPageSize(value)
                setPortfolioPage(1)
              }}
            />
          </div>
          <div className="space-y-2">
            {pagedLibIds.map((libId) => (
              <LibraryHistoryRow key={libId} libId={libId} entries={byLibrary[libId]} />
            ))}
          </div>
          <PaginatedSectionFooter
            page={safePortfolioPage}
            totalPages={portfolioTotalPages}
            onPrev={() => setPortfolioPage((p) => Math.max(1, p - 1))}
            onNext={() => setPortfolioPage((p) => Math.min(portfolioTotalPages, p + 1))}
          />
        </SectionCard>
      ))}
    </div>
  )
}

