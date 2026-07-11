import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Save, RefreshCw, Loader2, AlertCircle, CheckCircle, XCircle, Plus, Trash2, Info, ChevronDown, ChevronUp } from 'lucide-react'
import ExecutiveTriad from '../components/ExecutiveTriad'
import { PaginatedSectionFooter, RowsPerPageControl } from '../components/PaginatedSectionControls'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import ChartSection from '../components/ChartSection'
import { settingsApi, healthApi } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, BarChart, Bar } from 'recharts'

interface AppSetting { key: string; value: string; description: string; is_sensitive: boolean }
interface PromptTemplate { prompt_key: string; template_text: string; variables_hint?: string | null; version?: number; updated_by?: string | null; updated_at?: string | null }
interface RuntimeTelemetry {
  gateway?: {
    uptime_seconds?: number
    uptime_minutes?: number
    uptime_hours?: number
  }
  requests?: {
    total?: number
    errors?: number
    error_rate_pct?: number
    avg_latency_ms?: number
    requests_per_minute_est?: number
    status_breakdown?: Record<string, number>
    top_endpoints?: Array<{
      method: string
      path: string
      requests: number
      errors: number
      avg_latency_ms: number
    }>
    windows?: {
      last_5m?: {
        requests?: number
        errors?: number
        avg_latency_ms?: number
        error_rate_pct?: number
        requests_per_minute_est?: number
      }
      last_1h?: {
        requests?: number
        errors?: number
        avg_latency_ms?: number
        error_rate_pct?: number
        requests_per_minute_est?: number
      }
    }
    trends?: {
      last_5m?: Array<{ bucket: number; requests: number; errors: number; avg_latency_ms: number }>
      last_1h?: Array<{ bucket: number; requests: number; errors: number; avg_latency_ms: number }>
    }
  }
  resources?: {
    memory_rss_mb?: number
    memory_percent?: number
    system_memory_used_pct?: number
    cpu_percent?: number
  }
}
interface GatewayRuntimeResponse {
  runtime?: RuntimeTelemetry
  services_runtime?: Array<{
    service: string
    status: string
    status_code?: number
    runtime?: RuntimeTelemetry
  }>
  services_runtime_summary?: {
    services_total?: number
    services_with_runtime?: number
    aggregate_requests?: number
    aggregate_errors?: number
    aggregate_error_rate_pct?: number
    aggregate_memory_rss_mb?: number
    aggregate_cpu_percent?: number
  }
  thresholds?: {
    errorRatePct?: number
    latencyMs?: number
    memoryMb?: number
  }
  threshold_alerts?: string[]
  policy_drift_alerts?: PolicyDriftAlert[]
  policy_drift_summary?: {
    total?: number
    high?: number
    medium?: number
    low?: number
    score?: number
    topImpactedAreas?: Array<{ area: string; count: number }>
  }
}

type SettingsCategory = 'operations' | 'aiPolicy' | 'businessComms' | 'priorityRules'
type PolicyDriftAlert = {
  id: string
  title: string
  severity: 'high' | 'medium' | 'low'
  status: 'drift' | 'stable'
  impact: string[]
  affectedAreas: string[]
  recommendation: string
}

function normalizeSettingsCategory(rawCategory: string | null): SettingsCategory | null {
  if (!rawCategory) return null
  const raw = rawCategory.trim()
  if (!raw) return null

  if (['operations', 'aiPolicy', 'businessComms', 'priorityRules'].includes(raw)) {
    return raw as SettingsCategory
  }

  const normalized = raw.toLowerCase().replace(/[\s_]+/g, '-')
  const aliases: Record<string, SettingsCategory> = {
    operations: 'operations',
    'ai-policy': 'aiPolicy',
    aipolicy: 'aiPolicy',
    'business-comms': 'businessComms',
    businesscomms: 'businessComms',
    'business-communication-controls': 'businessComms',
    notification: 'businessComms',
    'notification-configuration': 'businessComms',
    'priority-rules': 'priorityRules',
    priorityrules: 'priorityRules',
  }

  return aliases[normalized] ?? null
}

const DEFAULT_PROMPTS: Record<string, string> = {
  system_prompt:
    'You are a software SDK upgrade advisor for enterprise mobile SDK teams. Analyse the SDK details provided and return ONLY a strict JSON object with exactly these keys: upgrade_recommended (one of: Yes, No, Sufficient), upgrade_pros (list of strings), upgrade_cons (list of strings), no_upgrade_pros (list of strings), no_upgrade_cons (list of strings), recommendation_summary (concise paragraph). Be specific and technical. Do not include markdown, explanations, or code fences.',
  user_template:
    'SDK: {package}\nPlatform: {platform}\nCurrent version: {current}\nLatest version: {latest}\nUpdate priority: {update_needed}\nSDK status: {lib_status}\nNew version released: {new_version}\nVersion compare status: {version_status}\nNeeds manual review: {needs_manual_review}\nVersion window summary: {version_window_summary}\nRelease notes: {release_notes}\nDeprecation notes: {deprecation_notes}\n\nGenerate the JSON recommendation object.',
}

const PROMPT_HINTS: Record<string, string> = {
  system_prompt: 'No variables - static system context',
  user_template: '{package}, {platform}, {current}, {latest}, {update_needed}, {lib_status}, {new_version}, {version_status}, {needs_manual_review}, {version_window_summary}, {release_notes}, {deprecation_notes}',
}

