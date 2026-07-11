import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BellRing, Settings, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import { notificationsApi } from '../api/client'
import type { NotifyResult } from '../api/types'
import { classifyFailureReason, flattenNotificationRows, isRetryMessage } from '../utils/notificationAnalytics'

export default function NotificationReliability() {
  const { data, refetch, isFetching } = useQuery({
    queryKey: ['notifications-history', 'page'],
    queryFn: () => notificationsApi.list(),
    staleTime: 30_000,
  })

  const history: NotifyResult[] = Array.isArray(data?.data) ? (data.data as NotifyResult[]) : []

  const model = useMemo(() => {
    const rows = flattenNotificationRows(history)
    const sent = rows.filter((r) => r.status === 'sent').length
    const failed = rows.filter((r) => r.status === 'failed').length
    const deliveryPct = sent + failed > 0 ? Math.round((sent / (sent + failed)) * 100) : 100

    const channels = ['email', 'teams']
    const channelSummary = channels.map((channel) => {
      const subset = rows.filter((r) => r.channel === channel)
      return {
        channel,
        sent: subset.filter((r) => r.status === 'sent').length,
        failed: subset.filter((r) => r.status === 'failed').length,
        retries: subset.filter((r) => isRetryMessage(r.message)).length,
      }
    })

    const buckets: Record<string, number> = {}
    for (const row of rows.filter((r) => r.status === 'failed')) {
      const bucket = classifyFailureReason(row.message)
      buckets[bucket] = (buckets[bucket] ?? 0) + 1
    }

    const today = new Date()
    const trendDays = Array.from({ length: 7 }, (_, idx) => {
      const day = new Date(today)
      day.setDate(today.getDate() - (6 - idx))
      const key = day.toISOString().slice(5, 10)
      return key
    })

    const channelTrend = channels.map((channel) => ({
      channel,
      points: trendDays.map((label) => {
        const items = rows.filter((r) => r.channel === channel && String(r.at).slice(5, 10) === label)
        return {
          label,
          sent: items.filter((r) => r.status === 'sent').length,
          failed: items.filter((r) => r.status === 'failed').length,
          retries: items.filter((r) => isRetryMessage(r.message)).length,
        }
      }),
    }))

    const topReasons = Object.entries(buckets)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([reason, count]) => ({ reason, count }))

    return {
      attempts: rows.length,
      sent,
      failed,
      retries: rows.filter((r) => isRetryMessage(r.message)).length,
      deliveryPct,
      channelSummary,
      channelTrend,
      topReasons,
    }
  }, [history])

  return (
    <div className="space-y-5">
      <div className="page-header">
        <div>
          <h1 className="page-title">Notification Reliability Center</h1>
          <p className="page-subtitle">Per-channel delivery posture, retry behavior, and failure evidence.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary py-1.5 text-xs" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} /> Refresh
          </button>
          <Link to="/business-communication-controls" className="btn-primary py-1.5 text-xs">
            <Settings size={12} /> Business Communication Controls
          </Link>
        </div>
      </div>

      <SectionBand
        title="Delivery Trust"
        subtitle="Operational trend for email and teams notifications with strict retry/failure parsing. Configuration uses existing Business Communication Controls in Settings."
      />

      <SectionCard cardClassName="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <BellRing size={16} className="text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-700">Reliability Snapshot</h3>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4">
          {[
            { label: 'Attempts', value: model.attempts, tone: 'text-slate-800', bg: 'bg-slate-100' },
            { label: 'Sent', value: model.sent, tone: 'text-green-700', bg: 'bg-green-100' },
            { label: 'Failed', value: model.failed, tone: 'text-red-700', bg: 'bg-red-100' },
            { label: 'Retries', value: model.retries, tone: 'text-amber-700', bg: 'bg-amber-100' },
            { label: 'Delivery %', value: `${model.deliveryPct}%`, tone: model.deliveryPct >= 90 ? 'text-green-700' : model.deliveryPct >= 70 ? 'text-amber-700' : 'text-red-700', bg: model.deliveryPct >= 90 ? 'bg-green-100' : model.deliveryPct >= 70 ? 'bg-amber-100' : 'bg-red-100' },
          ].map((item) => (
            <div key={item.label} className="rounded-lg border border-slate-200 px-2.5 py-2 text-center bg-white">
              <p className={`text-base font-bold ${item.tone}`}>{item.value}</p>
              <p className="text-[10px] text-slate-500">{item.label}</p>
            </div>
          ))}
        </div>

        <div className="rounded-lg border border-slate-200 p-3 mb-3">
          <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1.5">By Channel</p>
          <div className="space-y-1.5">
            {model.channelSummary.map((s) => (
              <div key={s.channel} className="grid grid-cols-4 gap-2 text-xs items-center">
                <span className="font-semibold text-slate-700 capitalize">{s.channel}</span>
                <span className="text-green-700">Sent {s.sent}</span>
                <span className="text-red-700">Failed {s.failed}</span>
                <span className="text-amber-700">Retries {s.retries}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-3 mb-3">
          <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1.5">7-day Channel Trend</p>
          <div className="space-y-2">
            {model.channelTrend.map((ch) => (
              <div key={ch.channel}>
                <p className="text-[11px] font-semibold text-slate-600 capitalize mb-1">{ch.channel}</p>
                <div className="grid grid-cols-7 gap-1">
                  {ch.points.map((pt) => (
                    <div key={`${ch.channel}-${pt.label}`} className="rounded border border-slate-100 px-1 py-1 text-[9px] bg-slate-50">
                      <p className="text-slate-500 mb-0.5">{pt.label}</p>
                      <p className="text-green-700">S {pt.sent}</p>
                      <p className="text-red-700">F {pt.failed}</p>
                      <p className="text-amber-700">R {pt.retries}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-3">
          <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1.5">Failure Buckets</p>
          {model.topReasons.length === 0 ? (
            <p className="text-xs text-green-700">No failed sends observed.</p>
          ) : (
            <div className="space-y-1.5">
              {model.topReasons.map((row) => (
                <div key={row.reason} className="flex items-center justify-between text-xs border border-slate-100 rounded px-2 py-1 bg-slate-50">
                  <span className="text-slate-700">{row.reason}</span>
                  <span className="font-semibold text-red-700">{row.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </SectionCard>
    </div>
  )
}
