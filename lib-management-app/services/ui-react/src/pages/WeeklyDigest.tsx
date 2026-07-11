import { useQuery } from '@tanstack/react-query'
import { Download, Printer } from 'lucide-react'
import { businessApi, parseApiError } from '../api/client'
import type { WeeklyDigestSummary } from '../api/types'

function toCsv(rows: Record<string, string>[]): string {
  if (!rows.length) return ''
  const headers = Object.keys(rows[0])
  const esc = (v: string) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const body = rows.map((r) => headers.map((h) => esc(r[h] ?? '')).join(','))
  return [headers.join(','), ...body].join('\n')
}

function downloadFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default function WeeklyDigest() {
  const {
    data: digest,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery<WeeklyDigestSummary>({
    queryKey: ['weekly-digest-backend'],
    queryFn: async () => {
      const resp = await businessApi.weeklyDigest()
      // Handle either axios response shape ({ data }) or already-unwrapped payload.
      const payload = (resp?.data ?? resp) as WeeklyDigestSummary | undefined
      if (!payload || !payload.generated_at) {
        throw new Error('Weekly digest payload is missing or invalid')
      }
      return payload
    },
    staleTime: 60_000,
  })

  const csvRows = digest ? [
    {
      GeneratedAt: digest.generated_at,
      PortfolioRiskTrendPct: String(digest.portfolio_risk_trend_pct),
      ApprovalsProcessed7d: String(digest.approvals_processed_7d),
      OverdueNow: String(digest.overdue_now),
      DueWithin7d: String(digest.due_7d),
      DueWithin30d: String(digest.due_30d),
      PipelineReliability7dPct: String(digest.pipeline_reliability_7d_pct),
      NotificationHealthPct: String(digest.notification_health_pct),
      NotificationRetryCount: String(digest.notification_retry_count),
      SlaCompliancePct: String(digest.sla_compliance_pct),
      PipelineCompleted7d: String(digest.pipeline_by_status_7d.completed),
      PipelineFailed7d: String(digest.pipeline_by_status_7d.failed),
      PipelinePartial7d: String(digest.pipeline_by_status_7d.partial),
      ApprovalsCompleted7d: String(digest.approvals_by_status_7d.completed),
      ApprovalsAcknowledged7d: String(digest.approvals_by_status_7d.acknowledged),
      ApprovalsInProgress7d: String(digest.approvals_by_status_7d.inProgress),
    },
  ] : []

  return (
    <div className="space-y-4 print:space-y-2">
      <div className="page-header print:hidden">
        <div>
          <h1 className="page-title">Executive Weekly Digest</h1>
          <p className="page-subtitle">Print-friendly governance snapshot for leadership review.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary py-1.5 text-xs" onClick={() => window.print()}>
            <Printer size={12} /> Print
          </button>
          <button
            className="btn-secondary py-1.5 text-xs"
            disabled={!digest}
            onClick={() => {
              if (!digest) return
              downloadFile('executive_weekly_digest.json', JSON.stringify(digest, null, 2), 'application/json')
            }}
          >
            <Download size={12} /> JSON
          </button>
          <button
            className="btn-primary py-1.5 text-xs"
            disabled={!digest}
            onClick={() => {
              if (!digest) return
              downloadFile('executive_weekly_digest.csv', toCsv(csvRows), 'text/csv;charset=utf-8;')
            }}
          >
            <Download size={12} /> CSV
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-600">Loading weekly digest from backend...</p>
        </div>
      )}

      {!isLoading && isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-semibold text-red-700">Failed to load weekly digest.</p>
          <p className="text-xs text-red-600 mt-1">{parseApiError(error, 'Unable to fetch digest data')}</p>
          <button className="btn-secondary py-1.5 text-xs mt-3" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}

      {!isLoading && !isError && digest && (

      <div className="bg-white border border-slate-200 rounded-xl p-5 print:border-0 print:rounded-none print:p-0">
        <div className="mb-4">
          <h2 className="text-lg font-bold text-slate-800">Leadership Governance Digest</h2>
          <p className="text-xs text-slate-500">Generated: {new Date(digest.generated_at).toLocaleString()}</p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <DigestTile label="Portfolio Risk Trend" value={`${digest.portfolio_risk_trend_pct}%`} />
          <DigestTile label="Approvals Processed (7d)" value={String(digest.approvals_processed_7d)} />
          <DigestTile label="Overdue Movement" value={`${digest.overdue_now} now`} />
          <DigestTile label="Pipeline Reliability" value={`${digest.pipeline_reliability_7d_pct}%`} />
          <DigestTile label="Notification Health" value={`${digest.notification_health_pct}%`} />
          <DigestTile label="Notification Retries" value={String(digest.notification_retry_count)} />
        </div>

        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <p className="text-xs font-semibold text-slate-700 mb-2">Leadership Summary</p>
          <div className="space-y-1.5 text-xs text-slate-600">
            <p>
              Portfolio risk is <strong>{digest.portfolio_risk_trend_pct}%</strong> with <strong>{digest.overdue_now}</strong> overdue SLA items.
            </p>
            <p>
              Pipeline reliability in the last 7 days is <strong>{digest.pipeline_reliability_7d_pct}%</strong> ({digest.pipeline_by_status_7d.completed} completed, {digest.pipeline_by_status_7d.failed} failed, {digest.pipeline_by_status_7d.partial} partial).
            </p>
            <p>
              Notification health is <strong>{digest.notification_health_pct}%</strong> with <strong>{digest.notification_retry_count}</strong> retry attempts.
            </p>
          </div>
        </div>

        <div className="mt-4 border border-slate-200 rounded-lg p-3">
          <p className="text-xs font-semibold text-slate-700 mb-2">SLA Position</p>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">Overdue: <strong>{digest.overdue_now}</strong></div>
            <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">Due ≤7d: <strong>{digest.due_7d}</strong></div>
            <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">Due ≤30d: <strong>{digest.due_30d}</strong></div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="text-xs font-semibold text-slate-700 mb-2">Platform Risk Split</p>
            <div className="space-y-1.5">
              {digest.platform_risk.map((row) => (
                <div key={row.platform} className="grid grid-cols-4 gap-2 text-xs border border-slate-100 rounded px-2 py-1.5 bg-slate-50">
                  <span className="font-semibold text-slate-700">{row.platform}</span>
                  <span className="text-slate-600">Total {row.total}</span>
                  <span className="text-red-700">Critical {row.critical}</span>
                  <span className="text-amber-700">Overdue {row.overdue}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 p-3">
            <p className="text-xs font-semibold text-slate-700 mb-2">Notification Channel Health</p>
            <div className="space-y-1.5">
              {digest.channel_summary.map((row) => (
                <div key={row.channel} className="grid grid-cols-5 gap-2 text-xs border border-slate-100 rounded px-2 py-1.5 bg-slate-50">
                  <span className="font-semibold text-slate-700 capitalize">{row.channel}</span>
                  <span className="text-green-700">Sent {row.sent}</span>
                  <span className="text-red-700">Failed {row.failed}</span>
                  <span className="text-amber-700">Retries {row.retries}</span>
                  <span className={`font-semibold ${row.deliveryPct >= 90 ? 'text-green-700' : row.deliveryPct >= 70 ? 'text-amber-700' : 'text-red-700'}`}>{row.deliveryPct}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="text-xs font-semibold text-slate-700 mb-2">Approval Flow (7d)</p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">Completed: <strong>{digest.approvals_by_status_7d.completed}</strong></div>
              <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">Acknowledged: <strong>{digest.approvals_by_status_7d.acknowledged}</strong></div>
              <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">In Progress: <strong>{digest.approvals_by_status_7d.inProgress}</strong></div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 p-3">
            <p className="text-xs font-semibold text-slate-700 mb-2">Top Failure Reasons</p>
            {digest.top_failure_reasons.length === 0 ? (
              <p className="text-xs text-green-700">No failed sends observed in this digest window.</p>
            ) : (
              <div className="space-y-1.5">
                {digest.top_failure_reasons.map((row) => (
                  <div key={row.reason} className="flex items-center justify-between text-xs border border-slate-100 rounded px-2 py-1.5 bg-slate-50">
                    <span className="text-slate-700">{row.reason}</span>
                    <span className="font-semibold text-red-700">{row.count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-slate-200 p-3">
          <p className="text-xs font-semibold text-slate-700 mb-2">Top Overdue Libraries</p>
          {digest.top_overdue_libraries.length === 0 ? (
            <p className="text-xs text-green-700">No overdue libraries found for the current digest period.</p>
          ) : (
            <div className="overflow-auto">
              <table className="w-full table-base text-xs">
                <thead>
                  <tr>
                    <th>Package</th>
                    <th>Platform</th>
                    <th>Priority</th>
                    <th>Owner</th>
                    <th>Days Overdue</th>
                  </tr>
                </thead>
                <tbody>
                  {digest.top_overdue_libraries.map((row) => (
                    <tr key={row.id}>
                      <td>{row.package}</td>
                      <td>{row.platform}</td>
                      <td>{row.priority || 'n/a'}</td>
                      <td>{row.owner}</td>
                      <td className="text-red-700 font-semibold">{row.daysOverdue}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      )}

      {!isLoading && !isError && !digest && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-600">No digest data returned from backend.</p>
        </div>
      )}
    </div>
  )
}

function DigestTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="text-lg font-bold text-slate-800">{value}</p>
    </div>
  )
}
