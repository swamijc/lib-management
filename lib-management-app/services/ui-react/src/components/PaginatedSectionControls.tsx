type RowsPerPageControlProps = {
  pageSize: number
  options: number[]
  onChange: (value: number) => void
  label?: string
  className?: string
  labelClassName?: string
  selectClassName?: string
}

export function RowsPerPageControl({
  pageSize,
  options,
  onChange,
  label = 'Rows',
  className = 'flex items-center gap-1.5',
  labelClassName = 'text-xs text-slate-500',
  selectClassName = 'select py-1 text-xs w-auto',
}: RowsPerPageControlProps) {
  return (
    <div className={className}>
      <span className={labelClassName}>{label}</span>
      <select
        className={selectClassName}
        value={pageSize}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {options.map((size) => (
          <option key={size} value={size}>{size}</option>
        ))}
      </select>
    </div>
  )
}

type PaginatedSectionHeaderProps = {
  title: string
  totalItems: number
  startIndex: number
  endIndex: number
  pageSize: number
  pageSizeOptions: number[]
  onPageSizeChange: (value: number) => void
  recordLabel?: string
  containerClassName?: string
  titleClassName?: string
  metaClassName?: string
  rowsLabelClassName?: string
  rowsSelectClassName?: string
}

export function PaginatedSectionHeader({
  title,
  totalItems,
  startIndex,
  endIndex,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  recordLabel = 'records',
  containerClassName = 'px-5 py-3 border-b border-slate-100 flex items-center justify-between',
  titleClassName = 'text-sm font-semibold text-slate-700',
  metaClassName = 'text-xs text-slate-400',
  rowsLabelClassName = 'text-xs text-slate-500',
  rowsSelectClassName = 'select py-1 text-xs w-auto',
}: PaginatedSectionHeaderProps) {
  return (
    <div className={containerClassName}>
      <h3 className={titleClassName}>{title}</h3>
      <div className="flex items-center gap-3">
        <span className={metaClassName}>
          {totalItems} {recordLabel} · showing {totalItems ? startIndex + 1 : 0}-{endIndex}
        </span>
        <RowsPerPageControl
          pageSize={pageSize}
          options={pageSizeOptions}
          onChange={onPageSizeChange}
          labelClassName={rowsLabelClassName}
          selectClassName={rowsSelectClassName}
        />
      </div>
    </div>
  )
}

type PaginatedSectionFooterProps = {
  page: number
  totalPages: number
  onPrev: () => void
  onNext: () => void
  prevLabel?: string
  nextLabel?: string
  containerClassName?: string
  pageClassName?: string
  buttonClassName?: string
  pagePrefix?: string
}

export function PaginatedSectionFooter({
  page,
  totalPages,
  onPrev,
  onNext,
  prevLabel = 'Previous',
  nextLabel = 'Next',
  containerClassName = 'px-5 py-3 border-t border-slate-100 flex items-center justify-between',
  pageClassName = 'text-xs text-slate-500',
  buttonClassName = 'btn-secondary py-1 px-2 text-xs',
  pagePrefix = 'Page',
}: PaginatedSectionFooterProps) {
  return (
    <div className={containerClassName}>
      <span className={pageClassName}>{pagePrefix} {page} of {totalPages}</span>
      <div className="flex items-center gap-2">
        <button className={buttonClassName} onClick={onPrev} disabled={page <= 1}>{prevLabel}</button>
        <button className={buttonClassName} onClick={onNext} disabled={page >= totalPages}>{nextLabel}</button>
      </div>
    </div>
  )
}
