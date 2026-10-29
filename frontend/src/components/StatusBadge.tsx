import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, Clock, HelpCircle, Info, ShieldAlert, XCircle } from 'lucide-react'
import { humanize } from '../lib/format'

const STATUS = {
  available: { label: 'Reported available', cls: 'bg-emerald-50 text-emerald-800 ring-emerald-200', Icon: CheckCircle2 },
  low: { label: 'Reported low stock', cls: 'bg-amber-50 text-amber-900 ring-amber-200', Icon: AlertTriangle },
  out_of_stock: { label: 'Reported out of stock', cls: 'bg-red-50 text-red-800 ring-red-200', Icon: XCircle },
  stale: { label: 'Stale: needs confirmation', cls: 'bg-stone-100 text-stone-800 ring-stone-300', Icon: Clock },
  unknown: { label: 'Unknown: no recent report', cls: 'bg-slate-100 text-slate-700 ring-slate-300', Icon: HelpCircle },
} as const

export function StatusBadge({ status, short = false, className }: { status: string; short?: boolean; className?: string }) {
  const s = STATUS[status as keyof typeof STATUS] ?? STATUS.unknown
  const shortLabel = { available: 'Available', low: 'Low', out_of_stock: 'Out of stock', stale: 'Stale', unknown: 'Unknown' }[
    status as keyof typeof STATUS
  ]
  return (
    <span className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset', s.cls, className)}>
      <s.Icon className="h-3.5 w-3.5" aria-hidden />
      {short ? shortLabel ?? humanize(status) : s.label}
    </span>
  )
}

const SEVERITY = {
  critical: { cls: 'bg-red-700 text-white', Icon: ShieldAlert },
  warning: { cls: 'bg-amber-100 text-amber-900 ring-1 ring-inset ring-amber-300', Icon: AlertTriangle },
  info: { cls: 'bg-sky-50 text-sky-900 ring-1 ring-inset ring-sky-200', Icon: Info },
} as const

export function SeverityBadge({ severity }: { severity: string }) {
  const s = SEVERITY[severity as keyof typeof SEVERITY] ?? SEVERITY.info
  return (
    <span className={clsx('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold uppercase tracking-wide', s.cls)}>
      <s.Icon className="h-3.5 w-3.5" aria-hidden />
      {severity}
    </span>
  )
}

export function Pill({ children, tone = 'slate' }: { children: React.ReactNode; tone?: 'slate' | 'brand' | 'amber' | 'red' | 'green' | 'violet' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700',
    brand: 'bg-brand-50 text-brand-800',
    amber: 'bg-amber-50 text-amber-900',
    red: 'bg-red-50 text-red-800',
    green: 'bg-emerald-50 text-emerald-800',
    violet: 'bg-violet-50 text-violet-800',
  }
  return <span className={clsx('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium', tones[tone])}>{children}</span>
}

export function AlertStatusPill({ status }: { status: string }) {
  const tone = status === 'open' ? 'red' : status === 'resolved' ? 'green' : status === 'dismissed' ? 'slate' : 'amber'
  return <Pill tone={tone}>{humanize(status)}</Pill>
}

export function DeliveryStatusPill({ status }: { status: string }) {
  const map: Record<string, { tone: 'slate' | 'brand' | 'amber' | 'red' | 'green' | 'violet'; label: string }> = {
    queued: { tone: 'slate', label: 'Queued' },
    simulated: { tone: 'violet', label: 'Simulated (not sent)' },
    accepted: { tone: 'brand', label: 'Accepted by provider' },
    delivered: { tone: 'green', label: 'Delivered' },
    failed: { tone: 'red', label: 'Failed' },
    retrying: { tone: 'amber', label: 'Retrying' },
  }
  const s = map[status] ?? { tone: 'slate', label: humanize(status) }
  return <Pill tone={s.tone}>{s.label}</Pill>
}
