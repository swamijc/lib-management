interface MetricCardProps {
  title: string
  value: string | number
  subtitle?: string
  icon?: React.ReactNode
  color?: 'default' | 'red' | 'amber' | 'green' | 'blue' | 'purple' | 'slate'
  trend?: { value: number; label: string }
  href?: string
}

const colorMap = {
  default: 'bg-white border-slate-200',
  red:     'bg-red-50 border-red-200',
  amber:   'bg-amber-50 border-amber-200',
  green:   'bg-emerald-50 border-emerald-200',
  blue:    'bg-blue-50 border-blue-200',
  purple:  'bg-violet-50 border-violet-200',
  slate:   'bg-slate-50 border-slate-200',
}
const iconColorMap = {
  default: 'bg-slate-100 text-slate-500',
  red:     'bg-red-100 text-red-600',
  amber:   'bg-amber-100 text-amber-600',
  green:   'bg-emerald-100 text-emerald-600',
  blue:    'bg-blue-100 text-blue-600',
  purple:  'bg-violet-100 text-violet-600',
  slate:   'bg-slate-200 text-slate-500',
}
const valueColorMap = {
  default: 'text-slate-900',
  red:     'text-red-700',
  amber:   'text-amber-700',
  green:   'text-emerald-700',
  blue:    'text-blue-700',
  purple:  'text-violet-700',
  slate:   'text-slate-700',
}

export default function MetricCard({
  title, value, subtitle, icon, color = 'default', trend, href,
}: MetricCardProps) {
  const inner = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-bold text-slate-500 uppercase tracking-widest truncate leading-tight">{title}</p>
          <p className={`mt-2 text-3xl font-extrabold tabular-nums leading-none ${valueColorMap[color]}`}>{value}</p>
          {subtitle && <p className="mt-1.5 text-[11px] text-slate-400 truncate leading-snug">{subtitle}</p>}
          {trend && (
            <p className={`mt-1.5 text-[11px] font-semibold flex items-center gap-0.5 ${trend.value >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
              <span>{trend.value >= 0 ? '↑' : '↓'}</span>
              <span>{Math.abs(trend.value)}%</span>
              <span className="font-normal text-slate-400">{trend.label}</span>
            </p>
          )}
        </div>
        {icon && (
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${iconColorMap[color]}`}>
            {icon}
          </div>
        )}
      </div>
      {href && (
        <p className="mt-2 text-[11px] text-slate-400 group-hover:text-primary-600 transition-colors">
          View all →
        </p>
      )}
    </>
  )

  if (href) {
    return (
      <a href={href} className={`card p-5 group cursor-pointer hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 ${colorMap[color]}`}>
        {inner}
      </a>
    )
  }
  return <div className={`card p-5 ${colorMap[color]}`}>{inner}</div>
}
