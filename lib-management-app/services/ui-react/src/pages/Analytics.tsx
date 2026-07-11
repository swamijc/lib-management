import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi, settingsApi } from '../api/client'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend,
} from 'recharts'
import MetricCard from '../components/MetricCard'
import ExecutiveTriad from '../components/ExecutiveTriad'
import { PaginatedSectionFooter, RowsPerPageControl } from '../components/PaginatedSectionControls'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import ChartSection from '../components/ChartSection'
import { DollarSign, Zap, Clock, TrendingUp } from 'lucide-react'

type UsageStats = {
  total_calls?: number
  total_tokens?: number
  total_prompt_tokens?: number
  total_completion_tokens?: number
  total_cost_usd?: number
  avg_latency_ms?: number | null
  calls_this_month?: number
  cost_this_month?: number
}

type ModelBreakdown = {
  model: string
  calls?: number
  tokens?: number
  cost?: number
  avg_latency_ms?: number | null
  last_used_at?: string | null
}

type UsageEntry = {
  id?: number
  logged_at?: string
  model?: string
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  estimated_cost_usd?: number
  latency_ms?: number | null
  library_id?: number | null
}

type DailyPoint = {
  date: string
  tokens_used: number
  calls: number
  cost_usd: number
}

type LlmConfigView = {
  provider?: string
  model_name?: string
  enabled?: boolean
  api_key_set?: boolean
}

