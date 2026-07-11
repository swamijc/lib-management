import { useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

interface PlatformEntry {
  platform: string
  critical: number
  high: number
  moderate: number
  upToDate: number
}

interface Props {
  data: PlatformEntry[]
  onInsightComputed?: (insight: string) => void
}

const BARS = [
  { key: 'critical', label: '🔴 Critical',   color: 'var(--chart-priority-critical)' },
  { key: 'high',     label: '🟠 High',        color: 'var(--chart-priority-high)' },
  { key: 'moderate', label: '🟡 Moderate',    color: 'var(--chart-priority-moderate)' },
  { key: 'upToDate', label: '✅ Up to Date',  color: 'var(--chart-priority-up-to-date)' },
]

export default function PlatformBarChart({ data, onInsightComputed }: Props) {
  const computedInsight = (() => {
    if (!data.length) return 'Insight: No platform distribution available yet.'

    const ranked = data
      .map((row) => {
        const total = row.critical + row.high + row.moderate + row.upToDate
        const risk = row.critical + row.high
        const riskPct = total > 0 ? Math.round((risk / total) * 100) : 0
        return { platform: row.platform, riskPct }
      })
      .sort((a, b) => b.riskPct - a.riskPct)

    const top = ranked[0]
    const next = ranked[1]
    const delta = next ? top.riskPct - next.riskPct : 0

    return next
      ? `Insight: ${top.platform} shows the highest critical/high pressure at ${top.riskPct}%, ${delta}% above ${next.platform}.`
      : `Insight: ${top.platform} shows ${top.riskPct}% critical/high pressure in the current portfolio.`
  })()

  useEffect(() => {
    onInsightComputed?.(computedInsight)
  }, [computedInsight, onInsightComputed])

  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={220}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -8, bottom: 4 }} barSize={32}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          dataKey="platform"
          tick={{ fontSize: 12, fill: 'var(--chart-axis)', fontWeight: 600 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: 'var(--chart-axis-muted)' }}
          axisLine={false}
          tickLine={false}
          width={28}
        />
        <Tooltip
          cursor={{ fill: 'var(--chart-tooltip-cursor)' }}
          contentStyle={{ background: 'var(--chart-tooltip-bg)', border: '1px solid var(--chart-tooltip-border)', borderRadius: 8, fontSize: 12 }}
          formatter={(value: number, name: string) => [value, name]}
        />
        <Legend
          iconSize={8}
          wrapperStyle={{ paddingTop: 8, fontSize: 11 }}
          formatter={(v) => <span style={{ color: 'var(--chart-legend)', fontSize: 11 }}>{v}</span>}
        />
        {BARS.map(({ key, label, color }) => (
          <Bar key={key} dataKey={key} name={label} fill={color}
            radius={[3, 3, 0, 0]} stackId="a" />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
