interface StatusBadgeProps { status: string; size?: 'sm' | 'md' }

// Enterprise semantic badge tokens — consistent across all themes
const BASE = 'inline-flex items-center gap-1 font-semibold rounded-full border leading-none'
const SM   = 'px-1.5 py-0.5 text-[10px]'
const MD   = 'px-2.5 py-1 text-[11px]'

const statusMap: Record<string, { cls: string; dot?: string }> = {
  // ── 4-tier priority ─────────────────────────────────────────────────────
  critical:        { cls: 'bg-red-600 text-white border-red-700',                    dot: 'bg-red-200' },
  high:            { cls: 'bg-orange-500 text-white border-orange-600',              dot: 'bg-orange-200' },
  moderate:        { cls: 'bg-amber-100 text-amber-800 border-amber-300' },
  low:             { cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  // ── legacy priority ──────────────────────────────────────────────────────
  mandatory:       { cls: 'bg-red-100 text-red-800 border-red-200' },
  recommended:     { cls: 'bg-amber-100 text-amber-800 border-amber-200' },
  optional:        { cls: 'bg-sky-100 text-sky-700 border-sky-200' },
  none:            { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  sufficient:      { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  // ── library operational status ───────────────────────────────────────────
  active:          { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  inactive:        { cls: 'bg-slate-100 text-slate-600 border-slate-200' },
  deprecated:      { cls: 'bg-rose-100 text-rose-700 border-rose-200' },
  legacy:          { cls: 'bg-slate-200 text-slate-600 border-slate-300' },
  maintenance:     { cls: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  unknown:         { cls: 'bg-slate-100 text-slate-500 border-slate-200' },
  // ── lifecycle states ─────────────────────────────────────────────────────
  'up-to-date':    { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  pending:         { cls: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  awaiting_review: { cls: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  acknowledged:    { cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  scheduled:       { cls: 'bg-violet-100 text-violet-700 border-violet-200' },
  'in progress':   { cls: 'bg-orange-100 text-orange-700 border-orange-200' },
  completed:       { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  skipped:         { cls: 'bg-slate-100 text-slate-500 border-slate-200' },
  rejected:        { cls: 'bg-red-100 text-red-700 border-red-200' },
  approved:        { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  overdue:         { cls: 'bg-red-100 text-red-700 border-red-200' },
  normal:          { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  // ── platform ─────────────────────────────────────────────────────────────
  android:         { cls: 'bg-green-100 text-green-800 border-green-200' },
  ios:             { cls: 'bg-slate-100 text-slate-800 border-slate-300' },
  cross_platform:  { cls: 'bg-purple-100 text-purple-700 border-purple-200' },
  // ── pipeline ─────────────────────────────────────────────────────────────
  running:         { cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  success:         { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  failed:          { cls: 'bg-red-100 text-red-700 border-red-200' },
  warning:         { cls: 'bg-amber-100 text-amber-700 border-amber-200' },
  medium:          { cls: 'bg-amber-100 text-amber-700 border-amber-200' },
}

const labels: Record<string, string> = {
  awaiting_review:  'Awaiting Review',
  'up-to-date':     'Up to Date',
  cross_platform:   'Cross Platform',
  running:          'Running',
  none:             'Up to Date',
  sufficient:       'Up to Date',
  'in progress':    'In Progress',
  critical:         'Critical',
  high:             'High',
  moderate:         'Moderate',
  low:              'Low',
  mandatory:        'Mandatory',
  recommended:      'Recommended',
  optional:         'Optional',
}

// Priority dot indicator for high-signal badges
const dotMap: Record<string, string> = {
  critical: '🔴',
  high:     '🟠',
  moderate: '🟡',
  low:      '🔵',
  none:     '🟢',
  active:   '🟢',
  inactive: '⚪',
}

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const key = (status ?? 'unknown').toLowerCase().replace(/ /g, ' ')
  const entry = statusMap[key] ?? { cls: 'bg-slate-100 text-slate-500 border-slate-200' }
  const label = labels[key] ?? status
  const sizeClass = size === 'sm' ? SM : MD
  const dot = dotMap[key]
  return (
    <span className={`${BASE} ${sizeClass} ${entry.cls}`}>
      {dot && size === 'md' && <span className="text-[9px] leading-none">{dot}</span>}
      {String(label ?? key).replace(/_/g, ' ')}
    </span>
  )
}
