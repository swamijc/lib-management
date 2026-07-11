import { Outlet } from 'react-router-dom'
import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Building2, CalendarDays, Info, ShieldCheck } from 'lucide-react'
import Sidebar from './Sidebar'
import EnterprisePageInfoDrawer, { type EnterprisePageInfo } from './EnterprisePageInfoDrawer'
import GlobalAsyncLoader from './GlobalAsyncLoader'
import { useTheme } from '../context/ThemeContext'

const PAGE_LABELS: Record<string, string> = {
  '/dashboard': 'Executive Overview',
  '/libraries': 'SDK Portfolio',
  '/governance': 'Upgrade Governance',
  '/hitl-review': 'Approval Queue',
  '/scheduler': 'Pipeline Operations',
  '/notification-reliability': 'Notification Reliability Center',
  '/weekly-digest': 'Executive Weekly Digest',
  '/audit': 'Application Audit',
  '/analytics': 'AI Cost & Performance',
  '/users': 'Access Management',
  '/settings': 'Platform Settings',
}

const PAGE_GUIDANCE: Record<string, EnterprisePageInfo> = {
  '/dashboard': {
    pageLabel: 'Executive Overview',
    visualDirection: 'Use high-contrast KPI hierarchy with quick risk posture and weekly directional trends.',
    businessExperience: 'Decision makers should instantly see top risks, portfolio health, and action owners.',
    enterpriseExperience: 'Include exportable snapshot context and confidence tags on key indicators.',
    chartGuidance: 'Pair each chart with a one-line insight and target line for executive interpretation.',
    seeMorePattern: 'Open drill-down drawers by KPI for root-cause evidence and impacted teams.',
  },
  '/libraries': {
    pageLabel: 'SDK Portfolio',
    visualDirection: 'Emphasize risk status, upgrade urgency, and ownership in dense but scannable rows.',
    businessExperience: 'Help product teams prioritize upgrades by impact and release windows.',
    enterpriseExperience: 'Show governance metadata, deadlines, and policy-grade evidence per SDK.',
    chartGuidance: 'Use distribution charts for platform split, priority mix, and stale-version exposure.',
    seeMorePattern: 'Provide side panel profile for full SDK lineage, notes, and audit context.',
  },
  '/governance': {
    pageLabel: 'Upgrade Governance',
    visualDirection: 'Keep risk and SLA watchlists prominent with status colors and owner accountability.',
    businessExperience: 'Drive faster decisions with portfolio queue clarity and overdue visibility.',
    enterpriseExperience: 'Capture rationale quality, owner compliance, and escalations in a review-ready UI.',
    chartGuidance: 'Use funnel and aging trend visuals for decision throughput and governance debt.',
    seeMorePattern: 'Expose decision trail details via expandable timeline and evidence panel.',
  },
  '/hitl-review': {
    pageLabel: 'Approval Queue',
    visualDirection: 'Design for reviewer throughput with concise cards and strong priority cues.',
    businessExperience: 'Surface why each approval matters and what changes for deployment readiness.',
    enterpriseExperience: 'Track reviewer action quality, queue aging, and high-impact exceptions.',
    chartGuidance: 'Show queue composition and reviewer throughput trends by priority band.',
    seeMorePattern: 'Use one-click detailed analysis tabs for AI rationale and release-note proof.',
  },
  '/scheduler': {
    pageLabel: 'Pipeline Operations',
    visualDirection: 'Workflow canvas should feel orchestration-grade with clear stage progression.',
    businessExperience: 'Teams should quickly detect bottlenecks and SLA pressure during runs.',
    enterpriseExperience: 'Expose retry outcomes, stage evidence, and history jumps for operations governance.',
    chartGuidance: 'Track run quality, failure points, and stage SLA breach trends over time.',
    seeMorePattern: 'Node inspector should provide logs, timings, SLA verdict, and actionable controls.',
  },
  '/notification-reliability': {
    pageLabel: 'Notification Reliability Center',
    visualDirection: 'Keep channel reliability and failure evidence concise and operationally actionable.',
    businessExperience: 'Business owners should quickly identify channel risk and delivery trust gaps.',
    enterpriseExperience: 'Surface retries, failure taxonomy, and channel-specific trends with audit-friendly clarity.',
    chartGuidance: 'Use compact channel trend visuals and clear sent/failed/retry counters.',
    seeMorePattern: 'Link directly to notification configuration controls for immediate remediation.',
  },
  '/weekly-digest': {
    pageLabel: 'Executive Weekly Digest',
    visualDirection: 'Present a print-friendly leadership summary with high-signal metrics only.',
    businessExperience: 'Enable fast weekly review without deep navigation across operational pages.',
    enterpriseExperience: 'Ensure exported digest contains governance, reliability, and SLA posture data.',
    chartGuidance: 'Prefer compact summary cards and avoid dense exploratory visuals.',
    seeMorePattern: 'Offer JSON/CSV export and print actions for leadership distribution workflows.',
  },
  '/audit': {
    pageLabel: 'Application Audit',
    visualDirection: 'Prioritize chronology, actor clarity, and event severity with clear table rhythm.',
    businessExperience: 'Enable fast investigation of changes impacting delivery and compliance.',
    enterpriseExperience: 'Maintain complete traceability with before/after context and reason quality.',
    chartGuidance: 'Use event-volume and actor heatmaps for operational compliance posture.',
    seeMorePattern: 'Add event context drawer to reveal raw evidence and related workflow run IDs.',
  },
  '/analytics': {
    pageLabel: 'AI Cost & Performance',
    visualDirection: 'Balance cost and latency metrics with clear model efficiency storytelling.',
    businessExperience: 'Make optimization opportunities obvious through cost-to-value framing.',
    enterpriseExperience: 'Support FinOps decisions with governance-ready spend and risk indicators.',
    chartGuidance: 'Standardize trend, breakdown, and forecast charts with threshold overlays.',
    seeMorePattern: 'Allow model-level deep dives with token, latency, and usage evidence.',
  },
  '/users': {
    pageLabel: 'Access Management',
    visualDirection: 'Highlight role posture and stale account risks with strong status clarity.',
    businessExperience: 'Reduce governance friction through clear owner and role grouping.',
    enterpriseExperience: 'Strengthen auditability of access changes and admin concentration.',
    chartGuidance: 'Use role mix and login recency charts to expose access hygiene trends.',
    seeMorePattern: 'User profile detail panel should include access history and governance impact.',
  },
  '/settings': {
    pageLabel: 'Platform Settings',
    visualDirection: 'Organize by governance categories with low-scroll controls and rich context.',
    businessExperience: 'Changes should clearly communicate operational impact before save.',
    enterpriseExperience: 'Show policy readiness, drift signals, and runtime health confidence.',
    chartGuidance: 'Correlate runtime and request trend charts with threshold alert explanations.',
    seeMorePattern: 'Use info drawer and category guides to explain risk and action consequences.',
  },
}

