type SectionBandProps = {
  title: string
  subtitle: string
  className?: string
}

export default function SectionBand({
  title,
  subtitle,
  className = '',
}: SectionBandProps) {
  return (
    <div className={`rounded-md border border-slate-200 bg-slate-50 px-3 py-2 ${className}`.trim()}>
      <p className="text-[11px] font-medium text-slate-700">{title}</p>
      <p className="text-[10px] text-slate-500">{subtitle}</p>
    </div>
  )
}
