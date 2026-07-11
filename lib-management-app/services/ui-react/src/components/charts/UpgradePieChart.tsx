import { useEffect } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

interface Props {
  critical: number
  high: number
  moderate: number
  upToDate: number
  onInsightComputed?: (insight: string) => void
}

const SLICES = [
  { key: 'critical', label: 'Critical',   color: 'var(--chart-priority-critical)', emoji: '🔴' },
  { key: 'high',     label: 'High',        color: 'var(--chart-priority-high)', emoji: '🟠' },
  { key: 'moderate', label: 'Moderate',    color: 'var(--chart-priority-moderate)', emoji: '🟡' },
  { key: 'upToDate', label: 'Up to Date',  color: 'var(--chart-priority-up-to-date)', emoji: '✅' },
]

export default function UpgradePieChart({ critical, high, moderate, upToDate, onInsightComputed }: Props) {
  const raw: Record<string, number> = { critical, high, moderate, upToDate }
  const total = critical + high + moderate + upToDate

  const data = SLICES
    .map((s) => ({ ...s, value: raw[s.key] ?? 0 }))
    .filter((d) => d.value > 0)

  const riskBacklog = critical + high
  const riskPct = total > 0 ? Math.round((riskBacklog / total) * 100) : 0
  const topSlice = data.slice().sort((a, b) => b.value - a.value)[0]
  const topPct = total > 0 && topSlice ? Math.round((topSlice.value / total) * 100) : 0

  const computedInsight = total === 0
    ? 'Insight: No tracked SDKs yet; run portfolio ingestion to establish risk posture.'
    : topSlice?.key === 'upToDate'
      ? `Insight: ${topPct}% of SDKs are up to date, indicating stable portfolio hygiene.`
      : `Insight: ${riskPct}% of SDKs are in critical/high bands; dominant segment is ${topSlice?.label ?? 'risk backlog'} (${topPct}%).`

  useEffect(() => {
    onInsightComputed?.(computedInsight)
  }, [computedInsight, onInsightComputed])

  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-52 text-slate-400 text-sm">
        No data yet
      </div>
    )
  }

  return (
    <div className="flex flex-col sm:flex-row items-center gap-6 py-2">
      {/* Donut chart — fixed 200×200 so it never collapses */}
      <div className="flex-shrink-0 w-[200px] h-[200px]">
        <ResponsiveContainer width={200} height={200}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={90}
              paddingAngle={3}
              dataKey="value"
              startAngle={90}
              endAngle={-270}
              strokeWidth={0}
            >
              {data.map((d, i) => (
                <Cell key={i} fill={d.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number, name: string) => [
                `${value} (${((value / total) * 100).toFixed(1)}%)`,
                name,
              ]}
              contentStyle={{
                background: 'var(--chart-tooltip-bg)',
                border: '1px solid var(--chart-tooltip-border)',
                borderRadius: 8,
                fontSize: 12,
                boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Custom legend — sits to the right on desktop, below on mobile */}
      <div className="flex flex-col gap-3 flex-1 min-w-0 w-full sm:w-auto">
        {data.map((d) => {
          const pct = ((d.value / total) * 100).toFixed(1)
          const barW = Math.round((d.value / total) * 100)
          return (
            <div key={d.key}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-700 flex items-center gap-1.5">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ background: d.color }}
                  />
                  {d.emoji} {d.label}
                </span>
                <span className="text-xs font-bold text-slate-800 tabular-nums">
                  {d.value}
                  <span className="text-slate-400 font-normal ml-1">({pct}%)</span>
                </span>
              </div>
              {/* Mini progress bar */}
              <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${barW}%`, background: d.color }}
                />
              </div>
            </div>
          )
        })}
        <div className="mt-1 pt-2 border-t border-slate-100 flex items-center justify-between">
          <span className="text-[11px] text-slate-400">Total tracked</span>
          <span className="text-xs font-bold text-slate-700">{total}</span>
        </div>
      </div>
    </div>
  )
}
