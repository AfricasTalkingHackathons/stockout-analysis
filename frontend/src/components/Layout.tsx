import clsx from 'clsx'
import {
  Activity,
  Bell,
  Boxes,
  Building2,
  ClipboardCheck,
  FileClock,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Pill as PillIcon,
  Radar,
  Settings,
  X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Spinner } from './ui'

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill={light ? '#ffffff' : '#0b5d57'} />
        <path d="M10 9h12a2 2 0 0 1 2 2v3H8v-3a2 2 0 0 1 2-2Z" fill={light ? '#78cfbe' : '#9ee6d9'} />
        <rect x="8" y="14" width="16" height="10" rx="2" fill={light ? '#0b5d57' : '#fff'} />
        <path d="M16 16.5v5M13.5 19h5" stroke={light ? '#fff' : '#0b5d57'} strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span className={clsx('text-lg font-semibold tracking-tight', light ? 'text-white' : 'text-ink')}>
        StockOut<span className={light ? 'text-brand-200' : 'text-brand-600'}> Alert</span>
      </span>
    </span>
  )
}

export function DemoBanner() {
  const { meta } = useAuth()
  if (!meta?.demo_mode) return null
  return (
    <div className="bg-violet-700 px-4 py-1.5 text-center text-xs font-medium text-white" role="note">
      Demonstration environment. Facilities marked “(Demo)” are fictional and their stock data is synthetic.
      {meta.sms_mode !== 'live-live' && ' SMS messages are simulated unless explicitly configured.'}
    </div>
  )
}

export function PublicLayout() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const links = [
    { to: '/search', label: 'Find medicine' },
    { to: '/refill', label: 'Pickup reminders' },
    { to: '/ussd', label: 'USSD / basic phones' },
    { to: '/register', label: 'Register a facility' },
  ]
  return (
    <div className="flex min-h-screen flex-col">
      <DemoBanner />
      <header className="sticky top-0 z-[500] border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4">
          <Link to="/" aria-label="StockOut Alert home">
            <Logo />
          </Link>
          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  clsx('rounded-lg px-3 py-2 text-sm font-medium', isActive ? 'bg-brand-50 text-brand-800' : 'text-slate-700 hover:bg-slate-100')
                }
              >
                {l.label}
              </NavLink>
            ))}
            <Link to={user ? '/app' : '/login'} className="ml-2 rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800">
              {user ? 'Open dashboard' : 'Sign in'}
            </Link>
          </nav>
          <button className="rounded-lg p-2 md:hidden" onClick={() => setOpen(!open)} aria-label="Toggle menu" aria-expanded={open}>
            {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
        {open && (
          <nav className="border-t border-slate-200 px-4 py-2 md:hidden" aria-label="Mobile">
            {links.map((l) => (
              <Link key={l.to} to={l.to} onClick={() => setOpen(false)} className="block rounded-lg px-3 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-100">
                {l.label}
              </Link>
            ))}
            <Link to={user ? '/app' : '/login'} onClick={() => setOpen(false)} className="block rounded-lg px-3 py-2.5 text-sm font-semibold text-brand-700">
              {user ? 'Open dashboard' : 'Sign in'}
            </Link>
          </nav>
        )}
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-sm text-slate-600 md:grid-cols-3">
          <div>
            <Logo />
            <p className="mt-3 text-xs leading-relaxed">
              Availability is self-reported by participating facilities and can change at any time. Nothing is reserved for you.
              Contact the facility before travelling.
            </p>
          </div>
          <div className="text-xs leading-relaxed">
            <p className="font-semibold text-slate-800">Health safety</p>
            <p className="mt-1">
              StockOut Alert does not diagnose, prescribe or recommend substitutes. Never change a prescribed medicine without a
              qualified health professional. In an emergency, go to the nearest health facility.
            </p>
          </div>
          <div className="text-xs">
            <p className="font-semibold text-slate-800">Your alerts</p>
            <Link to="/unsubscribe" className="mt-1 block text-brand-700 underline">
              Stop SMS alerts and pickup reminders
            </Link>
            <Link to="/refill" className="mt-1 block text-brand-700 underline">
              Ongoing treatment: find a facility and set a reminder
            </Link>
            <Link to="/report" className="mt-1 block text-brand-700 underline">
              Report unavailable medicine
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  perm?: string
  end?: boolean
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Operations',
    items: [
      { to: '/app', label: 'Dashboard', icon: <LayoutDashboard className="h-4 w-4" />, end: true },
      { to: '/app/inventory', label: 'Inventory', icon: <Boxes className="h-4 w-4" />, perm: 'inventory.view' },
      { to: '/app/movements', label: 'Stock movements', icon: <History className="h-4 w-4" />, perm: 'inventory.view' },
      { to: '/app/alerts', label: 'Stockout alerts', icon: <Bell className="h-4 w-4" />, perm: 'alerts.view' },
      { to: '/app/ripple', label: 'Ripple monitoring', icon: <Radar className="h-4 w-4" />, perm: 'alerts.view' },
      { to: '/app/reports', label: 'Public reports', icon: <ClipboardCheck className="h-4 w-4" />, perm: 'alerts.view' },
    ],
  },
  {
    section: 'Administration',
    items: [
      { to: '/app/facilities', label: 'Facilities', icon: <Building2 className="h-4 w-4" /> },
      { to: '/app/catalog', label: 'Medicine catalog', icon: <PillIcon className="h-4 w-4" />, perm: 'catalog.manage' },
      { to: '/app/notifications', label: 'Notifications', icon: <MessageSquare className="h-4 w-4" />, perm: 'notifications.view' },
      { to: '/app/audit', label: 'Audit logs', icon: <FileClock className="h-4 w-4" />, perm: 'audit.view' },
      { to: '/app/settings', label: 'Settings & integrations', icon: <Settings className="h-4 w-4" />, perm: 'config.manage' },
    ],
  },
]