export default function Analytics() {
  const [modelPage, setModelPage] = useState(1)
  const [modelPageSize, setModelPageSize] = useState(8)
  const [recentPage, setRecentPage] = useState(1)
  const [recentPageSize, setRecentPageSize] = useState(10)

  const { data, isError } = useQuery({ queryKey: ['llm-usage'], queryFn: () => analyticsApi.usage() })
  const { data: llmCfg } = useQuery({ queryKey: ['settings-llm'], queryFn: () => settingsApi.getLlm() })

  const apiData = data?.data as { stats?: UsageStats; models_breakdown?: ModelBreakdown[]; recent_entries?: UsageEntry[] } | undefined
  const stats = (apiData?.stats ?? {}) as UsageStats
  const recentEntries = (apiData?.recent_entries ?? []) as UsageEntry[]
  const byModel = ((apiData?.models_breakdown ?? []) as ModelBreakdown[]).map((m) => ({
    model: m.model,
    calls: Number(m.calls ?? 0),
    tokens: Number(m.tokens ?? 0),
    cost: Number(m.cost ?? 0),
    avg_latency_ms: m.avg_latency_ms ?? null,
    last_used_at: m.last_used_at ?? null,
  }))
  const llmConfig = (llmCfg?.data ?? {}) as LlmConfigView

  const modelTotalPages = Math.max(1, Math.ceil(byModel.length / modelPageSize))
  const safeModelPage = Math.min(modelPage, modelTotalPages)
  const modelStart = (safeModelPage - 1) * modelPageSize
  const modelEnd = Math.min(modelStart + modelPageSize, byModel.length)
  const pagedModels = useMemo(() => byModel.slice(modelStart, modelEnd), [byModel, modelStart, modelEnd])

  const recentTotalPages = Math.max(1, Math.ceil(recentEntries.length / recentPageSize))
  const safeRecentPage = Math.min(recentPage, recentTotalPages)
  const recentStart = (safeRecentPage - 1) * recentPageSize
  const recentEnd = Math.min(recentStart + recentPageSize, recentEntries.length)
  const pagedRecentEntries = useMemo(() => recentEntries.slice(recentStart, recentEnd), [recentEntries, recentStart, recentEnd])

  const dailyMap = new Map<string, DailyPoint>()
  for (const entry of recentEntries) {
    const rawDate = (entry.logged_at ?? '').slice(0, 10)
    if (!rawDate) continue
    const prev = dailyMap.get(rawDate) ?? { date: rawDate, tokens_used: 0, calls: 0, cost_usd: 0 }
    prev.tokens_used += Number(entry.total_tokens ?? 0)
    prev.calls += 1
    prev.cost_usd += Number(entry.estimated_cost_usd ?? 0)
    dailyMap.set(rawDate, prev)
  }
  const daily = Array.from(dailyMap.values())
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-14)

  // LLM is not active if API 404s or total_calls is 0/null
  const llmNotConfigured = isError || !stats.total_calls || stats.total_calls === 0

  if (llmNotConfigured) {
    return (
      <div className="space-y-6">
        <div className="page-header">
          <div>
            <h1 className="page-title">AI Cost & Performance</h1>
            <p className="page-subtitle">AI utilization, spend, latency, and model efficiency insights</p>
          </div>
        </div>

        <ExecutiveTriad
          impact="AI spend governance is currently unavailable because no LLM usage has been recorded."
          owner="AI Platform Owner"
          nextAction="Enable LLM in Platform Settings, run pipeline once, then review daily cost and latency trend."
          tone="warning"
        />

        <SectionCard cardClassName="card p-10 text-center max-w-lg mx-auto">
          <div className="text-5xl mb-4">🤖</div>
          <h2 className="text-lg font-semibold text-slate-800 mb-2">No LLM Usage Recorded</h2>
          <p className="text-sm text-slate-500 leading-relaxed mb-4">
            The platform is running on the <strong>built-in rule engine</strong> which generates
            recommendations without AI — no setup needed. To enable AI-powered recommendations:
          </p>
          <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-left text-xs text-slate-600 space-y-1.5">
            <p>1. Go to <strong>⚙️ Settings → LLM Configuration</strong></p>
            <p>2. Ensure an API key is saved and <strong>Enable LLM is ON</strong></p>
            <p>3. Run the pipeline — usage will appear here</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Cost & Performance</h1>
          <p className="page-subtitle">AI utilization, spend, latency, and model efficiency insights</p>
        </div>
      </div>

      <ExecutiveTriad
        impact={`${(stats.total_calls ?? 0).toLocaleString()} LLM calls with $${(stats.total_cost_usd ?? 0).toFixed(4)} total spend recorded.`}
        owner="AI Platform Owner"
        nextAction="Review model breakdown, then optimize high-cost prompts and latency outliers in the next release cycle."
        tone={(stats.total_cost_usd ?? 0) > 0 ? 'neutral' : 'warning'}
      />

      <SectionBand
        title="Cost Governance Snapshot"
        subtitle="Business-level usage, spend, and token posture for the active LLM model stack."
      />

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <MetricCard
          title="Total LLM Calls"
          value={(stats.total_calls ?? 0).toLocaleString()}
          icon={<TrendingUp size={18} />}
        />
        <MetricCard
          title="Total Tokens"
          value={(stats.total_tokens ?? 0).toLocaleString()}
          icon={<Zap size={18} />}
          color="blue"
        />
        <MetricCard
          title="Total Cost"
          value={`$${(stats.total_cost_usd ?? 0).toFixed(4)}`}
          subtitle={`$${(stats.cost_this_month ?? 0).toFixed(4)} this month`}
          icon={<DollarSign size={18} />}
          color="amber"
        />
        <MetricCard
          title="Avg Latency"
          value={stats.avg_latency_ms ? `${Math.round(stats.avg_latency_ms)}ms` : 'N/A'}
          icon={<Clock size={18} />}
          color="purple"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricCard
          title="Configured Model"
          value={llmConfig.model_name || 'N/A'}
          subtitle={`${llmConfig.provider || 'N/A'}${llmConfig.enabled ? ' | enabled' : ' | disabled'}`}
          icon={<TrendingUp size={18} />}
        />
        <MetricCard
          title="Prompt Tokens"
          value={(stats.total_prompt_tokens ?? 0).toLocaleString()}
          icon={<Zap size={18} />}
          color="blue"
        />
        <MetricCard
          title="Completion Tokens"
          value={(stats.total_completion_tokens ?? 0).toLocaleString()}
          icon={<Zap size={18} />}
          color="amber"
        />
      </div>

      {/* Daily trend */}
      {daily.length > 0 && (
        <SectionBand
          title="Trend Analytics"
          subtitle="Daily activity and model distribution for usage and token intensity."
        />
      )}

      {/* Daily trend */}
      {daily.length > 0 && (
        <SectionCard cardClassName="card p-5">
          <ChartSection
            title="Daily LLM Activity"
            insight="Insight: Token usage trend reflects workload intensity and predicts near-term inference cost exposure."
          >
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={daily}>
                <defs>
                  <linearGradient id="callsGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip
                  contentStyle={{ fontSize: 12, border: '1px solid #e2e8f0', borderRadius: 8 }}
                />
                <Area dataKey="tokens_used" stroke="#3b82f6" fill="url(#callsGrad)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartSection>
        </SectionCard>
      )}

      {/* By model */}
      {byModel.length > 0 && (
        <SectionCard cardClassName="card p-5">
          <ChartSection
            className="mb-4"
            title="Usage by Model"
            insight="Insight: Model-level call and token distribution reveals optimization targets for cost and latency."
          >
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={byModel}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="model" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip contentStyle={{ fontSize: 12, border: '1px solid #e2e8f0', borderRadius: 8 }} />
                <Legend iconSize={8} />
                <Bar dataKey="calls" fill="#6366f1" radius={[3, 3, 0, 0]} />
                <Bar dataKey="tokens" fill="#10b981" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartSection>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-200">
                  <th className="text-left py-2">Model</th>
                  <th className="text-right py-2">Calls</th>
                  <th className="text-right py-2">Tokens</th>
                  <th className="text-right py-2">Cost (USD)</th>
                  <th className="text-right py-2">Avg Latency</th>
                </tr>
              </thead>
              <tbody>
                {pagedModels.map((row) => (
                  <tr key={row.model} className="border-b border-slate-100 text-slate-700">
                    <td className="py-2 font-medium">{row.model}</td>
                    <td className="py-2 text-right">{row.calls.toLocaleString()}</td>
                    <td className="py-2 text-right">{row.tokens.toLocaleString()}</td>
                    <td className="py-2 text-right">${row.cost.toFixed(6)}</td>
                    <td className="py-2 text-right">{row.avg_latency_ms ? `${Math.round(row.avg_latency_ms)}ms` : 'N/A'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-[10px] text-slate-500">
            <div className="flex items-center gap-2">
              <span>Showing {byModel.length ? modelStart + 1 : 0}-{modelEnd} of {byModel.length}</span>
              <RowsPerPageControl
                pageSize={modelPageSize}
                options={[5, 8, 12]}
                onChange={(value) => {
                  setModelPageSize(value)
                  setModelPage(1)
                }}
                labelClassName="text-[10px] text-slate-500"
                selectClassName="select py-1 text-[10px]"
              />
            </div>
            <PaginatedSectionFooter
              page={safeModelPage}
              totalPages={modelTotalPages}
              onPrev={() => setModelPage((p) => Math.max(1, p - 1))}
              onNext={() => setModelPage((p) => Math.min(modelTotalPages, p + 1))}
              prevLabel="Prev"
              nextLabel="Next"
              pagePrefix="Page"
              containerClassName="flex items-center gap-1.5"
              pageClassName="text-[10px] text-slate-500"
              buttonClassName="btn-secondary py-1 px-2 text-[10px]"
            />
          </div>
        </SectionCard>
      )}

      {recentEntries.length > 0 && (
        <SectionBand
          title="Operational Ledger"
          subtitle="Detailed call-level entries with consistent table pagination controls."
        />
      )}

      {recentEntries.length > 0 && (
        <SectionCard cardClassName="card p-5">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">Recent LLM Calls</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-200">
                  <th className="text-left py-2">Logged At</th>
                  <th className="text-left py-2">Model</th>
                  <th className="text-right py-2">Prompt</th>
                  <th className="text-right py-2">Completion</th>
                  <th className="text-right py-2">Total</th>
                  <th className="text-right py-2">Cost</th>
                  <th className="text-right py-2">Latency</th>
                  <th className="text-right py-2">SDK</th>
                </tr>
              </thead>
              <tbody>
                {pagedRecentEntries.map((entry) => (
                  <tr key={entry.id ?? `${entry.logged_at}-${entry.model}`} className="border-b border-slate-100 text-slate-700">
                    <td className="py-2">{entry.logged_at?.replace('T', ' ').replace('Z', '') ?? 'N/A'}</td>
                    <td className="py-2 font-medium">{entry.model ?? 'N/A'}</td>
                    <td className="py-2 text-right">{Number(entry.prompt_tokens ?? 0).toLocaleString()}</td>
                    <td className="py-2 text-right">{Number(entry.completion_tokens ?? 0).toLocaleString()}</td>
                    <td className="py-2 text-right">{Number(entry.total_tokens ?? 0).toLocaleString()}</td>
                    <td className="py-2 text-right">${Number(entry.estimated_cost_usd ?? 0).toFixed(6)}</td>
                    <td className="py-2 text-right">{entry.latency_ms ? `${entry.latency_ms}ms` : 'N/A'}</td>
                    <td className="py-2 text-right">{entry.library_id ?? 'N/A'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-[10px] text-slate-500">
            <div className="flex items-center gap-2">
              <span>Showing {recentEntries.length ? recentStart + 1 : 0}-{recentEnd} of {recentEntries.length}</span>
              <RowsPerPageControl
                pageSize={recentPageSize}
                options={[10, 20, 30]}
                onChange={(value) => {
                  setRecentPageSize(value)
                  setRecentPage(1)
                }}
                labelClassName="text-[10px] text-slate-500"
                selectClassName="select py-1 text-[10px]"
              />
            </div>
            <PaginatedSectionFooter
              page={safeRecentPage}
              totalPages={recentTotalPages}
              onPrev={() => setRecentPage((p) => Math.max(1, p - 1))}
              onNext={() => setRecentPage((p) => Math.min(recentTotalPages, p + 1))}
              prevLabel="Prev"
              nextLabel="Next"
              pagePrefix="Page"
              containerClassName="flex items-center gap-1.5"
              pageClassName="text-[10px] text-slate-500"
              buttonClassName="btn-secondary py-1 px-2 text-[10px]"
            />
          </div>
        </SectionCard>
      )}

      {!daily.length && !byModel.length && (
        <SectionCard cardClassName="card p-8 text-center text-slate-400 text-sm">
          LLM configured but no usage data yet. Run the pipeline to generate AI recommendations.
        </SectionCard>
      )}
    </div>
  )
}