export default function Settings() {
  const { isAdmin } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const qc = useQueryClient()
  const [refreshCadenceMs, setRefreshCadenceMs] = useState<number>(30_000)
  const [servicePage, setServicePage] = useState(1)
  const [servicePageSize, setServicePageSize] = useState(5)
  const [endpointPage, setEndpointPage] = useState(1)
  const [endpointPageSize, setEndpointPageSize] = useState(6)
  const [llmMsg, setLlmMsg] = useState<string | null>(null)
  const [appMsg, setAppMsg] = useState<string | null>(null)
  const [promptMsg, setPromptMsg] = useState<string | null>(null)
  const [llmEdits, setLlmEdits] = useState<Record<string, string>>({})
  const [llmApiKeyMode, setLlmApiKeyMode] = useState<'keep' | 'set' | 'clear'>('keep')
  const [llmApiKeyInput, setLlmApiKeyInput] = useState('')
  const [savingAppKey, setSavingAppKey] = useState<string | null>(null)
  const [savingPromptKey, setSavingPromptKey] = useState<string | null>(null)
  const [appEdits, setAppEdits] = useState<Record<string, string>>({})
  const [promptEdits, setPromptEdits] = useState<Record<string, string>>({})
  const [activeCategory, setActiveCategory] = useState<SettingsCategory>('operations')
  const businessCommsRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const normalized = normalizeSettingsCategory(searchParams.get('category'))
    if (normalized) setActiveCategory(normalized)
  }, [searchParams])

  useEffect(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('category', activeCategory)
      return next
    }, { replace: true })
  }, [activeCategory, setSearchParams])

  useEffect(() => {
    if (activeCategory !== 'businessComms') return
    const target = businessCommsRef.current
    if (!target) return
    requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }, [activeCategory])

  const openBusinessCommunicationControls = useCallback(() => {
    setActiveCategory('businessComms')
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('category', 'businessComms')
      next.set('focus', 'businessComms')
      return next
    }, { replace: true })

    requestAnimationFrame(() => {
      businessCommsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })

    setTimeout(() => {
      businessCommsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 120)
  }, [setSearchParams])

  const { data: llmData } = useQuery({
    queryKey: ['settings-llm'],
    queryFn: () => settingsApi.getLlm(),
    enabled: isAdmin,
  })
  const { data: appData, refetch: refetchApp } = useQuery({
    queryKey: ['settings-app'],
    queryFn: () => settingsApi.getApp(),
    enabled: isAdmin,
  })
  const { data: promptsData, refetch: refetchPrompts } = useQuery({
    queryKey: ['settings-prompts'],
    queryFn: () => settingsApi.getPrompts(),
    enabled: isAdmin,
  })
  const { data: healthData, refetch: recheckHealth, isFetching: healthLoading } = useQuery({
    queryKey: ['health-services'],
    queryFn: () => healthApi.services(),
  })
  const { data: runtimeData, refetch: refetchRuntime, isFetching: runtimeLoading } = useQuery({
    queryKey: ['health-runtime'],
    queryFn: () => healthApi.runtime(),
    refetchInterval: refreshCadenceMs,
  })

  // LLM settings — flat dict; skip internal/read-only fields
  const LLM_SKIP = new Set(['id', 'api_key', 'api_key_set', 'updated_by', 'updated_at'])
  const llmRaw = (llmData?.data ?? {}) as Record<string, unknown>
  const llmFields = Object.entries(llmRaw).filter(([k]) => !LLM_SKIP.has(k))
  const hasLlmChanges = Object.keys(llmEdits).length > 0 || llmApiKeyMode !== 'keep'

  // App settings — array of { key, value, description, is_sensitive }
  const appSettings: AppSetting[] = Array.isArray(appData?.data)
    ? (appData!.data as AppSetting[])
    : []
  const promptRows: PromptTemplate[] = Array.isArray(promptsData?.data)
    ? (promptsData!.data as PromptTemplate[])
    : []
  const promptsByKey = Object.fromEntries(promptRows.map((p) => [p.prompt_key, p])) as Record<string, PromptTemplate>

  // Health — raw response: { overall, gateway_status, services: [{ service, status, status_code }] }
  const healthRaw = healthData?.data as {
    overall?: string
    services?: { service: string; status: string; status_code: number }[]
  } | undefined
  const services = healthRaw?.services ?? []
  const unhealthyServices = services.filter((s) => s.status !== 'healthy').length
  const llmIsEnabled = Boolean(llmRaw.enabled && llmRaw.api_key_set)
  const runtimePayload = (runtimeData?.data ?? {}) as GatewayRuntimeResponse
  const runtime = runtimePayload.runtime
  const perServiceRuntime = runtimePayload.services_runtime ?? []
  const runtimeSummary = runtimePayload.services_runtime_summary
  const reqStats = runtime?.requests
  const resourceStats = runtime?.resources
  const gatewayStats = runtime?.gateway
  const fmtPct = (v?: number | null) => (typeof v === 'number' ? `${v.toFixed(2)}%` : 'N/A')
  const last5m = reqStats?.windows?.last_5m
  const last1h = reqStats?.windows?.last_1h

  const localThresholds = {
    errorRatePct: 2,
    latencyMs: 500,
    memoryMb: 700,
  }

  const backendThresholds = runtimePayload.thresholds
  const thresholds = {
    errorRatePct: backendThresholds?.errorRatePct ?? localThresholds.errorRatePct,
    latencyMs: backendThresholds?.latencyMs ?? localThresholds.latencyMs,
    memoryMb: backendThresholds?.memoryMb ?? localThresholds.memoryMb,
  }

  const localActiveAlerts = [
    (last5m?.error_rate_pct ?? 0) > thresholds.errorRatePct
      ? `5m error rate ${last5m?.error_rate_pct?.toFixed(2)}% exceeds ${thresholds.errorRatePct}%`
      : null,
    (last5m?.avg_latency_ms ?? 0) > thresholds.latencyMs
      ? `5m avg latency ${last5m?.avg_latency_ms?.toFixed(2)}ms exceeds ${thresholds.latencyMs}ms`
      : null,
    (resourceStats?.memory_rss_mb ?? 0) > thresholds.memoryMb
      ? `Gateway memory ${resourceStats?.memory_rss_mb?.toFixed(2)}MB exceeds ${thresholds.memoryMb}MB`
      : null,
  ].filter(Boolean) as string[]
  const activeAlerts = Array.isArray(runtimePayload.threshold_alerts) && runtimePayload.threshold_alerts.length > 0
    ? runtimePayload.threshold_alerts
    : localActiveAlerts

  const localPolicyDriftAlerts = useMemo(() => {
    const drifts: PolicyDriftAlert[] = []

    if (!llmIsEnabled) {
      drifts.push({
        id: 'llm-disabled',
        title: 'LLM disabled or missing key',
        severity: 'high',
        status: 'drift',
        impact: [
          'Recommendation confidence and AI guidance degrade to fallback mode',
          'HITL reviewers receive less contextual recommendation evidence',
        ],
        affectedAreas: ['Recommendations', 'HITL Review', 'Confidence Scoring'],
        recommendation: 'Re-enable LLM and validate API key and model endpoint health before next approval cycle.',
      })
    }

    const promptVersions = promptRows.map((p) => p.version ?? 1)
    const maxPromptVersion = promptVersions.length ? Math.max(...promptVersions) : 1
    if (maxPromptVersion > 1) {
      drifts.push({
        id: 'prompt-version-drift',
        title: `Prompt templates updated (v${maxPromptVersion})`,
        severity: 'medium',
        status: 'drift',
        impact: [
          'Recommendation wording/structure may change for governance reviewers',
          'Audit interpretation should validate prompt update intent and owner',
        ],
        affectedAreas: ['Prompt Contracts', 'Audit Interpretation', 'Reviewer Experience'],
        recommendation: 'Run spot-check comparisons for a sample SDK set and approve prompt revision evidence in audit.',
      })
    }

    const teamsEnabled = appSettings.find((s) => s.key === 'teams_enabled')?.value === '1'
    const emailEnabled = appSettings.find((s) => s.key === 'email_enabled')?.value === '1'
    if (!teamsEnabled) {
      drifts.push({
        id: 'teams-disabled',
        title: 'Teams channel disabled',
        severity: 'high',
        status: 'drift',
        impact: [
          'Business communication control loses group-channel escalation path',
          'Notification reliability posture may appear healthy while channel coverage is reduced',
        ],
        affectedAreas: ['Business Communication Controls', 'Notification Reliability Center', 'Escalation Workflow'],
        recommendation: 'Enable Teams channel and validate webhook configuration with a test notification.',
      })
    }
    if (!emailEnabled) {
      drifts.push({
        id: 'email-disabled',
        title: 'Email channel disabled',
        severity: 'high',
        status: 'drift',
        impact: [
          'Direct stakeholder notification path is unavailable',
          'Operational trust depends solely on Teams delivery state',
        ],
        affectedAreas: ['Business Communication Controls', 'Executive Weekly Digest Distribution', 'Stakeholder Alerting'],
        recommendation: 'Enable email channel and verify SMTP host, auth, TLS, and recipient list settings.',
      })
    }

    const scheduleEnabled = appSettings.find((s) => s.key === 'schedule_enabled')?.value === '1'
    if (!scheduleEnabled) {
      drifts.push({
        id: 'schedule-disabled',
        title: 'Schedule appears disabled in app policy settings',
        severity: 'medium',
        status: 'drift',
        impact: [
          'Automated pipeline execution may not run at expected governance cadence',
          'SLA forecasting confidence drops due to inconsistent queue velocity',
        ],
        affectedAreas: ['Scheduler', 'SLA Forecasting', 'Executive Dashboard'],
        recommendation: 'Enable scheduler policy and confirm cron + timezone alignment with governance cadence.',
      })
    }

    if (unhealthyServices > 0) {
      drifts.push({
        id: 'service-health-drift',
        title: `${unhealthyServices} service(s) unhealthy`,
        severity: 'medium',
        status: 'drift',
        impact: [
          'Policy controls may not apply uniformly across services',
          'Digest and reliability metrics can lag or be incomplete',
        ],
        affectedAreas: ['Service Health', 'Metrics Collection', 'Digest Completeness'],
        recommendation: 'Resolve unhealthy services, then refresh runtime and policy dashboards to confirm recovery.',
      })
    }

    return drifts
  }, [llmIsEnabled, promptRows, appSettings, unhealthyServices])

  const policyDriftAlerts: PolicyDriftAlert[] = Array.isArray(runtimePayload.policy_drift_alerts)
    && runtimePayload.policy_drift_alerts.length > 0
    ? runtimePayload.policy_drift_alerts
    : localPolicyDriftAlerts

  const policyDriftSummary = useMemo(() => {
    const backendSummary = runtimePayload.policy_drift_summary
    if (backendSummary && typeof backendSummary.total === 'number') {
      return {
        total: backendSummary.total,
        high: backendSummary.high ?? 0,
        medium: backendSummary.medium ?? 0,
        low: backendSummary.low ?? 0,
        score: backendSummary.score ?? ((backendSummary.high ?? 0) * 5 + (backendSummary.medium ?? 0) * 3 + (backendSummary.low ?? 0)),
        topImpactedAreas: backendSummary.topImpactedAreas ?? [],
      }
    }

    const high = policyDriftAlerts.filter((d) => d.severity === 'high').length
    const medium = policyDriftAlerts.filter((d) => d.severity === 'medium').length
    const low = policyDriftAlerts.filter((d) => d.severity === 'low').length
    const score = high * 5 + medium * 3 + low
    const impactedAreaCounts: Record<string, number> = {}
    for (const drift of policyDriftAlerts) {
      for (const area of drift.affectedAreas) {
        impactedAreaCounts[area] = (impactedAreaCounts[area] ?? 0) + 1
      }
    }
    const topImpactedAreas = Object.entries(impactedAreaCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([area, count]) => ({ area, count }))

    return {
      total: policyDriftAlerts.length,
      high,
      medium,
      low,
      score,
      topImpactedAreas,
    }
  }, [policyDriftAlerts, runtimePayload.policy_drift_summary])

  const trend5m = (reqStats?.trends?.last_5m ?? []).map((p: { bucket: number; requests: number; errors: number; avg_latency_ms: number }, i: number) => ({
    bucket: `${i + 1}m`,
    requests: p.requests,
    errors: p.errors,
    latency: p.avg_latency_ms,
  }))
  const trend1h = (reqStats?.trends?.last_1h ?? []).map((p: { bucket: number; requests: number; errors: number; avg_latency_ms: number }, i: number) => ({
    bucket: `${(i + 1) * 5}m`,
    requests: p.requests,
    errors: p.errors,
    latency: p.avg_latency_ms,
  }))
  const statusBreakdownEntries = Object.entries(reqStats?.status_breakdown ?? {}).sort((a, b) => Number(a[0]) - Number(b[0]))
  const statusChartData = statusBreakdownEntries.map(([status, count]) => ({ status: `HTTP ${status}`, count }))

  const perServiceResourceChart = perServiceRuntime.map((svc) => {
    const label = svc.service.replace(/-service$/, '').replace(/-/g, ' ')
    return {
      service: label,
      memory: Number((svc.runtime?.resources?.memory_rss_mb ?? 0).toFixed(2)),
      cpu: Number((svc.runtime?.resources?.cpu_percent ?? 0).toFixed(2)),
      requests: svc.runtime?.requests?.total ?? 0,
    }
  })

  const allEndpoints = reqStats?.top_endpoints ?? []
  const endpointTotalPages = Math.max(1, Math.ceil(allEndpoints.length / endpointPageSize))
  const safeEndpointPage = Math.min(endpointPage, endpointTotalPages)
  const pagedEndpoints = allEndpoints.slice((safeEndpointPage - 1) * endpointPageSize, safeEndpointPage * endpointPageSize)

  const serviceTotalPages = Math.max(1, Math.ceil(perServiceRuntime.length / servicePageSize))
  const safeServicePage = Math.min(servicePage, serviceTotalPages)
  const pagedServices = perServiceRuntime.slice((safeServicePage - 1) * servicePageSize, safeServicePage * servicePageSize)

  const saveLlmMut = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = { ...llmRaw, ...llmEdits }
      // API key behavior:
      // keep  -> send null (backend preserves existing key)
      // set   -> send entered value
      // clear -> send empty string (backend clears stored key)
      payload.api_key = llmApiKeyMode === 'set'
        ? llmApiKeyInput
        : llmApiKeyMode === 'clear'
          ? ''
          : null
      return settingsApi.updateLlm(payload)
    },
    onSuccess: () => {
      setLlmMsg('✅ LLM settings saved')
      setLlmEdits({})
      setLlmApiKeyMode('keep')
      setLlmApiKeyInput('')
      qc.invalidateQueries({ queryKey: ['settings-llm'] })
    },
    onError: () => setLlmMsg('❌ Failed to save LLM settings'),
  })

  const saveAppSetting = async (key: string, value: string) => {
    setSavingAppKey(key)
    try {
      await settingsApi.updateApp(key, { value, updated_by: 'admin' })
      setAppMsg(`✅ "${key}" updated`)
      setAppEdits((p) => { const n = { ...p }; delete n[key]; return n })
      refetchApp()
    } catch {
      setAppMsg(`❌ Failed to update "${key}"`)
    } finally {
      setSavingAppKey((prev) => (prev === key ? null : prev))
    }
  }

  const savePrompt = async (key: string) => {
    setSavingPromptKey(key)
    try {
      const template_text = (promptEdits[key] ?? promptsByKey[key]?.template_text ?? DEFAULT_PROMPTS[key] ?? '').trim()
      await settingsApi.upsertPrompt(key, {
        template_text,
        variables_hint: PROMPT_HINTS[key] ?? null,
        updated_by: 'admin',
      })
      setPromptMsg(`✅ Prompt "${key}" saved`)
      setPromptEdits((p) => {
        const n = { ...p }
        delete n[key]
        return n
      })
      refetchPrompts()
    } catch {
      setPromptMsg(`❌ Failed to save prompt "${key}"`)
    } finally {
      setSavingPromptKey((prev) => (prev === key ? null : prev))
    }
  }

  if (!isAdmin) {
    return (
      <SectionCard cardClassName="card p-12 text-center">
        <AlertCircle size={40} className="text-amber-400 mx-auto mb-3" />
        <p className="text-slate-600 font-medium">Admin access required</p>
      </SectionCard>
    )
  }

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title">Platform Settings</h1>
          <p className="page-subtitle">AI runtime policy, platform controls, and service readiness</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-primary py-1.5 text-xs" onClick={openBusinessCommunicationControls}>
            Open Business Communication Controls
          </button>
        </div>
      </div>

      <ExecutiveTriad
        impact={unhealthyServices > 0 ? `${unhealthyServices} service${unhealthyServices === 1 ? '' : 's'} are unhealthy and can affect policy execution.` : 'Core services are healthy and platform policy controls are available.'}
        owner="Platform Governance Administrator"
        nextAction={llmIsEnabled ? 'Validate prompt templates and monitor API performance and memory thresholds daily.' : 'Enable LLM credentials and verify runtime policy before the next governance cycle.'}
        tone={unhealthyServices > 0 ? 'critical' : llmIsEnabled ? 'positive' : 'warning'}
      />

      <SectionCard cardClassName="card p-4">
        <SectionBand
          title="Settings Category Navigator"
          subtitle="Choose one category at a time to reduce scrolling and focus operational decisions."
          className="mb-3"
        />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {[
            { key: 'operations' as const, label: 'Operations Intelligence' },
            { key: 'aiPolicy' as const, label: 'AI & Policy Governance' },
            { key: 'businessComms' as const, label: 'Business Communication Controls' },
            { key: 'priorityRules' as const, label: 'Priority Rules' },
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

      {activeCategory === 'operations' && (
        <>
          <div className="px-1">
            <h2 className="text-sm font-semibold text-slate-800">Operations Intelligence</h2>
            <p className="text-xs text-slate-500">Enterprise runtime, API traffic, and infrastructure health posture.</p>
          </div>

          <SectionCard cardClassName="card p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-700">API Runtime & Resource Telemetry</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Gateway uptime: {gatewayStats?.uptime_hours?.toFixed(2) ?? '0.00'}h
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              className="select py-1.5 text-xs"
              value={String(refreshCadenceMs)}
              onChange={(e) => setRefreshCadenceMs(Number(e.target.value))}
            >
              <option value="10000">Auto refresh: 10s</option>
              <option value="30000">Auto refresh: 30s</option>
              <option value="60000">Auto refresh: 60s</option>
              <option value="120000">Auto refresh: 2m</option>
              <option value="300000">Auto refresh: 5m</option>
            </select>
            <button className="btn-secondary py-1.5 text-xs" onClick={() => refetchRuntime()} disabled={runtimeLoading}>
              {runtimeLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Refresh Telemetry
            </button>
          </div>
        </div>

        <SectionBand
          title="Runtime Snapshot"
          subtitle="Cadence controls update all telemetry cards, charts, and operational tables below."
          className="mb-3"
        />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5">
            <p className="text-[11px] text-blue-700 font-medium">Total API Requests</p>
            <p className="text-xl font-bold text-blue-800">{(reqStats?.total ?? 0).toLocaleString()}</p>
            <p className="text-[10px] text-blue-600 mt-1">{(reqStats?.requests_per_minute_est ?? 0).toFixed(2)} req/min (est)</p>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
            <p className="text-[11px] text-amber-700 font-medium">Avg API Latency</p>
            <p className="text-xl font-bold text-amber-800">{(reqStats?.avg_latency_ms ?? 0).toFixed(2)} ms</p>
            <p className="text-[10px] text-amber-600 mt-1">Error rate: {(reqStats?.error_rate_pct ?? 0).toFixed(2)}%</p>
          </div>
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5">
            <p className="text-[11px] text-rose-700 font-medium">Gateway Memory (RSS)</p>
            <p className="text-xl font-bold text-rose-800">{(resourceStats?.memory_rss_mb ?? 0).toFixed(2)} MB</p>
            <p className="text-[10px] text-rose-600 mt-1">Process usage: {fmtPct(resourceStats?.memory_percent)}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
            <p className="text-[11px] text-slate-600 font-medium">CPU / System Memory</p>
            <p className="text-xl font-bold text-slate-800">{(resourceStats?.cpu_percent ?? 0).toFixed(2)}% CPU</p>
            <p className="text-[10px] text-slate-500 mt-1">System mem used: {fmtPct(resourceStats?.system_memory_used_pct)}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5">
            <p className="text-[11px] text-emerald-700 font-medium">5m Request Volume</p>
            <p className="text-xl font-bold text-emerald-800">{(last5m?.requests ?? 0).toLocaleString()}</p>
            <p className="text-[10px] text-emerald-600 mt-1">{(last5m?.requests_per_minute_est ?? 0).toFixed(2)} req/min</p>
          </div>
          <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2.5">
            <p className="text-[11px] text-sky-700 font-medium">1h Request Volume</p>
            <p className="text-xl font-bold text-sky-800">{(last1h?.requests ?? 0).toLocaleString()}</p>
            <p className="text-[10px] text-sky-600 mt-1">Err: {(last1h?.error_rate_pct ?? 0).toFixed(2)}%</p>
          </div>
          <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2.5">
            <p className="text-[11px] text-indigo-700 font-medium">Services with Runtime</p>
            <p className="text-xl font-bold text-indigo-800">{runtimeSummary?.services_with_runtime ?? 0} / {runtimeSummary?.services_total ?? 0}</p>
            <p className="text-[10px] text-indigo-600 mt-1">Per-service telemetry coverage</p>
          </div>
          <div className="rounded-lg border border-fuchsia-200 bg-fuchsia-50 px-3 py-2.5">
            <p className="text-[11px] text-fuchsia-700 font-medium">Aggregate Service Memory</p>
            <p className="text-xl font-bold text-fuchsia-800">{(runtimeSummary?.aggregate_memory_rss_mb ?? 0).toFixed(2)} MB</p>
            <p className="text-[10px] text-fuchsia-600 mt-1">CPU sum: {(runtimeSummary?.aggregate_cpu_percent ?? 0).toFixed(2)}%</p>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-3 mb-4">
          <p className="text-xs font-semibold text-slate-700 mb-2">Threshold Alerts</p>
          {activeAlerts.length === 0 ? (
            <p className="text-xs text-green-700">No active alerts. All observed metrics are within configured thresholds.</p>
          ) : (
            <div className="space-y-1.5">
              {activeAlerts.map((msg, idx) => (
                <div key={idx} className="text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1.5">
                  ⚠ {msg}
                </div>
              ))}
            </div>
          )}
        </div>

        <SectionBand
          title="Trend Analytics"
          subtitle="Short and long window trends for requests, errors, latency, and infrastructure pressure."
          className="mb-3"
        />

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
          <ChartSection
            title="5m Trend (1-minute buckets)"
            insight="Insight: 5-minute trend highlights immediate traffic or latency anomalies requiring operator intervention."
          >
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={trend5m}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Legend iconSize={8} />
                <Line type="monotone" dataKey="requests" stroke="#2563eb" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="errors" stroke="#dc2626" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="latency" stroke="#d97706" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartSection>
          <ChartSection
            title="1h Trend (5-minute buckets)"
            insight="Insight: 1-hour trend reveals sustained operational pressure and helps verify stabilization after incidents."
          >
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={trend1h}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Legend iconSize={8} />
                <Line type="monotone" dataKey="requests" stroke="#0f766e" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="errors" stroke="#be123c" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="latency" stroke="#7c3aed" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartSection>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
          <ChartSection
            title="HTTP Status Volume (Detailed)"
            insight="Insight: HTTP status concentration identifies reliability degradation patterns and API quality hotspots."
          >
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={statusChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="status" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#334155" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartSection>
          <ChartSection
            title="Per-Service Memory/CPU Comparison"
            insight="Insight: Service-level memory and CPU comparison pinpoints saturation sources before SLA impact expands."
          >
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={perServiceResourceChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="service" tick={{ fontSize: 10 }} interval={0} angle={-10} height={40} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Legend iconSize={8} />
                <Bar dataKey="memory" name="Memory (MB)" fill="#7c3aed" radius={[4, 4, 0, 0]} />
                <Bar dataKey="cpu" name="CPU (%)" fill="#0f766e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartSection>
        </div>

        <SectionBand
          title="Operational Tables"
          subtitle="Each table includes paging controls for executive review and operational drill-down."
          className="mb-3"
        />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-lg border border-slate-200 bg-white p-3">
            <p className="text-xs font-semibold text-slate-700 mb-2">HTTP Status Distribution</p>
            <div className="space-y-1.5">
              {statusBreakdownEntries.length === 0 ? (
                <p className="text-xs text-slate-400">No request samples yet.</p>
              ) : statusBreakdownEntries.map(([status, count]) => (
                <div key={status} className="flex items-center justify-between text-xs border border-slate-100 rounded px-2 py-1">
                  <span className="text-slate-600">HTTP {status}</span>
                  <span className="font-semibold text-slate-800">{count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-3">
            <p className="text-xs font-semibold text-slate-700 mb-2">Top API Endpoints (by request volume)</p>
            <div className="space-y-1.5 max-h-[220px] overflow-auto">
              {pagedEndpoints.length === 0 ? (
                <p className="text-xs text-slate-400">No endpoint telemetry available yet.</p>
              ) : pagedEndpoints.map((ep, idx) => (
                <div key={`${ep.method}-${ep.path}-${idx}`} className="border border-slate-100 rounded px-2 py-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-semibold text-slate-700 truncate">{ep.method} {ep.path}</p>
                    <span className="text-[10px] text-slate-500">{ep.requests} req</span>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-0.5">Errors: {ep.errors} · Avg latency: {ep.avg_latency_ms.toFixed(2)} ms</p>
                </div>
              ))}
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
              <RowsPerPageControl
                pageSize={endpointPageSize}
                options={[4, 6, 10]}
                onChange={(value) => {
                  setEndpointPageSize(value)
                  setEndpointPage(1)
                }}
                labelClassName="text-[10px] text-slate-500"
                selectClassName="select py-1 text-[10px]"
              />
              <PaginatedSectionFooter
                page={safeEndpointPage}
                totalPages={endpointTotalPages}
                onPrev={() => setEndpointPage((p) => Math.max(1, p - 1))}
                onNext={() => setEndpointPage((p) => Math.min(endpointTotalPages, p + 1))}
                prevLabel="Prev"
                nextLabel="Next"
                pagePrefix="Page"
                containerClassName="flex items-center gap-2"
                pageClassName="text-[10px] text-slate-500"
                buttonClassName="btn-secondary py-1 px-2 text-[10px]"
              />
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-3 mt-4">
          <p className="text-xs font-semibold text-slate-700 mb-2">Per-Service Runtime (Memory / CPU / Requests)</p>
          <div className="overflow-auto">
            <table className="w-full table-base">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Status</th>
                  <th>Requests</th>
                  <th>Error Rate</th>
                  <th>Avg Latency</th>
                  <th>Memory RSS</th>
                  <th>CPU</th>
                </tr>
              </thead>
              <tbody>
                {pagedServices.map((svc, idx) => {
                  const sReq = svc.runtime?.requests
                  const sRes = svc.runtime?.resources
                  return (
                    <tr key={`${svc.service}-${idx}`}>
                      <td>{svc.service}</td>
                      <td>{svc.status}</td>
                      <td>{(sReq?.total ?? 0).toLocaleString()}</td>
                      <td>{(sReq?.error_rate_pct ?? 0).toFixed(2)}%</td>
                      <td>{(sReq?.avg_latency_ms ?? 0).toFixed(2)} ms</td>
                      <td>{(sRes?.memory_rss_mb ?? 0).toFixed(2)} MB</td>
                      <td>{(sRes?.cpu_percent ?? 0).toFixed(2)}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
            <RowsPerPageControl
              pageSize={servicePageSize}
              options={[5, 10, 20]}
              onChange={(value) => {
                setServicePageSize(value)
                setServicePage(1)
              }}
              labelClassName="text-[10px] text-slate-500"
              selectClassName="select py-1 text-[10px]"
            />
            <PaginatedSectionFooter
              page={safeServicePage}
              totalPages={serviceTotalPages}
              onPrev={() => setServicePage((p) => Math.max(1, p - 1))}
              onNext={() => setServicePage((p) => Math.min(serviceTotalPages, p + 1))}
              prevLabel="Prev"
              nextLabel="Next"
              pagePrefix="Page"
              containerClassName="flex items-center gap-2"
              pageClassName="text-[10px] text-slate-500"
              buttonClassName="btn-secondary py-1 px-2 text-[10px]"
            />
          </div>
        </div>
          </SectionCard>

          {/* ── Service Health ─────────────────────────────────────────────── */}
          <SectionCard cardClassName="card p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-700">Service Health</h3>
            {healthRaw?.overall && (
              <p className={`text-xs mt-0.5 font-medium ${healthRaw.overall === 'healthy' ? 'text-green-600' : 'text-red-600'}`}>
                Overall: {healthRaw.overall}
              </p>
            )}
          </div>
          <button className="btn-secondary py-1.5 text-xs" onClick={() => recheckHealth()} disabled={healthLoading}>
            {healthLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {services.map(({ service, status, status_code }) => (
            <div
              key={service}
              className={`rounded-lg px-3 py-2.5 flex items-center gap-2 border ${
                status === 'healthy'
                  ? 'bg-green-50 border-green-200'
                  : 'bg-red-50 border-red-200'
              }`}
            >
              {status === 'healthy'
                ? <CheckCircle size={13} className="text-green-500 flex-shrink-0" />
                : <XCircle size={13} className="text-red-500 flex-shrink-0" />}
              <div className="min-w-0">
                <p className={`text-xs font-semibold truncate ${status === 'healthy' ? 'text-green-800' : 'text-red-800'}`}>
                  {service.replace(/-service$/, '').replace(/-/g, ' ')
                    .replace(/\b\w/g, (c) => c.toUpperCase())}
                </p>
                <p className="text-[10px] text-slate-400">HTTP {status_code}</p>
              </div>
            </div>
          ))}
        </div>
          </SectionCard>
        </>
      )}

      {activeCategory === 'aiPolicy' && (
        <>
          <div className="px-1">
            <h2 className="text-sm font-semibold text-slate-800">AI & Policy Governance</h2>
            <p className="text-xs text-slate-500">Model behavior, prompt contracts, and policy controls for recommendation quality.</p>
          </div>

          <SectionCard cardClassName="card p-5">
            <SectionBand
              title="Policy Drift Alerts"
              subtitle="Configuration drifts and impacted capabilities to prevent silent operational regressions."
              className="mb-3"
            />
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-center">
                <p className="text-base font-bold text-slate-800">{policyDriftSummary.total}</p>
                <p className="text-[10px] text-slate-500">Total Drifts</p>
              </div>
              <div className="rounded-lg border border-red-200 bg-red-50 px-2.5 py-2 text-center">
                <p className="text-base font-bold text-red-700">{policyDriftSummary.high}</p>
                <p className="text-[10px] text-red-600">High</p>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-center">
                <p className="text-base font-bold text-amber-700">{policyDriftSummary.medium}</p>
                <p className="text-[10px] text-amber-600">Medium</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-center">
                <p className="text-base font-bold text-slate-700">{policyDriftSummary.low}</p>
                <p className="text-[10px] text-slate-500">Low</p>
              </div>
              <div className="rounded-lg border border-purple-200 bg-purple-50 px-2.5 py-2 text-center">
                <p className="text-base font-bold text-purple-700">{policyDriftSummary.score}</p>
                <p className="text-[10px] text-purple-600">Risk Score</p>
              </div>
            </div>

            {policyDriftSummary.topImpactedAreas.length > 0 && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 mb-3">
                <p className="text-xs font-semibold text-slate-700 mb-2">Most impacted capabilities</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                  {policyDriftSummary.topImpactedAreas.map((row) => (
                    <div key={row.area} className="flex items-center justify-between text-xs border border-slate-200 rounded px-2 py-1 bg-white">
                      <span className="text-slate-600">{row.area}</span>
                      <span className="font-semibold text-slate-800">{row.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {policyDriftAlerts.length === 0 ? (
              <p className="text-xs text-green-700">No policy drift signals detected. Current AI and communication posture is stable.</p>
            ) : (
              <div className="space-y-2">
                {policyDriftAlerts.map((drift: PolicyDriftAlert) => (
                  <div
                    key={drift.title}
                    className={`rounded-lg border p-3 ${
                      drift.severity === 'high'
                        ? 'bg-red-50 border-red-200'
                        : drift.severity === 'medium'
                          ? 'bg-amber-50 border-amber-200'
                          : 'bg-slate-50 border-slate-200'
                    }`}
                  >
                    <p className={`text-xs font-semibold ${
                      drift.severity === 'high'
                        ? 'text-red-700'
                        : drift.severity === 'medium'
                          ? 'text-amber-700'
                          : 'text-slate-700'
                    }`}>{drift.title}</p>
                    <div className="mt-1 space-y-1">
                      {drift.impact.map((line: string) => (
                        <p key={line} className="text-[11px] text-slate-600">• {line}</p>
                      ))}
                    </div>
                    <div className="mt-2">
                      <p className="text-[11px] font-semibold text-slate-600">Affected Areas</p>
                      <p className="text-[11px] text-slate-500">{drift.affectedAreas.join(' · ')}</p>
                    </div>
                    <div className="mt-2 rounded border border-slate-200 bg-white px-2 py-1.5">
                      <p className="text-[11px] font-semibold text-slate-600">Recommended Action</p>
                      <p className="text-[11px] text-slate-600">{drift.recommendation}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>

          {/* ── LLM Configuration ─────────────────────────────────────────── */}
          <SectionCard cardClassName="card p-5">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-slate-700">LLM Configuration</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            API Key: {llmRaw.api_key_set ? '✅ configured' : '❌ not set'}
            {llmRaw.enabled === false
              ? <span className="ml-2 text-amber-600 font-semibold">⚠️ LLM disabled — using rule-based recommendations</span>
              : llmRaw.api_key_set ? <span className="ml-2 text-green-600 font-semibold">✅ LLM active</span> : null}
          </p>
        </div>
        {llmMsg && (
          <div className={`mb-3 px-3 py-2 rounded-lg text-xs border ${
            llmMsg.startsWith('✅')
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}>{llmMsg}</div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {llmFields.map(([key, val]) => (
            <div key={key}>
              <label className="block text-xs font-medium text-slate-600 mb-1 capitalize">
                {key.replace(/_/g, ' ')}
              </label>
              {typeof val === 'boolean' ? (
                <select
                  className="select"
                  value={llmEdits[key] ?? String(val)}
                  onChange={(e) => setLlmEdits((p) => ({ ...p, [key]: e.target.value }))}
                >
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
              ) : (
                <input
                  className="input"
                  type={key.includes('key') || key.includes('secret') || key.includes('password') ? 'password' : 'text'}
                  value={llmEdits[key] ?? String(val ?? '')}
                  onChange={(e) => setLlmEdits((p) => ({ ...p, [key]: e.target.value }))}
                  placeholder={val === null ? '(not set)' : undefined}
                />
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 border border-slate-200 rounded-lg p-4 bg-slate-50">
          <p className="text-xs font-semibold text-slate-700">API Key Behavior</p>
          <p className="text-[11px] text-slate-500 mt-1">
            Keep Existing keeps the current key unchanged. Set/Replace stores the new key value. Clear removes the stored key.
          </p>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2">
            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="radio"
                name="llm-api-key-mode"
                checked={llmApiKeyMode === 'keep'}
                onChange={() => setLlmApiKeyMode('keep')}
              />
              Keep Existing
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="radio"
                name="llm-api-key-mode"
                checked={llmApiKeyMode === 'set'}
                onChange={() => setLlmApiKeyMode('set')}
              />
              Set / Replace
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="radio"
                name="llm-api-key-mode"
                checked={llmApiKeyMode === 'clear'}
                onChange={() => setLlmApiKeyMode('clear')}
              />
              Clear
            </label>
          </div>

          {llmApiKeyMode === 'set' && (
            <div className="mt-3">
              <label className="block text-xs font-medium text-slate-600 mb-1">New API Key</label>
              <input
                className="input"
                type="password"
                value={llmApiKeyInput}
                onChange={(e) => setLlmApiKeyInput(e.target.value)}
                placeholder={llmRaw.api_key_set ? 'Enter new key to replace existing key' : 'Enter API key'}
              />
            </div>
          )}

          {llmApiKeyMode === 'clear' && (
            <p className="mt-3 text-[11px] text-red-600 font-medium">
              Saving now will clear the stored API key and disable LLM calls until a new key is set.
            </p>
          )}
        </div>

        <button
          className="btn-primary mt-4"
          onClick={() => { setLlmMsg(null); saveLlmMut.mutate() }}
          disabled={saveLlmMut.isPending || !hasLlmChanges || (llmApiKeyMode === 'set' && !llmApiKeyInput.trim())}
        >
          {saveLlmMut.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          {!hasLlmChanges ? 'No Changes' : 'Save LLM Settings'}
        </button>
          </SectionCard>

          {/* ── Prompt Templates ───────────────────────────────────────────── */}
          <SectionCard cardClassName="card p-5">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-slate-700">Prompt Templates</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            These templates are stored in DB and used by recommendation generation. Keep output contract strict JSON.
          </p>
        </div>
        {promptMsg && (
          <div className={`mb-3 px-3 py-2 rounded-lg text-xs border ${
            promptMsg.startsWith('✅')
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}>{promptMsg}</div>
        )}

        {Object.keys(DEFAULT_PROMPTS).map((key) => {
          const row = promptsByKey[key]
          const value = promptEdits[key] ?? row?.template_text ?? DEFAULT_PROMPTS[key]
          const dirty = promptEdits[key] !== undefined && promptEdits[key] !== (row?.template_text ?? DEFAULT_PROMPTS[key])
          return (
            <div key={key} className="mb-4 border border-slate-200 rounded-lg p-4 bg-slate-50">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <p className="text-xs font-semibold text-slate-700">{key}</p>
                  <p className="text-[11px] text-slate-500">{PROMPT_HINTS[key]}</p>
                </div>
                <div className="flex gap-2">
                  <button
                    className="btn-secondary py-1 px-3 text-xs"
                    onClick={() => setPromptEdits((p) => ({ ...p, [key]: DEFAULT_PROMPTS[key] }))}
                  >
                    Reset Default
                  </button>
                  <button
                    className="btn-primary py-1 px-3 text-xs"
                    onClick={() => savePrompt(key)}
                    disabled={!dirty || savingPromptKey === key}
                  >
                    {savingPromptKey === key ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
                    {savingPromptKey === key ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
              {row?.updated_at && (
                <p className="text-[11px] text-slate-400 mb-2">Last updated by {row.updated_by ?? 'unknown'} at {row.updated_at}</p>
              )}
              <textarea
                className="input min-h-[170px] font-mono text-xs"
                value={value}
                onChange={(e) => setPromptEdits((p) => ({ ...p, [key]: e.target.value }))}
              />
            </div>
          )
        })}
          </SectionCard>
        </>
      )}

      {/* ── App Settings ───────────────────────────────────────────────── */}
      {activeCategory === 'businessComms' && (appSettings.length > 0 ? (() => {
        const get = (k: string) => appEdits[k] ?? appSettings.find(s => s.key === k)?.value ?? ''
        const set = (k: string, v: string) => setAppEdits(p => ({ ...p, [k]: v }))
        const dirty = (k: string) => appEdits[k] !== undefined && appEdits[k] !== appSettings.find(s => s.key === k)?.value

        return (
          <div className="space-y-5" id="business-communication-controls" ref={businessCommsRef}>

            <div className="px-1">
              <h2 className="text-sm font-semibold text-slate-800">Business Communication Controls</h2>
              <p className="text-xs text-slate-500">Notification delivery channels and schedule visibility for business stakeholders.</p>
            </div>

            {appMsg && (
              <div className={`px-4 py-3 rounded-lg text-sm border ${
                appMsg.startsWith('✅')
                  ? 'bg-green-50 border-green-200 text-green-700'
                  : 'bg-red-50 border-red-200 text-red-700'
              }`}>
                {appMsg}
              </div>
            )}

            {/* ── Email Notifications ─── */}
            <SectionCard cardClassName="card p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-700">📧 Email Notifications</h3>
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input type="checkbox"
                    checked={get('email_enabled') === '1'}
                    onChange={e => { set('email_enabled', e.target.checked ? '1' : '0'); saveAppSetting('email_enabled', e.target.checked ? '1' : '0') }}
                    disabled={savingAppKey === 'email_enabled'}
                    className="w-3.5 h-3.5"
                  />
                  <span className="text-slate-600">Enabled</span>
                  {savingAppKey === 'email_enabled' && <Loader2 size={12} className="animate-spin text-slate-500" />}
                </label>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { k: 'smtp_host',         label: 'SMTP Host',         ph: 'smtp.office365.com', sensitive: false },
                  { k: 'smtp_port',         label: 'SMTP Port',         ph: '587',                sensitive: false },
                  { k: 'smtp_username',     label: 'SMTP Username',     ph: 'user@company.com',   sensitive: false },
                  { k: 'smtp_password',     label: 'SMTP Password',     ph: '••••••••',           sensitive: true  },
                  { k: 'smtp_from_address', label: 'From Address',      ph: 'noreply@company.com',sensitive: false },
                  { k: 'email_recipients',  label: 'Recipients (JSON)', ph: '["a@b.com"]',        sensitive: false },
                ].map(({ k, label, ph, sensitive }) => (
                  <div key={k}>
                    <label className="block text-xs text-slate-500 mb-1">{label}</label>
                    <div className="flex gap-2">
                      <input className="input text-xs flex-1"
                        type={sensitive ? 'password' : 'text'}
                        value={get(k)} placeholder={ph}
                        onChange={e => set(k, e.target.value)}
                      />
                      {dirty(k) && (
                        <button className="btn-primary py-1 px-3 text-xs" onClick={() => saveAppSetting(k, get(k))} disabled={savingAppKey === k}>
                          {savingAppKey === k ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <label className="flex items-center gap-2 text-xs mt-3 cursor-pointer">
                <input type="checkbox"
                  checked={get('smtp_use_tls') === '1'}
                  onChange={e => { set('smtp_use_tls', e.target.checked ? '1' : '0'); saveAppSetting('smtp_use_tls', e.target.checked ? '1' : '0') }}
                  disabled={savingAppKey === 'smtp_use_tls'}
                  className="w-3.5 h-3.5"
                />
                <span className="text-slate-600">Use TLS</span>
                {savingAppKey === 'smtp_use_tls' && <Loader2 size={12} className="animate-spin text-slate-500" />}
              </label>
            </SectionCard>

            {/* ── Microsoft Teams Notifications ─── */}
            <SectionCard cardClassName="card p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-700">💬 Microsoft Teams Notifications</h3>
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input type="checkbox"
                    checked={get('teams_enabled') === '1'}
                    onChange={e => { set('teams_enabled', e.target.checked ? '1' : '0'); saveAppSetting('teams_enabled', e.target.checked ? '1' : '0') }}
                    disabled={savingAppKey === 'teams_enabled'}
                    className="w-3.5 h-3.5"
                  />
                  <span className="text-slate-600">Enabled</span>
                  {savingAppKey === 'teams_enabled' && <Loader2 size={12} className="animate-spin text-slate-500" />}
                </label>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Incoming Webhook URL</label>
                <div className="flex gap-2">
                  <input className="input text-xs flex-1" type="password"
                    value={get('teams_webhook_url')}
                    placeholder="https://company.webhook.office.com/webhookb2/…"
                    onChange={e => set('teams_webhook_url', e.target.value)}
                  />
                  {dirty('teams_webhook_url') && (
                    <button className="btn-primary py-1 px-3 text-xs" onClick={() => saveAppSetting('teams_webhook_url', get('teams_webhook_url'))} disabled={savingAppKey === 'teams_webhook_url'}>
                      {savingAppKey === 'teams_webhook_url' ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
                      {savingAppKey === 'teams_webhook_url' ? 'Saving…' : 'Save'}
                    </button>
                  )}
                </div>
                <p className="text-[11px] text-slate-400 mt-1">
                  In Teams: channel → ⋯ → Workflows → "Post to a channel when a webhook request is received"
                </p>
              </div>
            </SectionCard>

            {/* ── Schedule ─── */}
            <SectionCard cardClassName="card p-5">
              <h3 className="text-sm font-semibold text-slate-700 mb-1">⏰ Schedule</h3>
              <p className="text-xs text-slate-400 mb-4">The pipeline schedule is managed on the <a href="/scheduler" className="text-primary-600 hover:underline">Scheduler page</a>.</p>
              <div className="flex flex-wrap gap-4 items-center text-xs text-slate-600 bg-slate-50 rounded-lg px-4 py-3">
                <span>Cron: <code className="font-mono bg-white px-1 rounded">{get('schedule_cron') || '0 2 * * *'}</code></span>
                <span>Enabled: <strong>{get('schedule_enabled') === '1' ? 'Yes' : 'No'}</strong></span>
                <span>Timezone: <strong>{get('schedule_timezone') || 'UTC'}</strong></span>
              </div>
            </SectionCard>

          </div>
        )
      })() : (
        <SectionCard cardClassName="card p-5">
          <p className="text-sm text-slate-500">No business communication settings are available in this environment.</p>
        </SectionCard>
      ))}

      {/* ── Priority Classification Rules ────────────────────────────────── */}
      {activeCategory === 'priorityRules' && <PriorityRulesSection />}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Priority Classification Rules Section
// ═══════════════════════════════════════════════════════════════════════════════

const TIER_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  CRITICAL: { label: '🔴 Critical', color: 'text-red-700',    bg: 'bg-red-50',    border: 'border-red-200' },
  HIGH:     { label: '🟠 High',     color: 'text-orange-700', bg: 'bg-orange-50', border: 'border-orange-200' },
  MODERATE: { label: '🟡 Moderate', color: 'text-amber-700',  bg: 'bg-amber-50',  border: 'border-amber-200' },
  LOW:      { label: '🔵 Low',      color: 'text-blue-700',   bg: 'bg-blue-50',   border: 'border-blue-200' },
}

const DEFAULT_KEYWORDS: Record<string, string[]> = {
  CRITICAL: ['cve', 'vulnerability', 'critical', 'zero-day', 'remote code execution', 'rce',
             'actively exploited', 'must update', 'immediate action', 'breaking change',
             'incompatible', 'data breach'],
  HIGH:     ['security fix', 'security patch', 'security update', 'authentication', 'authorization',
             'payment', 'pci', 'gdpr', 'compliance', 'crash fix', 'memory leak', 'data loss',
             'regression', 'breaking', 'deprecated', 'end of life', 'eol', '3ds', 'force update'],
  MODERATE: ['bug fix', 'bugfix', 'fixed', 'improvement', 'performance', 'stability',
             'enhancement', 'api change', 'behaviour change', 'recommended'],
  LOW:      ['minor', 'cosmetic', 'typo', 'documentation', 'readme', 'refactor',
             'cleanup', 'optional', 'new feature'],
}

const DEFAULT_SDK_FLOORS: Array<{ sdk: string; floor: string }> = [
  { sdk: 'ACI OPPWa',           floor: 'HIGH' },
  { sdk: 'ACI IPWorks',         floor: 'HIGH' },
  { sdk: 'Braintree',           floor: 'HIGH' },
  { sdk: 'PayPal',              floor: 'HIGH' },
  { sdk: 'KlarnaMobileSDK',     floor: 'HIGH' },
  { sdk: 'Gigya',               floor: 'HIGH' },
  { sdk: 'GigyaAuth',           floor: 'HIGH' },
  { sdk: 'GigyaTfa',            floor: 'HIGH' },
  { sdk: 'SQLCipher',           floor: 'HIGH' },
  { sdk: 'Firebase',            floor: 'MODERATE' },
  { sdk: 'FirebaseCrashlytics', floor: 'MODERATE' },
  { sdk: 'AppsFlyer',           floor: 'MODERATE' },
  { sdk: 'ContentsquareSDK',    floor: 'MODERATE' },
  { sdk: 'Alamofire',           floor: 'LOW' },
  { sdk: 'Glide',               floor: 'LOW' },
  { sdk: 'SDWebImage',          floor: 'LOW' },
]

const SETTING_KEY = 'priority_rules_config'

interface PriorityConfig {
  keywords: Record<string, string[]>
  sdk_floors: Array<{ sdk: string; floor: string }>
  version_bump: { MAJOR: string; MINOR: string; PATCH: string }
}

const DEFAULT_CONFIG: PriorityConfig = {
  keywords:     DEFAULT_KEYWORDS,
  sdk_floors:   DEFAULT_SDK_FLOORS,
  version_bump: { MAJOR: 'CRITICAL', MINOR: 'HIGH', PATCH: 'MODERATE' },
}

function PriorityRulesSection() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const [openTier, setOpenTier] = useState<string | null>(null)
  const [sdkPage, setSdkPage] = useState(1)
  const [sdkPageSize, setSdkPageSize] = useState(8)
  const [newKw, setNewKw] = useState<Record<string, string>>({})
  const [newSdk, setNewSdk] = useState({ sdk: '', floor: 'HIGH' })
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  const { data: settingsData } = useQuery({
    queryKey: ['settings-app'],
    queryFn: () => settingsApi.getApp(),
  })

  // Load saved config from settings — deep merge so empty saved fields fall back to defaults
  const saved = (() => {
    const items = (settingsData?.data as Array<{ key: string; value: unknown }> | undefined) ?? []
    const raw = items.find(i => i.key === SETTING_KEY)?.value
    if (!raw) return null
    try {
      return JSON.parse(typeof raw === 'string' ? raw : JSON.stringify(raw)) as Partial<PriorityConfig>
    } catch { return null }
  })()

  // Deep merge: only use saved sub-fields if they are non-empty, else fall back to DEFAULT
  const mergeConfig = useCallback((partial: Partial<PriorityConfig> | null): PriorityConfig => {
    if (!partial) return DEFAULT_CONFIG
    const kw = partial.keywords && Object.keys(partial.keywords).length > 0
      ? partial.keywords : DEFAULT_CONFIG.keywords
    const sdks = partial.sdk_floors && partial.sdk_floors.length > 0
      ? partial.sdk_floors : DEFAULT_CONFIG.sdk_floors
    return {
      keywords:     kw,
      sdk_floors:   sdks,
      version_bump: partial.version_bump ?? DEFAULT_CONFIG.version_bump,
    }
  }, [])

  const [config, setConfig] = useState<PriorityConfig>(DEFAULT_CONFIG)
  const [initialized, setInitialized] = useState(false)

  // Sync from API once loaded (using useCallback-based merge to avoid re-render issues)
  const syncedConfig = initialized ? config : mergeConfig(saved)
  if (!initialized && settingsData) {
    setConfig(mergeConfig(saved))
    setInitialized(true)
  }

  const sdkTotalPages = Math.max(1, Math.ceil(syncedConfig.sdk_floors.length / sdkPageSize))
  const safeSdkPage = Math.min(sdkPage, sdkTotalPages)
  const pagedSdkFloors = syncedConfig.sdk_floors.slice((safeSdkPage - 1) * sdkPageSize, safeSdkPage * sdkPageSize)

  const saveMut = useMutation({
    mutationFn: () => settingsApi.updateApp(SETTING_KEY, {
      value: JSON.stringify(syncedConfig),
      updated_by: user?.username ?? 'admin',
    }),
    onSuccess: () => {
      setSaveMsg('✅ Priority rules saved — re-run the pipeline to apply.')
      qc.invalidateQueries({ queryKey: ['settings-app'] })
      setTimeout(() => setSaveMsg(null), 5000)
    },
    onError: () => setSaveMsg('❌ Failed to save rules. Try again.'),
  })

  const addKeyword = (tier: string) => {
    const kw = (newKw[tier] ?? '').trim().toLowerCase()
    if (!kw) return
    setConfig(c => ({
      ...c,
      keywords: { ...c.keywords, [tier]: [...(c.keywords[tier] ?? []), kw] },
    }))
    setNewKw(p => ({ ...p, [tier]: '' }))
  }

  const removeKeyword = (tier: string, kw: string) =>
    setConfig(c => ({
      ...c,
      keywords: { ...c.keywords, [tier]: (c.keywords[tier] ?? []).filter(k => k !== kw) },
    }))

  const addSdk = () => {
    if (!newSdk.sdk.trim()) return
    setConfig(c => ({ ...c, sdk_floors: [...c.sdk_floors, { sdk: newSdk.sdk.trim(), floor: newSdk.floor }] }))
    setNewSdk({ sdk: '', floor: 'HIGH' })
  }

  const removeSdk = (sdk: string) =>
    setConfig(c => ({ ...c, sdk_floors: c.sdk_floors.filter(s => s.sdk !== sdk) }))

  const resetToDefaults = () => {
    setConfig(DEFAULT_CONFIG)
    setSaveMsg(null)
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-800">🎯 Priority Classification Rules</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Configure how library upgrade priorities (Critical / High / Moderate / Low) are assigned.
            Changes take effect on the next pipeline run.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary py-1.5 text-xs" onClick={resetToDefaults}>
            Reset Defaults
          </button>
          <button className="btn-primary py-1.5" onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
            {saveMut.isPending ? <><Loader2 size={13} className="animate-spin" /> Saving…</> : <><Save size={13} /> Save Rules</>}
          </button>
        </div>
      </div>

      {saveMsg && (
        <div className={`px-4 py-2.5 rounded-lg text-xs font-medium border flex items-center gap-2 ${
          saveMsg.startsWith('✅') ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'
        }`}>
          {saveMsg}
        </div>
      )}

      {/* How it works banner */}
      <SectionCard cardClassName="card p-4 flex items-start gap-3 border-primary-200 bg-orange-50">
        <Info size={15} className="text-primary-600 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-slate-700 space-y-0.5">
          <p className="font-semibold text-slate-800">How the classification engine works</p>
          <p>1. <strong>Version bump</strong> (Rule 1) → base priority from the version change</p>
          <p>2. <strong>Keyword scan</strong> (Rule 2) → scans release notes for matching words</p>
          <p>3. <strong>Merge</strong> (Rule 3) → always takes the <em>higher</em> of the two</p>
          <p>4. <strong>SDK floor</strong> (Rule 4) → applies minimum priority for sensitive SDKs</p>
        </div>
      </SectionCard>

      {/* Rule 1 — Version Bump (fixed, display only) */}
      <SectionCard cardClassName="card p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-1">Rule 1 — Version Bump Priority</h3>
        <p className="text-xs text-slate-400 mb-4">Based on semantic versioning (MAJOR.MINOR.PATCH). These mappings are fixed by the engine design.</p>
        <div className="grid grid-cols-3 gap-3">
          {([
            { bump: 'MAJOR', tier: 'CRITICAL', example: '4.x → 5.x', desc: 'Breaking API changes likely' },
            { bump: 'MINOR', tier: 'HIGH',     example: '2.8 → 2.11', desc: 'New features, minor breaking' },
            { bump: 'PATCH', tier: 'MODERATE', example: '1.2.3 → 1.2.5', desc: 'Bug fixes, low risk' },
          ] as const).map(({ bump, tier, example, desc }) => {
            const m = TIER_META[tier]
            return (
              <div key={bump} className={`rounded-xl border ${m.border} ${m.bg} p-4`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-600 uppercase tracking-wide">{bump} bump</span>
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${m.bg} ${m.color} border ${m.border}`}>{m.label}</span>
                </div>
                <code className="text-[11px] text-slate-500 block">{example}</code>
                <p className="text-[10px] text-slate-400 mt-1">{desc}</p>
              </div>
            )
          })}
        </div>
      </SectionCard>

      {/* Rule 2 — Keyword Rules (editable) */}
      <SectionCard cardClassName="card p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-1">Rule 2 — Release Notes Keyword Rules</h3>
        <p className="text-xs text-slate-400 mb-4">
          The engine scans release notes for these keywords. The <strong>highest matching tier wins</strong>.
          Add or remove keywords for each priority level.
        </p>
        <div className="space-y-3">
          {(['CRITICAL', 'HIGH', 'MODERATE', 'LOW'] as const).map((tier) => {
            const m = TIER_META[tier]
            const open = openTier === tier
            const kws = syncedConfig.keywords[tier] ?? []
            return (
              <div key={tier} className={`rounded-xl border ${m.border} overflow-hidden`}>
                {/* Tier header toggle */}
                <button
                  className={`w-full flex items-center justify-between px-4 py-3 ${m.bg} hover:opacity-90 transition-opacity`}
                  onClick={() => setOpenTier(open ? null : tier)}
                >
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-bold ${m.color}`}>{m.label}</span>
                    <span className="text-[11px] text-slate-500">{kws.length} keywords</span>
                  </div>
                  {open ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
                </button>

                {open && (
                  <div className="px-4 py-3 bg-white">
                    {/* Keyword chips */}
                    <div className="flex flex-wrap gap-1.5 mb-3 min-h-[32px]">
                      {kws.map((kw) => (
                        <span key={kw} className={`inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-full border ${m.border} ${m.bg} ${m.color}`}>
                          {kw}
                          <button
                            onClick={() => removeKeyword(tier, kw)}
                            className="hover:text-red-600 ml-0.5 transition-colors"
                            title="Remove keyword"
                          >
                            <XCircle size={11} />
                          </button>
                        </span>
                      ))}
                      {kws.length === 0 && <span className="text-xs text-slate-400 italic">No keywords — add some below</span>}
                    </div>
                    {/* Add keyword input */}
                    <div className="flex gap-2">
                      <input
                        className="input text-xs flex-1"
                        placeholder={`Add ${tier.toLowerCase()} keyword (e.g. "cve", "security fix")`}
                        value={newKw[tier] ?? ''}
                        onChange={(e) => setNewKw(p => ({ ...p, [tier]: e.target.value }))}
                        onKeyDown={(e) => { if (e.key === 'Enter') addKeyword(tier) }}
                      />
                      <button className="btn-secondary py-1.5 px-3 text-xs" onClick={() => addKeyword(tier)}>
                        <Plus size={12} /> Add
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </SectionCard>

      {/* Rule 4 — SDK Sensitivity (editable) */}
      <SectionCard cardClassName="card p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-1">Rule 4 — SDK Sensitivity Floor</h3>
        <p className="text-xs text-slate-400 mb-4">
          Security/payment SDKs get a <strong>minimum priority floor</strong> regardless of version bump size.
          E.g. a PATCH bump on a payment SDK still gets elevated to HIGH.
        </p>
        <div className="overflow-x-auto mb-4">
          <table className="w-full table-base text-xs">
            <thead>
              <tr>
                <th className="w-1/2">SDK Name (matches package name partially)</th>
                <th>Minimum Priority Floor</th>
                <th className="w-16"></th>
              </tr>
            </thead>
            <tbody>
              {pagedSdkFloors.map(({ sdk, floor }) => {
                const m = TIER_META[floor] ?? TIER_META.HIGH
                return (
                  <tr key={sdk}>
                    <td className="font-mono text-slate-700">{sdk}</td>
                    <td>
                      <select
                        className="select text-xs w-auto py-1"
                        value={floor}
                        onChange={(e) => setConfig(c => ({
                          ...c,
                          sdk_floors: c.sdk_floors.map(s => s.sdk === sdk ? { ...s, floor: e.target.value } : s),
                        }))}
                      >
                        {['CRITICAL','HIGH','MODERATE','LOW'].map(t => (
                          <option key={t} value={t}>{TIER_META[t].label}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <button
                        className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors"
                        onClick={() => removeSdk(sdk)}
                        title="Remove SDK"
                      >
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="mt-2 mb-4 flex items-center justify-between text-[10px] text-slate-500">
          <RowsPerPageControl
            pageSize={sdkPageSize}
            options={[8, 12, 20]}
            onChange={(value) => {
              setSdkPageSize(value)
              setSdkPage(1)
            }}
            labelClassName="text-[10px] text-slate-500"
            selectClassName="select py-1 text-[10px]"
          />
          <PaginatedSectionFooter
            page={safeSdkPage}
            totalPages={sdkTotalPages}
            onPrev={() => setSdkPage((p) => Math.max(1, p - 1))}
            onNext={() => setSdkPage((p) => Math.min(sdkTotalPages, p + 1))}
            prevLabel="Prev"
            nextLabel="Next"
            pagePrefix="Page"
            containerClassName="flex items-center gap-2"
            pageClassName="text-[10px] text-slate-500"
            buttonClassName="btn-secondary py-1 px-2 text-[10px]"
          />
        </div>
        {/* Add SDK row */}
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="block text-[11px] text-slate-500 mb-1">SDK / Package name (partial match)</label>
            <input
              className="input text-xs"
              placeholder="e.g. PayPal, com.braintree, KlarnaMobileSDK"
              value={newSdk.sdk}
              onChange={(e) => setNewSdk(p => ({ ...p, sdk: e.target.value }))}
              onKeyDown={(e) => { if (e.key === 'Enter') addSdk() }}
            />
          </div>
          <div>
            <label className="block text-[11px] text-slate-500 mb-1">Floor</label>
            <select className="select text-xs w-auto" value={newSdk.floor}
              onChange={(e) => setNewSdk(p => ({ ...p, floor: e.target.value }))}>
              {['CRITICAL','HIGH','MODERATE','LOW'].map(t => (
                <option key={t} value={t}>{TIER_META[t].label}</option>
              ))}
            </select>
          </div>
          <button className="btn-primary py-2 px-4 text-xs whitespace-nowrap" onClick={addSdk}>
            <Plus size={12} /> Add SDK
          </button>
        </div>
      </SectionCard>
    </div>
  )
}
