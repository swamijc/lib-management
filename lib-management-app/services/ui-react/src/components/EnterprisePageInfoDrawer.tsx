import { X } from 'lucide-react'

export type EnterprisePageInfo = {
  pageLabel: string
  visualDirection: string
  businessExperience: string
  enterpriseExperience: string
  chartGuidance: string
  seeMorePattern: string
}

type EnterprisePageInfoDrawerProps = {
  open: boolean
  onClose: () => void
  info: EnterprisePageInfo
}

export default function EnterprisePageInfoDrawer({ open, onClose, info }: EnterprisePageInfoDrawerProps) {
  if (!open) return null

  return (
    <>
      <div className="info-drawer-overlay" onClick={onClose} />
      <aside className="info-drawer-panel flex flex-col">
        <div className="border-b border-slate-200 px-5 py-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold text-primary-700 uppercase tracking-wider">UI Modernization Guide</p>
            <h2 className="text-lg font-bold text-slate-900 mt-1">{info.pageLabel}</h2>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="modernization-chip business">Business Level</span>
              <span className="modernization-chip enterprise">Enterprise Level</span>
              <span className="modernization-chip ux">See More UX</span>
            </div>
          </div>
          <button className="btn-secondary py-1.5 px-2" onClick={onClose}>
            <X size={14} />
            Close
          </button>
        </div>

        <div className="overflow-auto p-5 space-y-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs font-semibold text-slate-700">Visual Direction</p>
            <p className="text-sm text-slate-600 mt-1">{info.visualDirection}</p>
          </div>

          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
            <p className="text-xs font-semibold text-amber-700">Business Experience</p>
            <p className="text-sm text-amber-800 mt-1">{info.businessExperience}</p>
          </div>

          <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3">
            <p className="text-xs font-semibold text-blue-700">Enterprise Experience</p>
            <p className="text-sm text-blue-800 mt-1">{info.enterpriseExperience}</p>
          </div>

          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
            <p className="text-xs font-semibold text-emerald-700">Chart Guidance</p>
            <p className="text-sm text-emerald-800 mt-1">{info.chartGuidance}</p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <p className="text-xs font-semibold text-slate-700">See More Pattern</p>
            <p className="text-sm text-slate-600 mt-1">{info.seeMorePattern}</p>
          </div>
        </div>
      </aside>
    </>
  )
}
