import type { ReactNode } from 'react'

type ChartSectionProps = {
  title: string
  insight: string
  rightSlot?: ReactNode
  children: ReactNode
  className?: string
}

export default function ChartSection({ title, insight, rightSlot, children, className }: ChartSectionProps) {
  return (
    <div className={`chart-shell ${className ?? ''}`.trim()}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="chart-title">{title}</h3>
        {rightSlot ? <div className="text-xs text-slate-400">{rightSlot}</div> : null}
      </div>
      {children}
      <p className="chart-insight">{insight}</p>
    </div>
  )
}