export default function Layout() {
  const location = useLocation()
  const [infoOpen, setInfoOpen] = useState(false)
  const { theme, themes, setTheme } = useTheme()
  const currentPage = PAGE_LABELS[location.pathname] ?? 'Enterprise Workspace'
  const currentGuidance = PAGE_GUIDANCE[location.pathname] ?? {
    pageLabel: currentPage,
    visualDirection: 'Use clear KPI hierarchy and concise status signals.',
    businessExperience: 'Ensure each section explains impact and next action.',
    enterpriseExperience: 'Preserve traceability, ownership, and confidence indicators.',
    chartGuidance: 'Attach insight sentences to charts and include threshold references.',
    seeMorePattern: 'Use detail drawers for evidence instead of long scroll expansions.',
  }
  const todayLabel = new Date().toLocaleDateString([], { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main
        className="flex-1 overflow-auto min-w-0"
        style={{ marginLeft: 'var(--sidebar-width)' }}
      >
        <GlobalAsyncLoader />
        <div className="p-6 page-enter">
          <div className="enterprise-context-strip">
            <div className="enterprise-context-left">
              <span className="context-chip">
                <Building2 size={13} />
                Enterprise Control
              </span>
              <span className="context-page-name">{currentPage}</span>
            </div>
            <div className="enterprise-context-right">
              <span className="context-chip context-chip-subtle">
                <CalendarDays size={12} />
                {todayLabel}
              </span>
              <span className="context-chip context-chip-subtle">
                <ShieldCheck size={12} />
                Business Governance Mode
              </span>
              <div className="flex items-center gap-1.5">
                <label className="text-[11px] text-slate-500 font-semibold">Theme</label>
                <select
                  className="select py-1 px-2 text-[11px] min-w-[150px]"
                  value={theme}
                  onChange={(e) => setTheme(e.target.value as typeof theme)}
                  title={themes.find((t) => t.id === theme)?.description}
                >
                  {themes.map((t) => (
                    <option key={t.id} value={t.id}>{t.label}</option>
                  ))}
                </select>
              </div>
              <button className="btn-secondary py-1.5 text-xs" onClick={() => setInfoOpen(true)}>
                <Info size={12} />
                See More Info
              </button>
            </div>
          </div>

          <div className="page-shell">
            <Outlet />
          </div>
        </div>
      </main>

      <EnterprisePageInfoDrawer
        open={infoOpen}
        onClose={() => setInfoOpen(false)}
        info={currentGuidance}
      />
    </div>
  )
}