export function AppLayout() {
  const { user, ready, logout, can } = useAuth()
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  if (!ready) return <Spinner />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />

  const roleLabel = { system_admin: 'System administrator', facility_admin: 'Facility administrator', facility_staff: 'Facility staff' }[user.role]
  const nav = (
    <nav className="space-y-6 px-3 py-4" aria-label="Application">
      {NAV.map((s) => {
        const items = s.items.filter((i) => !i.perm || can(i.perm))
        if (!items.length) return null
        return (
          <div key={s.section}>
            <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-brand-200/80">{s.section}</p>
            {items.map((i) => (
              <NavLink
                key={i.to}
                to={i.to}
                end={i.end}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium',
                    isActive ? 'bg-white/15 text-white' : 'text-brand-100 hover:bg-white/10 hover:text-white',
                  )
                }
              >
                {i.icon}
                {i.label}
              </NavLink>
            ))}
          </div>
        )
      })}
    </nav>
  )

  return (
    <div className="min-h-screen">
      <DemoBanner />
      <div className="flex">
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-brand-900 lg:flex">
          <Link to="/" className="px-6 py-5">
            <Logo light />
          </Link>
          <div className="flex-1 overflow-y-auto">{nav}</div>
          <div className="border-t border-white/10 px-6 py-4 text-xs text-brand-100">
            <Activity className="mr-1 inline h-3.5 w-3.5" aria-hidden /> Data shown is from the live database.
          </div>
        </aside>
        {open && (
          <div className="fixed inset-0 z-[900] lg:hidden" onClick={() => setOpen(false)}>
            <div className="absolute inset-0 bg-slate-900/40" />
            <aside className="absolute inset-y-0 left-0 w-72 overflow-y-auto bg-brand-900" onClick={(e) => e.stopPropagation()}>
              <div className="px-6 py-5">
                <Logo light />
              </div>
              {nav}
            </aside>
          </div>
        )}
        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-[400] flex h-16 items-center justify-between gap-3 border-b border-slate-200 bg-white/95 px-4 backdrop-blur lg:px-8">
            <button className="rounded-lg p-2 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
              <Menu className="h-6 w-6" />
            </button>
            <div className="min-w-0 flex-1 truncate text-sm text-slate-600">
              {user.memberships.length > 0 && (
                <span>
                  {user.memberships.map((m) => m.facility_name).join(', ')}
                  {user.memberships.some((m) => m.facility_status !== 'approved') && (
                    <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900">Awaiting approval</span>
                  )}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <div className="hidden text-right sm:block">
                <p className="text-sm font-medium text-ink">{user.full_name}</p>
                <p className="text-xs text-slate-500">{roleLabel}</p>
              </div>
              <button
                onClick={async () => {
                  await logout()
                  navigate('/login')
                }}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                <LogOut className="h-4 w-4" aria-hidden /> Sign out
              </button>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-4 py-6 lg:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
