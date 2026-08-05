import { useEffect, useMemo, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Library, GitBranch, UserCheck, Clock, BarChart3, Settings,
  LogOut, Shield, Users, ClipboardList, BellRing, Newspaper, Building2, Activity, GanttChartSquare, Briefcase,
  type LucideIcon,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

type NavItem = {
  to: string
  icon: LucideIcon
  label: string
  adminOnly: boolean
}

type NavSection = {
  title: string
  icon: LucideIcon
  items: NavItem[]
}

type NavProfile = 'cio' | 'ops' | 'governance'

const NAV_PROFILE_STORAGE_PREFIX = 'sidebar_nav_profile'
const SIDEBAR_WIDTH_BY_PROFILE: Record<NavProfile, string> = {
  cio: '248px',
  ops: '256px',
  governance: '284px',
}

function getResponsiveSidebarWidth(profile: NavProfile, viewportWidth: number): string {
  const baseWidth = Number.parseInt(SIDEBAR_WIDTH_BY_PROFILE[profile], 10) || 248

  if (viewportWidth <= 1280) return `${Math.max(232, baseWidth - 28)}px`
  if (viewportWidth <= 1440) return `${Math.max(240, baseWidth - 14)}px`
  return `${baseWidth}px`
}

function storageKey(username?: string) {
  return `${NAV_PROFILE_STORAGE_PREFIX}:${username || 'guest'}`
}

function getSectionsByProfile(profile: NavProfile): NavSection[] {
  if (profile === 'governance') {
    return [
      {
        title: 'Governance Priority',
        icon: GanttChartSquare,
        items: [
          { to: '/libraries', icon: Library, label: 'SDK Portfolio', adminOnly: false },
          { to: '/audit', icon: ClipboardList, label: 'Application Audit', adminOnly: false },
          { to: '/governance', icon: GitBranch, label: 'Upgrade Governance', adminOnly: false },
        ],
      },
      {
        title: 'Execution Assurance',
        icon: Activity,
        items: [
          { to: '/scheduler', icon: Clock, label: 'Pipeline Operations', adminOnly: false },
          { to: '/notification-reliability', icon: BellRing, label: 'Notification Reliability', adminOnly: false },
        ],
      },
      {
        title: 'Leadership Visibility',
        icon: Briefcase,
        items: [
          { to: '/dashboard', icon: LayoutDashboard, label: 'Executive Overview', adminOnly: false },
          { to: '/weekly-digest', icon: Newspaper, label: 'Executive Weekly Digest', adminOnly: false },
          { to: '/analytics', icon: BarChart3, label: 'AI Cost & Performance', adminOnly: false },
        ],
      },
      {
        title: 'Platform Administration',
        icon: Settings,
        items: [
          { to: '/users', icon: Users, label: 'Access Management', adminOnly: true },
          { to: '/settings', icon: Settings, label: 'Platform Settings', adminOnly: true },
        ],
      },
    ]
  }

  if (profile === 'ops') {
    return [
      {
        title: 'Run Control',
        icon: Activity,
        items: [
          { to: '/scheduler', icon: Clock, label: 'Pipeline Control Room', adminOnly: false },
          { to: '/notification-reliability', icon: BellRing, label: 'Notification Reliability', adminOnly: false },
          { to: '/audit', icon: ClipboardList, label: 'Audit & Evidence Trail', adminOnly: false },
        ],
      },
      {
        title: 'Upgrade Flow',
        icon: GanttChartSquare,
        items: [
          { to: '/libraries', icon: Library, label: 'SDK Portfolio Backlog', adminOnly: false },
          { to: '/governance', icon: GitBranch, label: 'Upgrade Governance', adminOnly: false },
        ],
      },
      {
        title: 'Leadership Reporting',
        icon: Briefcase,
        items: [
          { to: '/dashboard', icon: LayoutDashboard, label: 'Executive Overview', adminOnly: false },
          { to: '/weekly-digest', icon: Newspaper, label: 'Weekly Leadership Digest', adminOnly: false },
          { to: '/analytics', icon: BarChart3, label: 'AI Cost & Performance', adminOnly: false },
        ],
      },
      {
        title: 'Platform Administration',
        icon: Settings,
        items: [
          { to: '/users', icon: Users, label: 'Access Management', adminOnly: true },
          { to: '/settings', icon: Settings, label: 'Platform Settings', adminOnly: true },
        ],
      },
    ]
  }

  return [
    {
      title: 'Executive Direction',
      icon: Building2,
      items: [
        { to: '/dashboard', icon: LayoutDashboard, label: 'Executive Overview', adminOnly: false },
        { to: '/weekly-digest', icon: Newspaper, label: 'Executive Weekly Digest', adminOnly: false },
        { to: '/analytics', icon: BarChart3, label: 'AI Cost & Performance', adminOnly: false },
      ],
    },
    {
      title: 'Portfolio Governance',
      icon: GanttChartSquare,
      items: [
        { to: '/libraries', icon: Library, label: 'SDK Portfolio', adminOnly: false },
        { to: '/governance', icon: GitBranch, label: 'Upgrade Governance', adminOnly: false },
      ],
    },
    {
      title: 'Operational Assurance',
      icon: Activity,
      items: [
        { to: '/scheduler', icon: Clock, label: 'Pipeline Operations', adminOnly: false },
        { to: '/notification-reliability', icon: BellRing, label: 'Notification Reliability', adminOnly: false },
        { to: '/audit', icon: ClipboardList, label: 'Application Audit', adminOnly: false },
      ],
    },
    {
      title: 'Platform Administration',
      icon: Settings,
      items: [
        { to: '/users', icon: Users, label: 'Access Management', adminOnly: true },
        { to: '/settings', icon: Settings, label: 'Platform Settings', adminOnly: true },
      ],
    },
  ]
}

export default function Sidebar() {
  const { user, isAdmin, logout } = useAuth()
  const location = useLocation()
  const [navProfile, setNavProfile] = useState<NavProfile>(() => {
    const stored = localStorage.getItem(storageKey())
    if (stored === 'ops' || stored === 'governance') return stored
    return 'cio'
  })

  useEffect(() => {
    const stored = localStorage.getItem(storageKey(user?.username))
    if (stored === 'ops' || stored === 'cio' || stored === 'governance') {
      setNavProfile(stored)
    } else {
      setNavProfile('cio')
    }
  }, [user?.username])

  useEffect(() => {
    const applySidebarWidth = () => {
      const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1440
      const width = getResponsiveSidebarWidth(navProfile, viewportWidth)
      document.documentElement.style.setProperty('--sidebar-width', width)
    }

    applySidebarWidth()
    window.addEventListener('resize', applySidebarWidth)
    return () => window.removeEventListener('resize', applySidebarWidth)
  }, [navProfile])

  const sections = useMemo(() => getSectionsByProfile(navProfile), [navProfile])

  const visibleSections = sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => !item.adminOnly || isAdmin),
    }))
    .filter((section) => section.items.length > 0)

  const setProfile = (profile: NavProfile) => {
    setNavProfile(profile)
    localStorage.setItem(storageKey(user?.username), profile)
  }

  return (
    <aside
      className="fixed top-0 left-0 h-full flex flex-col sidebar-shell"
      style={{ width: 'var(--sidebar-width)', background: 'var(--photon-navy)', zIndex: 40 }}
    >
      <div className="sidebar-brand">
        <div className="min-w-0 sidebar-brand-text-wrap">
          <p className="sidebar-brand-title">SDK Governance Hub</p>
          <p className="sidebar-brand-subtitle" style={{ color: 'var(--photon-orange)' }}>Enterprise Upgrade Platform</p>
        </div>
      </div>

      <div className="sidebar-profile-switch-wrap">
        <p className="sidebar-section-label px-1.5">Business Navigation</p>
        <div className="sidebar-profile-grid">
          <button
            className={`sidebar-profile-btn ${navProfile === 'cio' ? 'sidebar-profile-btn-active' : ''}`}
            onClick={() => setProfile('cio')}
          >
            CIO
          </button>
          <button
            className={`sidebar-profile-btn ${navProfile === 'ops' ? 'sidebar-profile-btn-active' : ''}`}
            onClick={() => setProfile('ops')}
          >
            Ops
          </button>
          <button
            className={`sidebar-profile-btn ${navProfile === 'governance' ? 'sidebar-profile-btn-active' : ''}`}
            onClick={() => setProfile('governance')}
          >
            Gov
          </button>
        </div>
      </div>

      {/* Nav */}
      <nav className="sidebar-nav">
        {visibleSections.map((section, index) => (
          <div key={section.title} className="sidebar-section-block">
            {index > 0 && <div className="sidebar-section-separator" />}
            <p className="sidebar-section-label">
              <section.icon size={12} />
              {section.title}
            </p>
            <div className="space-y-1">
              {section.items.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `sidebar-link${isActive || location.pathname === to ? ' active' : ''}`
                  }
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-user-block">
          <div className="sidebar-user-avatar"
            style={{ background: isAdmin ? 'var(--photon-orange)' : '#334155' }}>
            <Shield size={12} className="text-white" />
          </div>
          <div className="min-w-0">
            <p className="sidebar-user-name">{user?.username}</p>
            <p className="sidebar-user-role"
              style={{ color: isAdmin ? 'var(--photon-orange)' : '#94A3B8' }}>
              {isAdmin ? '🛡 Admin' : '👁 Viewer'}
            </p>
          </div>
        </div>
        <button onClick={logout} className="sidebar-link w-full text-left">
          <LogOut size={14} />
          <span className="text-xs">Sign out</span>
        </button>
      </div>
    </aside>
  )
}
