import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Filter, RefreshCw, Search } from 'lucide-react'
import ExecutiveTriad from '../components/ExecutiveTriad'
import { PaginatedSectionFooter, PaginatedSectionHeader } from '../components/PaginatedSectionControls'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import { auditApi, parseApiError } from '../api/client'
import type { AuditLogEntry } from '../api/types'

const FIELD_LABELS: Record<string, string> = {
  current_version: 'Current Version',
  latest_version: 'Latest Version',
  update_needed: 'Update Status',
  status: 'SDK Status',
  priority: 'Priority',
  alert_priority: 'Alert Priority',
  comments: 'Comments',
  deprecation_notes: 'Deprecation Notes',
  deadline_date: 'Deadline',
  lifecycle_complete: 'Lifecycle Completed',
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

function toCsv(rows: Record<string, string>[]): string {
  if (!rows.length) return ''
  const headers = Object.keys(rows[0])
  const esc = (v: string) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const body = rows.map((r) => headers.map((h) => esc(r[h] ?? '')).join(','))
  return [headers.join(','), ...body].join('\n')
}

function downloadCsv(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default function Audit() {
  const [sdkId, setSdkId] = useState('')
  const [changedBy, setChangedBy] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [entryType, setEntryType] = useState<'all' | 'manual' | 'auto'>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  const [appliedFilters, setAppliedFilters] = useState({
    sdkId: '',
    changedBy: '',
    dateFrom: '',
    dateTo: '',
    entryType: 'all' as 'all' | 'manual' | 'auto',
  })

  const { data, isLoading, refetch, error, isFetching } = useQuery({
    queryKey: ['audit-log', appliedFilters],
    queryFn: async () => {
      const params: Record<string, string | number> = { limit: 500 }
      if (appliedFilters.sdkId.trim()) params.library_id = Number(appliedFilters.sdkId)
      if (appliedFilters.changedBy.trim()) params.updated_by = appliedFilters.changedBy.trim()
      if (appliedFilters.dateFrom) params.date_from = appliedFilters.dateFrom
      if (appliedFilters.dateTo) params.date_to = appliedFilters.dateTo
      return auditApi.list(params)
    },
  })

  const allEntries: AuditLogEntry[] = Array.isArray(data?.data) ? (data.data as AuditLogEntry[]) : []

  const entries = useMemo(() => {
    if (appliedFilters.entryType === 'all') return allEntries
    return allEntries.filter((e) => (e.update_type ?? '').toLowerCase() === appliedFilters.entryType)
  }, [allEntries, appliedFilters.entryType])

  const uniqueUsers = useMemo(() => new Set(entries.map((e) => e.updated_by || '')).size, [entries])
  const uniqueSdks = useMemo(() => new Set(entries.map((e) => e.library_id)).size, [entries])
  const manualCount = useMemo(() => entries.filter((e) => (e.update_type ?? '').toLowerCase() === 'manual').length, [entries])
  const autoCount = entries.length - manualCount
  const reasonCompleteness = entries.length > 0
    ? Math.round((entries.filter((e) => (e.reason ?? '').trim().length > 0).length / entries.length) * 100)
    : 100
  const traceCompleteness = entries.length > 0
    ? Math.round((entries.filter((e) => (e.updated_by ?? '').trim().length > 0 && (e.field_changed ?? '').trim().length > 0 && (e.updated_at ?? '').trim().length > 0).length / entries.length) * 100)
    : 100

  const missingReasonCount = useMemo(() => entries.filter((e) => (e.reason ?? '').trim().length === 0).length, [entries])
  const missingOwnerCount = useMemo(() => entries.filter((e) => (e.updated_by ?? '').trim().length === 0).length, [entries])
  const missingTargetDateEvidenceCount = useMemo(() => entries.filter((e) => {
    const field = (e.field_changed ?? '').toLowerCase()
    const isTargetField = ['deadline_date', 'target_date'].includes(field)
    return isTargetField && (e.new_value ?? '').trim().length === 0
  }).length, [entries])

  const qualityFlaggedAll = useMemo(() => entries
    .filter((e) => {
      const missingReason = (e.reason ?? '').trim().length === 0
      const missingOwner = (e.updated_by ?? '').trim().length === 0
      const missingTargetDate = ['deadline_date', 'target_date'].includes((e.field_changed ?? '').toLowerCase())
        && (e.new_value ?? '').trim().length === 0
      return missingReason || missingOwner || missingTargetDate
    })
    .map((e) => ({
      id: e.id,
      sdk: e.sdk_name || e.package || `ID:${e.library_id}`,
      field: FIELD_LABELS[e.field_changed || ''] || e.field_changed || 'Unknown field',
      missingReason: (e.reason ?? '').trim().length === 0,
      missingOwner: (e.updated_by ?? '').trim().length === 0,
      missingTargetDate: ['deadline_date', 'target_date'].includes((e.field_changed ?? '').toLowerCase())
        && (e.new_value ?? '').trim().length === 0,
    })), [entries])

  const qualityFlags = useMemo(() => qualityFlaggedAll.slice(0, 10), [qualityFlaggedAll])

  const topFlaggedFields = useMemo(() => {
    const byField: Record<string, number> = {}
    for (const row of qualityFlaggedAll) {
      byField[row.field] = (byField[row.field] ?? 0) + 1
    }
    return Object.entries(byField)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([field, count]) => ({ field, count }))
  }, [qualityFlaggedAll])

  const tableRows = useMemo(() => entries.map((e) => ({
    Timestamp: formatDateTime(e.updated_at),
    SDK: e.sdk_name || e.package || `ID:${e.library_id}`,
    'Changed By': e.updated_by || '—',
    Type: e.update_type || '—',
    Field: FIELD_LABELS[e.field_changed || ''] || e.field_changed || '—',
    From: e.old_value || '—',
    To: e.new_value || '—',
    Reason: (e.reason || '—').slice(0, 120),
  })), [entries])

  const totalPages = Math.max(1, Math.ceil(tableRows.length / pageSize))
  const startIndex = (page - 1) * pageSize
  const endIndex = Math.min(startIndex + pageSize, tableRows.length)
  const pageRows = tableRows.slice(startIndex, endIndex)

  useEffect(() => {
    setPage(1)
  }, [appliedFilters, pageSize])

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  const onApplyFilters = () => {
    setAppliedFilters({
      sdkId,
      changedBy,
      dateFrom,
      dateTo,
      entryType,
    })
  }

  const onResetFilters = () => {
    setSdkId('')
    setChangedBy('')
    setDateFrom('')
    setDateTo('')
    setEntryType('all')
    setPage(1)
    setAppliedFilters({ sdkId: '', changedBy: '', dateFrom: '', dateTo: '', entryType: 'all' })
  }

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title">Application Audit Trail</h1>
          <p className="page-subtitle">Immutable change history for SDK, lifecycle, and governance decisions</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary py-1.5 text-xs" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} /> Refresh
          </button>
          <button
            className="btn-primary py-1.5 text-xs"
            onClick={() => downloadCsv('audit_log.csv', toCsv(tableRows))}
            disabled={tableRows.length === 0}
          >
            <Download size={12} /> Export CSV
          </button>
        </div>
      </div>

      <ExecutiveTriad
        impact={`${entries.length} change events recorded. ${manualCount} manual interventions and ${autoCount} automated updates.`}
        owner="Governance & Compliance Team"
        nextAction={entries.length > 0 ? 'Review high-impact manual updates and validate reasons against policy.' : 'Run pipeline or update SDK records to generate auditable events.'}
        tone={manualCount > 0 ? 'warning' : 'neutral'}
      />

      <SectionBand
        title="Audit Control Center"
        subtitle="Filter scope, review executive metrics, and inspect event-level evidence with paging controls."
      />

      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Filter size={14} /> Audit Filters
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">SDK ID</label>
            <input className="input" value={sdkId} onChange={(e) => setSdkId(e.target.value)} placeholder="e.g. 1" />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Changed By</label>
            <input className="input" value={changedBy} onChange={(e) => setChangedBy(e.target.value)} placeholder="username" />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">From Date</label>
            <input className="input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">To Date</label>
            <input className="input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Entry Type</label>
            <select className="select" value={entryType} onChange={(e) => setEntryType(e.target.value as 'all' | 'manual' | 'auto')}>
              <option value="all">All</option>
              <option value="manual">Manual</option>
              <option value="auto">Auto</option>
            </select>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-primary py-1.5 text-xs" onClick={onApplyFilters}><Search size={12} /> Apply Filters</button>
          <button className="btn-secondary py-1.5 text-xs" onClick={onResetFilters}>Reset</button>
        </div>
      </div>

      <SectionBand
        title="Audit Intelligence Snapshot"
        subtitle="Current event volume, contributor spread, and manual-vs-automation posture."
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-slate-800">{entries.length}</p>
          <p className="text-xs text-slate-500 mt-1">Total Changes</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-blue-700">{uniqueSdks}</p>
          <p className="text-xs text-slate-500 mt-1">SDKs Affected</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-amber-700">{uniqueUsers}</p>
          <p className="text-xs text-slate-500 mt-1">Contributors</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-green-700">{manualCount} / {autoCount}</p>
          <p className="text-xs text-slate-500 mt-1">Manual / Auto</p>
        </div>
      </div>

      <SectionCard cardClassName="card p-4">
        <SectionBand
          title="Audit Quality Metrics"
          subtitle="Reason and action-trace completeness to improve compliance readiness."
          className="mb-3"
        />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-center">
            <p className="text-xl font-bold text-slate-800">{reasonCompleteness}%</p>
            <p className="text-[11px] text-slate-500">Reason Completeness</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-center">
            <p className="text-xl font-bold text-slate-800">{traceCompleteness}%</p>
            <p className="text-[11px] text-slate-500">Action Trace Completeness</p>
          </div>
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-center">
            <p className="text-xl font-bold text-rose-700">{missingReasonCount}</p>
            <p className="text-[11px] text-rose-600">Missing Reason</p>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-center">
            <p className="text-xl font-bold text-amber-700">{qualityFlaggedAll.length}</p>
            <p className="text-[11px] text-amber-600">Flagged Actions</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Missing owner evidence</p>
            <p className="text-lg font-bold text-slate-800">{missingOwnerCount}</p>
            <p className="text-[10px] text-slate-400">Coverage: {entries.length > 0 ? Math.max(0, 100 - Math.round((missingOwnerCount / entries.length) * 100)) : 100}%</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Missing target-date evidence</p>
            <p className="text-lg font-bold text-slate-800">{missingTargetDateEvidenceCount}</p>
            <p className="text-[10px] text-slate-400">For deadline/target field changes only</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Evidence complete actions</p>
            <p className="text-lg font-bold text-green-700">{Math.max(0, entries.length - qualityFlaggedAll.length)}</p>
            <p className="text-[10px] text-slate-400">All required note/owner/target evidence present</p>
          </div>
        </div>

        {topFlaggedFields.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 mb-3">
            <p className="text-xs font-semibold text-slate-700 mb-2">Top flagged fields</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
              {topFlaggedFields.map((row) => (
                <div key={row.field} className="text-xs flex items-center justify-between border border-slate-200 rounded px-2 py-1 bg-white">
                  <span className="text-slate-600">{row.field}</span>
                  <span className="font-semibold text-amber-700">{row.count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {qualityFlags.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs font-semibold text-amber-700 mb-2">Actions requiring evidence completion</p>
            <div className="space-y-1.5">
              {qualityFlags.map((f) => (
                <div key={f.id} className="text-xs flex items-center justify-between border border-amber-200 rounded px-2 py-1 bg-white">
                  <span className="text-slate-700 truncate pr-2">{f.sdk}</span>
                  <span className="text-amber-700 font-medium">
                    {f.missingReason ? 'note ' : ''}
                    {f.missingOwner ? 'owner ' : ''}
                    {f.missingTargetDate ? 'target-date' : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </SectionCard>

      <SectionBand
        title="Audit Event Ledger"
        subtitle="Detailed change log with pagination for compliance review sessions."
      />

      {error ? (
        <div className="card p-5 text-sm text-red-700 bg-red-50 border-red-200">
          Failed to load audit log: {parseApiError(error, 'Unknown error')}
        </div>
      ) : isLoading ? (
        <div className="card p-8 text-center text-slate-400">Loading audit log…</div>
      ) : tableRows.length === 0 ? (
        <div className="card p-8 text-center text-slate-500">
          <p className="font-medium">No audit events found for the selected filters.</p>
          <p className="text-xs mt-1 text-slate-400">Audit events are generated by SDK edits, governance decisions, and scheduler updates.</p>
        </div>
      ) : (
        <SectionCard
          cardClassName="card overflow-hidden"
          header={{
            title: 'Audit Events',
            totalItems: tableRows.length,
            startIndex,
            endIndex,
            pageSize,
            pageSizeOptions: [10, 25, 50, 100],
            onPageSizeChange: (value) => setPageSize(value),
          }}
          footer={{
            page,
            totalPages,
            onPrev: () => setPage((p) => Math.max(1, p - 1)),
            onNext: () => setPage((p) => Math.min(totalPages, p + 1)),
          }}
        >
          <div className="overflow-auto">
            <table className="w-full table-base">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>SDK</th>
                  <th>Changed By</th>
                  <th>Type</th>
                  <th>Field</th>
                  <th>From</th>
                  <th>To</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row, idx) => (
                  <tr key={`${row.Timestamp}-${row.SDK}-${idx}`}>
                    <td className="whitespace-nowrap">{row.Timestamp}</td>
                    <td>{row.SDK}</td>
                    <td>{row['Changed By']}</td>
                    <td>{row.Type}</td>
                    <td>{row.Field}</td>
                    <td className="max-w-[200px] truncate" title={row.From}>{row.From}</td>
                    <td className="max-w-[200px] truncate" title={row.To}>{row.To}</td>
                    <td className="max-w-[260px] truncate" title={row.Reason}>{row.Reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  )
}
