import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Library, AlertTriangle, CheckCircle, BarChart3, Clock, Shield, Archive, Play, TrendingUp, Users, BellRing, Download,
} from 'lucide-react'
import MetricCard from '../components/MetricCard'
import StatusBadge from '../components/StatusBadge'
import ExecutiveTriad from '../components/ExecutiveTriad'
import { PaginatedSectionFooter, RowsPerPageControl } from '../components/PaginatedSectionControls'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import ChartSection from '../components/ChartSection'
import UpgradePieChart from '../components/charts/UpgradePieChart'
import PlatformBarChart from '../components/charts/PlatformBarChart'
import { libraryApi, slaApi, lifecycleApi, schedulerApi, authApi, analyticsApi, settingsApi, notificationsApi } from '../api/client'
import type { Library as LibType, Lifecycle, NotifyResult, PipelineRun } from '../api/types'
import { classifyFailureReason, isRetryMessage } from '../utils/notificationAnalytics'

type UsageStats = {
  total_calls?: number
  total_tokens?: number
  total_cost_usd?: number
  avg_latency_ms?: number | null
}

type LlmConfigView = {
  model_name?: string
  enabled?: boolean
  api_key_set?: boolean
}

export default function Dashboard() {
  const [pieInsight, setPieInsight] = useState('Insight: Upgrade distribution reflects current portfolio risk posture.')
  const [platformInsight, setPlatformInsight] = useState('Insight: Platform-level split highlights where remediation capacity is required first.')
  const [slaPage, setSlaPage] = useState(1)
  const [slaPageSize, setSlaPageSize] = useState(5)
  const [userPage, setUserPage] = useState(1)
  const [userPageSize, setUserPageSize] = useState(6)

  const { data: libRes } = useQuery({ queryKey: ['libraries'], queryFn: () => libraryApi.list() })
  const { data: slaRes } = useQuery({ queryKey: ['sla-summary'], queryFn: () => slaApi.summary() })
  const { data: pendingRes } = useQuery({
    queryKey: ['hitl-pending'],
    queryFn: () => lifecycleApi.pendingReview(),
  })
  const { data: runsRes } = useQuery({
    queryKey: ['pipeline-runs'],
    queryFn: () => schedulerApi.getRuns(),
    staleTime: 30_000,
  })
  const { data: usersRes } = useQuery({
    queryKey: ['users'],
    queryFn: () => authApi.getUsers(),
    staleTime: 60_000,
  })
  const { data: llmUsageRes } = useQuery({
    queryKey: ['llm-usage'],
    queryFn: () => analyticsApi.usage(),
    staleTime: 60_000,
  })
  const { data: llmCfgRes } = useQuery({
    queryKey: ['settings-llm'],
    queryFn: () => settingsApi.getLlm(),
    staleTime: 60_000,
  })
  const { data: notificationsRes } = useQuery({
    queryKey: ['notifications-history'],
    queryFn: () => notificationsApi.list(),
    staleTime: 30_000,
  })
  const { data: lifecycleAllRes } = useQuery({
    queryKey: ['lifecycle-list-all'],
    queryFn: () => lifecycleApi.list(),
    staleTime: 0,
    refetchInterval: 15_000,
  })

  // libRes?.data = { libraries: [...], total: N } (double-wrapped by service)
  const libs: LibType[] = (libRes?.data as { libraries?: LibType[] })?.libraries ?? []
  const sla = (slaRes?.data ?? {}) as Record<string, unknown>

  // KPIs — 4-tier priority system (critical/high/moderate/low) + backward compat with mandatory
  const _un = (l: LibType) => (l.update_needed ?? '').toLowerCase()
  const backendPriorityCounts = (sla as Record<string, unknown>).priority_counts as
    | { critical?: number; high?: number; moderate?: number; low?: number; mandatory?: number; up_to_date?: number }
    | undefined
  // Only show mandatory+critical+high items in HITL pending count
  const pendingItems = Array.isArray(pendingRes?.data) ? (pendingRes.data as LibType[]) : []
  const localPendingCount: number = pendingItems.filter(l => ['mandatory','critical','high'].includes(_un(l))).length
  const backendPendingCount = Number((sla as Record<string, unknown>).pending_review_high_risk ?? NaN)
  const pendingCount = Number.isFinite(backendPendingCount) ? backendPendingCount : localPendingCount

  const lifecycleSplit = (sla as Record<string, unknown>).lifecycle_platform_split as
    | {
        in_progress?: { Android?: number; iOS?: number; Unknown?: number }
        awaiting_review?: { Android?: number; iOS?: number; Unknown?: number }
      }
    | undefined

  const inProgressAndroid = Number(lifecycleSplit?.in_progress?.Android ?? 0)
  const inProgressIos = Number(lifecycleSplit?.in_progress?.iOS ?? 0)
  const awaitingAndroid = Number(lifecycleSplit?.awaiting_review?.Android ?? 0)
  const awaitingIos = Number(lifecycleSplit?.awaiting_review?.iOS ?? 0)

  const critical   = Number.isFinite(Number(backendPriorityCounts?.critical))
    ? Number(backendPriorityCounts?.critical)
    : libs.filter((l) => _un(l) === 'critical').length
  const high       = Number.isFinite(Number(backendPriorityCounts?.high))
    ? Number(backendPriorityCounts?.high)
    : libs.filter((l) => _un(l) === 'high').length
  const moderate   = Number.isFinite(Number(backendPriorityCounts?.moderate))
    ? Number(backendPriorityCounts?.moderate)
    : libs.filter((l) => _un(l) === 'moderate').length
  const low        = Number.isFinite(Number(backendPriorityCounts?.low))
    ? Number(backendPriorityCounts?.low)
    : libs.filter((l) => _un(l) === 'low').length
  const mandatory  = Number.isFinite(Number(backendPriorityCounts?.mandatory))
    ? Number(backendPriorityCounts?.mandatory)
    : libs.filter((l) => _un(l) === 'mandatory').length  // legacy
  const upToDate   = Number.isFinite(Number(backendPriorityCounts?.up_to_date))
    ? Number(backendPriorityCounts?.up_to_date)
    : libs.filter((l) => ['none', 'optional', ''].includes(_un(l))).length
  const backendDeprecated = Number((sla as Record<string, unknown>).deprecated ?? NaN)
  const deprecated = Number.isFinite(backendDeprecated)
    ? backendDeprecated
    : libs.filter((l) => ['deprecated', 'legacy'].includes((l.status ?? '').toLowerCase())).length

  // Pie chart uses update_needed only — segments are mutually exclusive and sum to total
  // critical already includes deprecated libs (they get update_needed=critical via writeback)
  const backendPie = (sla as Record<string, unknown>).pie_distribution as
    | { critical?: number; high?: number; moderate?: number; up_to_date?: number }
    | undefined
  const pieData = {
    critical: Number.isFinite(Number(backendPie?.critical)) ? Number(backendPie?.critical) : critical + mandatory,
    high: Number.isFinite(Number(backendPie?.high)) ? Number(backendPie?.high) : high,
    moderate: Number.isFinite(Number(backendPie?.moderate)) ? Number(backendPie?.moderate) : moderate + low,
    upToDate: Number.isFinite(Number(backendPie?.up_to_date)) ? Number(backendPie?.up_to_date) : upToDate,
  }
  // Sanity: sum should equal libs.length
  // pieData.critical + pieData.high + pieData.moderate + pieData.upToDate === libs.length ✓

  // Platform chart — 4-tier breakdown per platform
  const backendPlatformDistribution = (sla as Record<string, unknown>).platform_distribution as
    | Array<{ platform: string; critical: number; high: number; moderate: number; up_to_date: number }>
    | undefined
  const platforms = ['Android', 'iOS']
  const platformData = Array.isArray(backendPlatformDistribution) && backendPlatformDistribution.length > 0
    ? backendPlatformDistribution.map((row) => ({
        platform: row.platform,
        critical: Number(row.critical ?? 0),
        high: Number(row.high ?? 0),
        moderate: Number(row.moderate ?? 0),
        upToDate: Number(row.up_to_date ?? 0),
      }))
    : platforms.map((p) => {
      const pl = libs.filter((l) => l.platform === p)
      return {
        platform: p,
        critical: pl.filter((l) => ['critical','mandatory'].includes(_un(l))).length,
        high:     pl.filter((l) => _un(l) === 'high').length,
        moderate: pl.filter((l) => ['moderate','low'].includes(_un(l))).length,
        upToDate: pl.filter((l) => ['none','optional',''].includes(_un(l))).length,
      }
    })

  // Risk score = weighted formula across all tiers
  const riskScore = libs.length > 0
    ? Math.round(((critical + mandatory) * 4 + high * 3 + moderate * 2 + low) / (libs.length * 4) * 100)
    : 0
  const backendRiskScore = Number((sla as Record<string, unknown>).risk_score ?? NaN)
  const effectiveRiskScore = Number.isFinite(backendRiskScore) ? backendRiskScore : riskScore

  // SLA derived directly from libs — no extra API call
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const slaLibs = libs
    .filter((l) => l.deadline_date)
    .map((l) => {
      const dl = new Date(l.deadline_date!)
      const daysLeft = Math.ceil((dl.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
      return { ...l, daysLeft }
    })
    .sort((a, b) => a.daysLeft - b.daysLeft)
  const slaOverdue     = slaLibs.filter((l) => l.daysLeft < 0)
  const slaDue7        = slaLibs.filter((l) => l.daysLeft >= 0 && l.daysLeft <= 7)
  const slaDue30       = slaLibs.filter((l) => l.daysLeft > 7 && l.daysLeft <= 30)
  const slaCompliance  = Number(sla.sla_compliance_pct ?? 0)
  const slaComplianceSafe = Math.max(0, Math.min(100, Number.isFinite(slaCompliance) ? slaCompliance : 0))

  const { data: pendingLifecycle } = useQuery({
    queryKey: ['lifecycle-pending'],
    queryFn: () => lifecycleApi.list({ status: 'awaiting_review', limit: 5 }),
  })
  const recent: Lifecycle[] = Array.isArray(pendingLifecycle?.data) ? (pendingLifecycle!.data as Lifecycle[]).slice(0, 5) : []
  const lifecycleAll: Lifecycle[] = Array.isArray(lifecycleAllRes?.data) ? (lifecycleAllRes!.data as Lifecycle[]) : []
  // Prefer backend split counts; fallback to local dedup if summary is unavailable.
  const localInProgressCount = new Set(
    lifecycleAll.filter(l => l.status === 'In Progress').map(l => l.library_id)
  ).size
  const inProgressCount = Number.isFinite(inProgressAndroid + inProgressIos)
    ? inProgressAndroid + inProgressIos
    : localInProgressCount

  // Pipeline run stats — all runs returned are real (ghosts cleaned from DB)
  const allRuns: PipelineRun[] = Array.isArray(runsRes?.data) ? (runsRes!.data as PipelineRun[]) : []
  const runStats = {
    total:     allRuns.length,
    completed: allRuns.filter(r => r.status === 'completed' || r.status === 'success').length,
    failed:    allRuns.filter(r => r.status === 'failed'    || r.status === 'error').length,
    partial:   allRuns.filter(r => r.status === 'partial').length,
    scheduled: allRuns.filter(r => r.triggered_by === 'scheduler').length,
    manual:    allRuns.filter(r => r.triggered_by === 'manual').length,
  }
  const lastRun = allRuns[0]
  const throughputPerDay = (() => {
    const now = Date.now()
    const windowMs = 14 * 24 * 60 * 60 * 1000
    const recent = allRuns.filter((r) => {
      if (!r.started_at) return false
      const t = new Date(r.started_at).getTime()
      return now - t <= windowMs && (r.status === 'completed' || r.status === 'partial')
    })
    if (recent.length === 0) return 0
    const processed = recent.reduce((sum, r) => sum + (r.total_libraries ?? 0), 0)
    return processed / 14
  })()
  const dueIn = (days: number) => slaLibs.filter((l) => l.daysLeft >= 0 && l.daysLeft <= days).length
  const projectedRisk = (days: number) => {
    const due = dueIn(days)
    const capacity = throughputPerDay * days
    return Math.max(0, Math.ceil(due - capacity))
  }
  const slaForecast = {
    d7: projectedRisk(7),
    d14: projectedRisk(14),
    d30: projectedRisk(30),
  }
  const backendForecast = (sla as Record<string, unknown>).sla_forecast as
    | { d7?: number; d14?: number; d30?: number; throughput_per_day?: number }
    | undefined
  const effectiveSlaForecast = {
    d7: Number.isFinite(Number(backendForecast?.d7)) ? Number(backendForecast?.d7) : slaForecast.d7,
    d14: Number.isFinite(Number(backendForecast?.d14)) ? Number(backendForecast?.d14) : slaForecast.d14,
    d30: Number.isFinite(Number(backendForecast?.d30)) ? Number(backendForecast?.d30) : slaForecast.d30,
  }
  const effectiveThroughputPerDay = Number.isFinite(Number(backendForecast?.throughput_per_day))
    ? Number(backendForecast?.throughput_per_day)
    : throughputPerDay

  // User stats
  interface AppUser { id: number; username: string; role: string; is_active: boolean }
  const allUsers: AppUser[] = (usersRes?.data as { users?: AppUser[] } | undefined)?.users ?? []
  const activeUsers   = allUsers.filter(u => u.is_active)
  const adminUsers    = allUsers.filter(u => u.role === 'admin' && u.is_active)
  const viewerUsers   = allUsers.filter(u => u.role === 'viewer' && u.is_active)
  const inactiveUsers = allUsers.filter(u => !u.is_active)

  const llmStats = ((llmUsageRes?.data as { stats?: UsageStats } | undefined)?.stats ?? {}) as UsageStats
  const llmCfg = (llmCfgRes?.data ?? {}) as LlmConfigView
  const llmActive = Boolean(llmCfg.enabled && llmCfg.api_key_set)
  const executiveRiskBacklog = critical + high + mandatory
  const notificationHistory: NotifyResult[] = Array.isArray(notificationsRes?.data)
    ? (notificationsRes?.data as NotifyResult[])
    : []

  const notificationStats = useMemo(() => {
    const rows = notificationHistory.flatMap((entry) =>
      (entry.results ?? []).map((res) => ({
        channel: String(res.channel ?? '').toLowerCase(),
        status: String(res.status ?? '').toLowerCase(),
        message: (res.message ?? '').trim(),
        at: res.sent_at ?? entry.generated_at,
      }))
    )
    const sent = rows.filter((r) => r.status === 'sent').length
    const failed = rows.filter((r) => r.status === 'failed').length
    const skipped = rows.filter((r) => r.status === 'skipped').length
    const deliveryBase = sent + failed
    const deliveryPct = deliveryBase > 0 ? Math.round((sent / deliveryBase) * 100) : 100

    const retryCount = rows.filter((r) => isRetryMessage(r.message)).length

    const failureBuckets: Record<string, number> = {}
    for (const row of rows.filter((r) => r.status === 'failed')) {
      const bucket = classifyFailureReason(row.message)
      failureBuckets[bucket] = (failureBuckets[bucket] ?? 0) + 1
    }

    const today = new Date()
    const trend: Array<{ label: string; value: number }> = []
    for (let i = 6; i >= 0; i -= 1) {
      const d = new Date(today)
      d.setDate(today.getDate() - i)
      const key = d.toISOString().slice(0, 10)
      const value = rows.filter((r) => String(r.at).slice(0, 10) === key).length
      trend.push({ label: key.slice(5), value })
    }

    const topReasons = Object.entries(failureBuckets)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([reason, count]) => ({ reason, count }))

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

    const channelTrend = channels.map((channel) => {
      const series = trend.map((t) => {
        const dayRows = rows.filter((r) => {
          const day = String(r.at).slice(5, 10)
          return r.channel === channel && day === t.label
        })
        return {
          label: t.label,
          sent: dayRows.filter((r) => r.status === 'sent').length,
          failed: dayRows.filter((r) => r.status === 'failed').length,
          retries: dayRows.filter((r) => isRetryMessage(r.message)).length,
        }
      })
      return { channel, series }
    })

    return {
      attempts: rows.length,
      sent,
      failed,
      skipped,
      retryCount,
      deliveryPct,
      topReasons,
      trend,
      channelSummary,
      channelTrend,
    }
  }, [notificationHistory])

  const latestLifecycleByLibrary = useMemo(() => {
    const map = new Map<number, Lifecycle>()
    for (const item of lifecycleAll) {
      const prev = map.get(item.library_id)
      if (!prev || new Date(item.updated_at).getTime() > new Date(prev.updated_at).getTime()) {
        map.set(item.library_id, item)
      }
    }
    return map
  }, [lifecycleAll])

  const atRiskItems = slaLibs.filter((l) => l.daysLeft <= 30)
  const backendAtRiskSummary = (sla as Record<string, unknown>).at_risk_summary as
    | { by_platform?: Array<{ name: string; count: number }>; by_owner?: Array<{ name: string; count: number }> }
    | undefined
  const atRiskByPlatform = useMemo(() => {
    if (Array.isArray(backendAtRiskSummary?.by_platform) && backendAtRiskSummary.by_platform.length > 0) {
      return backendAtRiskSummary.by_platform.map((row) => [row.name, Number(row.count)] as [string, number])
    }
    const acc: Record<string, number> = {}
    for (const item of atRiskItems) {
      const key = item.platform || 'Unknown'
      acc[key] = (acc[key] ?? 0) + 1
    }
    return Object.entries(acc).sort((a, b) => b[1] - a[1]).slice(0, 3)
  }, [atRiskItems, backendAtRiskSummary?.by_platform])

  const atRiskByTeam = useMemo(() => {
    if (Array.isArray(backendAtRiskSummary?.by_owner) && backendAtRiskSummary.by_owner.length > 0) {
      return backendAtRiskSummary.by_owner.map((row) => [row.name, Number(row.count)] as [string, number])
    }
    const acc: Record<string, number> = {}
    for (const item of atRiskItems) {
      const owner = latestLifecycleByLibrary.get(item.id)?.actioned_by || 'Unassigned'
      acc[owner] = (acc[owner] ?? 0) + 1
    }
    return Object.entries(acc).sort((a, b) => b[1] - a[1]).slice(0, 3)
  }, [atRiskItems, latestLifecycleByLibrary, backendAtRiskSummary?.by_owner])

  const backendOwnerWorkload = (sla as Record<string, unknown>).owner_workload as
    | Array<{ owner: string; critical: number; overdue: number; dueSoon: number; total: number }>
    | undefined
  const ownerWorkload = useMemo(() => {
    if (Array.isArray(backendOwnerWorkload) && backendOwnerWorkload.length > 0) {
      return backendOwnerWorkload
    }
    const open = Array.from(latestLifecycleByLibrary.values()).filter((x) => (x.status ?? '').toLowerCase() !== 'completed')
    const owners: Record<string, { critical: number; overdue: number; dueSoon: number }> = {}
    const todayTs = Date.now()
    const sevenDays = 7 * 24 * 60 * 60 * 1000
    for (const item of open) {
      const owner = (item.actioned_by || '').trim() || 'Unassigned'
      owners[owner] = owners[owner] ?? { critical: 0, overdue: 0, dueSoon: 0 }
      const un = (item.update_needed || '').toLowerCase()
      if (['mandatory', 'critical', 'high'].includes(un)) owners[owner].critical += 1
      if (item.target_date) {
        const due = new Date(item.target_date).getTime()
        if (due < todayTs) owners[owner].overdue += 1
        else if (due - todayTs <= sevenDays) owners[owner].dueSoon += 1
      }
    }
    return Object.entries(owners)
      .map(([owner, v]) => ({ owner, ...v, total: v.critical + v.overdue + v.dueSoon }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 5)
  }, [latestLifecycleByLibrary, backendOwnerWorkload])

  const rebalanceSuggestion = useMemo(() => {
    const backendSuggestion = String((sla as Record<string, unknown>).rebalance_suggestion ?? '').trim()
    if (backendSuggestion) return backendSuggestion
    if (ownerWorkload.length < 2) return 'Workload looks balanced across current owners.'
    const busiest = ownerWorkload[0]
    const lightest = ownerWorkload[ownerWorkload.length - 1]
    const delta = busiest.critical - lightest.critical
    if (delta >= 3) {
      return `Reassign ${Math.min(3, delta)} high-priority items from ${busiest.owner} to ${lightest.owner} to reduce SLA breach risk.`
    }
    return 'No immediate rebalancing required; continue monitoring overdue and due-soon queues.'
  }, [ownerWorkload, sla])

  const slaTotalPages = Math.max(1, Math.ceil(slaLibs.length / slaPageSize))
  const safeSlaPage = Math.min(slaPage, slaTotalPages)
  const slaStart = (safeSlaPage - 1) * slaPageSize
  const slaEnd = Math.min(slaStart + slaPageSize, slaLibs.length)
  const pagedSla = useMemo(() => slaLibs.slice(slaStart, slaEnd), [slaLibs, slaStart, slaEnd])

  const usersTotalPages = Math.max(1, Math.ceil(activeUsers.length / userPageSize))
  const safeUserPage = Math.min(userPage, usersTotalPages)
  const usersStart = (safeUserPage - 1) * userPageSize
  const usersEnd = Math.min(usersStart + userPageSize, activeUsers.length)
  const pagedUsers = useMemo(() => activeUsers.slice(usersStart, usersEnd), [activeUsers, usersStart, usersEnd])

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title">Executive Overview</h1>
          <p className="page-subtitle">Portfolio upgrade posture — {libs.length} SDKs under governance</p>
        </div>
      </div>

      <ExecutiveTriad
        impact={`${executiveRiskBacklog} high-priority SDKs (critical/high/mandatory) require governance attention.`}
        owner={`Portfolio Governance Office (${adminUsers.length} active admin${adminUsers.length === 1 ? '' : 's'})`}
        nextAction={pendingCount > 0 ? `Clear ${pendingCount} pending approvals in the review queue.` : `Run the next pipeline cycle and confirm SLA compliance trend (risk score ${effectiveRiskScore}).`}
        tone={executiveRiskBacklog > 0 ? 'warning' : 'positive'}
      />

      <SectionBand
        title="Portfolio Risk Snapshot"
        subtitle="Executive KPIs and model operating posture for current governance cycle."
      />

      {/* KPI Row — 4-tier priority + lifecycle In Progress */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-7 gap-4">
        <MetricCard title="SDK Portfolio" value={libs.length}         icon={<Library size={18} />}       color="default" href="/libraries" />
        <MetricCard title="🔴 Critical"      value={critical + mandatory} icon={<AlertTriangle size={18} />}  color="red"     subtitle="Major bump / security"   href="/libraries" />
        <MetricCard title="🟠 High"           value={high}                icon={<TrendingUp size={18} />}    color="amber"   subtitle="Minor bump / compliance" href="/libraries" />
        <MetricCard title="🟡 Moderate"      value={moderate + low}      icon={<TrendingUp size={18} />}    color="default" subtitle="Patch / bug fixes"       href="/libraries" />
        <MetricCard title="✅ Up to Date"    value={upToDate}            icon={<CheckCircle size={18} />}   color="green"   subtitle="No upgrade needed"       href="/libraries" />
        <MetricCard title="Deprecated"       value={deprecated}          icon={<Archive size={18} />}       color="slate"   subtitle="Deprecated / Legacy"     href="/libraries" />
        <MetricCard title="🔧 In Progress"    value={inProgressCount}     icon={<TrendingUp size={18} />}    color="amber"   subtitle={`Android ${inProgressAndroid} · iOS ${inProgressIos}`}   href="/libraries" />
      </div>

      {/* LLM high-level usage */}
      <SectionCard cardClassName="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-700">LLM Usage (High Level)</h3>
          <a href="/analytics" className="text-[11px] text-primary-600 hover:underline font-medium">Open LLM Analytics →</a>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Calls</p>
            <p className="text-lg font-bold text-slate-800">{(llmStats.total_calls ?? 0).toLocaleString()}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Tokens</p>
            <p className="text-lg font-bold text-slate-800">{(llmStats.total_tokens ?? 0).toLocaleString()}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Cost</p>
            <p className="text-lg font-bold text-slate-800">${(llmStats.total_cost_usd ?? 0).toFixed(4)}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Engine Mode</p>
            <p className={`text-sm font-semibold ${llmActive ? 'text-green-700' : 'text-amber-700'}`}>
              {llmActive ? `AI Active (${llmCfg.model_name || 'model'})` : 'Rule-based / inactive'}
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5">
              Avg latency: {llmStats.avg_latency_ms ? `${Math.round(llmStats.avg_latency_ms)}ms` : 'N/A'}
            </p>
          </div>
        </div>
      </SectionCard>

      {/* Charts row */}
      <SectionBand
        title="Trend & Distribution"
        subtitle="Priority distribution and platform-level risk visualization."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SectionCard cardClassName="card p-5">
          <ChartSection
            title="Upgrade Priority Distribution"
            rightSlot={`${libs.length} total`}
            insight={pieInsight}
          >
            <UpgradePieChart {...pieData} onInsightComputed={setPieInsight} />
          </ChartSection>
        </SectionCard>
        <SectionCard cardClassName="card p-5 flex flex-col">
          <ChartSection
            className="flex-1 flex flex-col"
            title="Priority by Platform"
            rightSlot="Android · iOS"
            insight={platformInsight}
          >
            <div className="flex-1 min-h-[240px]">
              <PlatformBarChart data={platformData} onInsightComputed={setPlatformInsight} />
            </div>
          </ChartSection>
        </SectionCard>
      </div>

      {/* SLA + HITL + Scheduler Stats + Recent */}
      <SectionBand
        title="Operational Control Boards"
        subtitle="SLA pressure, review queue, run reliability, and pending governance actions."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-5 gap-6">
        {/* SLA — high-level summary */}
        <SectionCard cardClassName="card p-5 overflow-hidden sla-overview-card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Clock size={16} className="text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-700">SLA Overview</h3>
            </div>
            <a href="/libraries" className="text-[11px] text-primary-600 font-medium no-underline hover:no-underline">{slaLibs.length} with deadline →</a>
          </div>

          {/* Compliance % */}
          <div className="text-center mb-4">
            <p className={`text-4xl font-bold tabular-nums ${
              slaComplianceSafe >= 80 ? 'text-green-600' :
              slaComplianceSafe >= 50 ? 'text-amber-600' : 'text-red-600'
            }`}>{slaComplianceSafe.toFixed(0)}<span className="text-xl font-medium">%</span></p>
            <p className="text-xs text-slate-500 mt-0.5">SLA Compliance</p>
            <div className="sla-compliance-meter h-1.5 bg-slate-100 rounded-full mt-2">
              <div
                className={`sla-compliance-fill rounded-full transition-all duration-700 ${
                  slaComplianceSafe >= 80 ? 'bg-green-500' :
                  slaComplianceSafe >= 50 ? 'bg-amber-500' : 'bg-red-500'
                }`}
                style={{ width: `${slaComplianceSafe}%`, minWidth: slaComplianceSafe > 0 ? '2px' : '0' }}
              />
            </div>
          </div>

          {/* 3 stat pills */}
          <div className="grid grid-cols-3 gap-2 mb-4">
            {[
              { label: 'Overdue',  value: slaOverdue.length, bg: 'bg-red-50',    text: 'text-red-700',    border: 'border-red-200' },
              { label: 'Due ≤7d',  value: slaDue7.length,    bg: 'bg-amber-50',  text: 'text-amber-700',  border: 'border-amber-200' },
              { label: 'Due ≤30d', value: slaDue30.length,   bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200' },
            ].map(({ label, value, bg, text, border }) => (
              <div key={label} className={`rounded-lg border ${border} ${bg} px-2 py-2 text-center`}>
                <p className={`text-2xl font-bold tabular-nums ${text}`}>{value}</p>
                <p className="text-[10px] text-slate-500 leading-tight mt-0.5">{label}</p>
              </div>
            ))}
          </div>

          {/* Most urgent deadline */}
          {slaLibs.length === 0 ? (
            <div className="text-center py-3">
              <p className="text-xs text-slate-400">No deadlines set</p>
              <p className="text-[11px] text-slate-300 mt-0.5">Set deadlines on SDKs to track SLA</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Most Urgent</p>
              {slaLibs.slice(0, 4).map((l) => {
                const isOverdue = l.daysLeft < 0
                const isUrgent  = l.daysLeft >= 0 && l.daysLeft <= 7
                const label = isOverdue
                  ? `${Math.abs(l.daysLeft)}d overdue`
                  : l.daysLeft === 0 ? 'Due today'
                  : `${l.daysLeft}d left`
                return (
                  <div key={l.id}
                    className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs ${
                      isOverdue ? 'bg-red-50 border-red-200' :
                      isUrgent  ? 'bg-amber-50 border-amber-200' :
                                  'bg-slate-50 border-slate-100'
                    }`}>
                    <span className="flex-shrink-0">{isOverdue ? '🔴' : isUrgent ? '🟠' : '🟢'}</span>
                    <span className="flex-1 font-medium text-slate-700 truncate">{l.sdk_name || l.package}</span>
                    <span className={`flex-shrink-0 font-semibold tabular-nums text-[11px] ${
                      isOverdue ? 'text-red-600' : isUrgent ? 'text-amber-600' : 'text-slate-500'
                    }`}>{label}</span>
                  </div>
                )
              })}
              {slaLibs.length > 4 && (
                <a href="/libraries" className="block text-center text-[11px] text-primary-600 hover:underline pt-1">
                  +{slaLibs.length - 4} more →
                </a>
              )}
            </div>
          )}
        </SectionCard>

        {/* HITL */}
        <SectionCard cardClassName="card p-5 group hover:shadow-md hover:-translate-y-0.5 transition-all duration-150">
          <a href="/hitl-review" className="block">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Shield size={16} className="text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-700">HITL Review</h3>
            </div>
            <span className="text-[11px] text-primary-600 font-medium group-hover:underline">Open →</span>
          </div>
          <div className="text-center py-4">
            <p className={`text-4xl font-bold ${pendingCount > 0 ? 'text-amber-600' : 'text-green-600'}`}>
              {pendingCount}
            </p>
            <p className="text-sm text-slate-500 mt-1">Awaiting review</p>
            <p className="text-[11px] text-slate-400 mt-0.5">Android {awaitingAndroid} · iOS {awaitingIos}</p>
          </div>
          {pendingCount > 0 && (
            <div className="btn-primary w-full justify-center mt-2 text-center py-2 rounded-lg text-sm font-semibold">
              Review Now →
            </div>
          )}
          </a>
        </SectionCard>

        {/* Scheduler Stats */}
        <SectionCard cardClassName="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Play size={16} className="text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-700">Pipeline Runs</h3>
            </div>
            <a href="/scheduler" className="text-[11px] text-primary-600 hover:underline font-medium">View Scheduler →</a>
          </div>
          <div className="space-y-2.5">
            {[
              { label: 'Total Runs',  value: runStats.total,     color: 'text-slate-800', bg: 'bg-slate-100' },
              { label: '✅ Completed', value: runStats.completed, color: 'text-green-700', bg: 'bg-green-100' },
              { label: '❌ Failed',    value: runStats.failed,    color: 'text-red-700',   bg: 'bg-red-100' },
              { label: '⚠️ Partial',   value: runStats.partial,   color: 'text-amber-700', bg: 'bg-amber-100' },
            ].map(({ label, value, color, bg }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="text-xs text-slate-600">{label}</span>
                <span className={`text-sm font-bold px-2 py-0.5 rounded-full ${color} ${bg}`}>{value}</span>
              </div>
            ))}
            <div className="border-t border-slate-100 pt-2 mt-1 flex gap-3">
              <div className="flex-1 text-center">
                <p className="text-xs text-slate-400">⏰ Auto</p>
                <p className="text-base font-bold text-purple-700">{runStats.scheduled}</p>
              </div>
              <div className="w-px bg-slate-200" />
              <div className="flex-1 text-center">
                <p className="text-xs text-slate-400">▶ Manual</p>
                <p className="text-base font-bold text-blue-700">{runStats.manual}</p>
              </div>
            </div>
          </div>
          {lastRun && (
            <div className="mt-3 pt-3 border-t border-slate-100">
              <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-1">Last run</p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  {new Date(lastRun.started_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </span>
                <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${
                  lastRun.status === 'completed' ? 'bg-green-100 text-green-700' :
                  lastRun.status === 'failed'    ? 'bg-red-100 text-red-700' :
                  lastRun.status === 'partial'   ? 'bg-amber-100 text-amber-700' :
                  'bg-blue-100 text-blue-700'
                }`}>
                  {lastRun.triggered_by === 'scheduler' ? '⏰ Auto' : '▶ Manual'} · {lastRun.status}
                </span>
              </div>
            </div>
          )}
          {runStats.total === 0 && (
            <p className="text-xs text-slate-400 text-center py-4">No runs yet</p>
          )}
        </SectionCard>

        {/* Notification Reliability Center */}
        <SectionCard cardClassName="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <BellRing size={16} className="text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-700">Notification Reliability</h3>
            </div>
            <div className="flex items-center gap-2 text-[11px]">
              <Link to="/notification-reliability" className="text-primary-600 hover:underline font-medium">Open Center →</Link>
              <Link to="/business-communication-controls" className="text-slate-500 hover:underline">Configure</Link>
            </div>
          </div>

          <div className="mb-4">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-slate-500">Delivery rate (sent vs failed)</span>
              <span className={`text-sm font-bold ${
                notificationStats.deliveryPct >= 90 ? 'text-green-600' :
                notificationStats.deliveryPct >= 70 ? 'text-amber-600' :
                'text-red-600'
              }`}>{notificationStats.deliveryPct}%</span>
            </div>
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-700 ${
                  notificationStats.deliveryPct >= 90 ? 'bg-green-500' :
                  notificationStats.deliveryPct >= 70 ? 'bg-amber-500' :
                  'bg-red-500'
                }`}
                style={{ width: `${notificationStats.deliveryPct}%` }}
              />
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 mb-4">
            {[
              { label: 'Attempts', value: notificationStats.attempts, bg: 'bg-slate-50', text: 'text-slate-700', border: 'border-slate-200' },
              { label: 'Sent', value: notificationStats.sent, bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' },
              { label: 'Failed', value: notificationStats.failed, bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
              { label: 'Retries', value: notificationStats.retryCount, bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
            ].map(({ label, value, bg, text, border }) => (
              <div key={label} className={`rounded-lg border ${border} ${bg} px-2 py-1.5 text-center`}>
                <p className={`text-base font-bold ${text}`}>{value}</p>
                <p className="text-[10px] text-slate-500 leading-tight">{label}</p>
              </div>
            ))}
          </div>

          <div className="mb-3 rounded-lg border border-slate-200 p-2.5">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1.5">Delivery status by channel</p>
            <div className="space-y-1.5">
              {notificationStats.channelSummary.map((c) => (
                <div key={c.channel} className="grid grid-cols-4 gap-2 text-xs items-center">
                  <span className="font-semibold text-slate-700 capitalize">{c.channel}</span>
                  <span className="text-green-700">Sent {c.sent}</span>
                  <span className="text-red-700">Failed {c.failed}</span>
                  <span className="text-amber-700">Retries {c.retries}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mb-3 rounded-lg border border-slate-200 p-2.5">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1.5">7-day channel trend (sent / failed / retries)</p>
            <div className="space-y-2">
              {notificationStats.channelTrend.map((ch) => (
                <div key={ch.channel}>
                  <p className="text-[11px] font-semibold text-slate-600 capitalize mb-1">{ch.channel}</p>
                  <div className="grid grid-cols-7 gap-1">
                    {ch.series.map((pt) => (
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

          <div className="mb-3">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1.5">7-day delivery activity</p>
            <div className="flex items-end gap-1 h-12">
              {notificationStats.trend.map((t) => {
                const maxValue = Math.max(1, ...notificationStats.trend.map((x) => x.value))
                const height = Math.max(3, Math.round((t.value / maxValue) * 44))
                return (
                  <div key={t.label} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className="w-full rounded-sm bg-primary-300"
                      style={{ height }}
                      title={`${t.label}: ${t.value}`}
                    />
                    <span className="text-[9px] text-slate-400">{t.label}</span>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="pt-2 border-t border-slate-100">
            <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1.5">Top failure reasons</p>
            {notificationStats.topReasons.length === 0 ? (
              <p className="text-xs text-green-700">No delivery failures observed.</p>
            ) : (
              <div className="space-y-1">
                {notificationStats.topReasons.map((r) => (
                  <div key={r.reason} className="flex items-center justify-between text-xs">
                    <span className="text-slate-600 truncate pr-2">{r.reason}</span>
                    <span className="font-semibold text-red-700">{r.count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </SectionCard>

        {/* Recent Pending SDKs */}
        <SectionCard cardClassName="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-700">Recent Pending</h3>
            <a href="/governance" className="text-[11px] text-primary-600 hover:underline font-medium">View All →</a>
          </div>
          {recent.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-4">No pending items</p>
          ) : (
            <div className="space-y-2">
              {recent.map((lc) => (
                <div key={lc.id} className="flex items-center justify-between text-xs">
                  <span className="text-slate-700 truncate mr-2">
                    {lc.package ?? `SDK #${lc.library_id}`}
                  </span>
                  <StatusBadge status={lc.status} size="sm" />
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard cardClassName="card p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-700">Executive Weekly Digest</p>
            <p className="text-xs text-slate-500">Print-friendly leadership snapshot moved to its own page.</p>
          </div>
          <Link to="/weekly-digest" className="btn-primary py-1.5 text-xs">
            <Download size={12} /> Open Digest View
          </Link>
        </div>
      </SectionCard>

      {/* User Statistics */}
      <SectionBand
        title="Access Posture"
        subtitle="Active user cohort and role coverage with consistent pagination controls."
      />

      <SectionCard cardClassName="card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Users size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-700">User Statistics</h3>
          </div>
          <a href="/users" className="text-[11px] text-primary-600 hover:underline font-medium">Manage Users →</a>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          {[
            { label: 'Total Users',   value: allUsers.length,     color: 'text-slate-800',   bg: 'bg-slate-50',   border: 'border-slate-200' },
            { label: 'Active',        value: activeUsers.length,  color: 'text-green-700',   bg: 'bg-green-50',   border: 'border-green-200' },
            { label: 'Admins',        value: adminUsers.length,   color: 'text-primary-700', bg: 'bg-primary-50', border: 'border-primary-200' },
            { label: 'Viewers',       value: viewerUsers.length,  color: 'text-slate-600',   bg: 'bg-slate-50',   border: 'border-slate-100' },
          ].map(({ label, value, color, bg, border }) => (
            <div key={label} className={`rounded-xl border ${border} ${bg} px-4 py-3 text-center`}>
              <p className={`text-2xl font-bold ${color}`}>{value}</p>
              <p className="text-xs text-slate-500 mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Active user list */}
        {activeUsers.length > 0 && (
          <>
            <div className="mb-2 flex items-center justify-between text-[10px] text-slate-500">
              <span>Showing {activeUsers.length ? usersStart + 1 : 0}-{usersEnd} of {activeUsers.length}</span>
              <RowsPerPageControl
                pageSize={userPageSize}
                options={[6, 10, 20]}
                onChange={(value) => {
                  setUserPageSize(value)
                  setUserPage(1)
                }}
                labelClassName="text-[10px] text-slate-500"
                selectClassName="select py-1 text-[10px]"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {pagedUsers.map((u) => (
              <div key={u.id} className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-slate-50 border border-slate-100">
                <div className="w-7 h-7 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                  <span className="text-xs font-bold text-primary-700 uppercase">{u.username.charAt(0)}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-slate-800 truncate">@{u.username}</p>
                  <p className="text-[10px] text-slate-400 capitalize">{u.role}</p>
                </div>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                  u.role === 'admin' ? 'bg-primary-100 text-primary-700' : 'bg-slate-100 text-slate-600'
                }`}>
                  {u.role === 'admin' ? '🛡 Admin' : '👁 Viewer'}
                </span>
              </div>
            ))}
            </div>
            <PaginatedSectionFooter
              page={safeUserPage}
              totalPages={usersTotalPages}
              onPrev={() => setUserPage((p) => Math.max(1, p - 1))}
              onNext={() => setUserPage((p) => Math.min(usersTotalPages, p + 1))}
              prevLabel="Prev"
              nextLabel="Next"
              pagePrefix="Page"
              containerClassName="mt-2 flex items-center justify-between"
              pageClassName="text-[10px] text-slate-500"
              buttonClassName="btn-secondary py-1 px-2 text-[10px]"
            />
          </>
        )}

        {inactiveUsers.length > 0 && (
          <p className="text-[11px] text-slate-400 mt-3 text-center">
            +{inactiveUsers.length} inactive account{inactiveUsers.length > 1 ? 's' : ''}
          </p>
        )}
      </SectionCard>
    </div>
  )
}
