import clsx from 'clsx'
import { AlertCircle, ChevronLeft, ChevronRight, Inbox, Loader2 } from 'lucide-react'
import {
  forwardRef,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import type { ApiError } from '../lib/api'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'

const variants: Record<Variant, string> = {
  primary: 'bg-brand-700 text-white hover:bg-brand-800 shadow-sm',
  secondary: 'bg-brand-50 text-brand-800 hover:bg-brand-100 ring-1 ring-inset ring-brand-200',
  outline: 'bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50',
  ghost: 'text-slate-700 hover:bg-slate-100',
  danger: 'bg-red-700 text-white hover:bg-red-800 shadow-sm',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export function Button({ variant = 'primary', size = 'md', loading, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60',
        size === 'sm' && 'h-8 px-3 text-sm',
        size === 'md' && 'h-10 px-4 text-sm',
        size === 'lg' && 'h-12 px-6 text-base',
        variants[variant],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={clsx('rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(16,34,43,0.04)]', className)} {...rest}>
      {children}
    </div>
  )
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
      <div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

interface FieldProps {
  label: string
  error?: string
  hint?: string
  children: (id: string, describedBy?: string) => ReactNode
  required?: boolean
}

export function Field({ label, error, hint, children, required }: FieldProps) {
  const id = useId()
  const descId = error || hint ? `${id}-desc` : undefined
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-slate-800">
        {label}
        {required && <span className="text-red-700" aria-hidden> *</span>}
      </label>
      {children(id, descId)}
      {error ? (
        <p id={descId} className="flex items-center gap-1 text-sm text-red-700" role="alert">
          <AlertCircle className="h-4 w-4" aria-hidden /> {error}
        </p>
      ) : hint ? (
        <p id={descId} className="text-xs text-slate-500">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

const control =
  'block w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-slate-100 aria-[invalid=true]:border-red-500'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={clsx(control, 'h-10', className)} {...rest} />
})

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...rest }, ref) {
  return (
    <select ref={ref} className={clsx(control, 'h-10 pr-8', className)} {...rest}>
      {children}
    </select>
  )
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={clsx(control, 'min-h-20 py-2', className)} {...rest} />
})

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500" role="status">
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden /> {label}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error | null; onRetry?: () => void }) {
  if (!error) return null
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
      <AlertCircle className="h-5 w-5 shrink-0" aria-hidden />
      <span className="flex-1">{error.message}</span>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 rounded-full bg-slate-100 p-3 text-slate-500">{icon ?? <Inbox className="h-6 w-6" aria-hidden />}</div>
      <p className="font-medium text-slate-800">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-slate-500">{children}</div>}
    </div>
  )
}

export function Notice({ tone = 'info', children, title }: { tone?: 'info' | 'warning' | 'success' | 'danger'; children: ReactNode; title?: string }) {
  const tones = {
    info: 'border-sky-200 bg-sky-50 text-sky-900',
    warning: 'border-amber-200 bg-amber-50 text-amber-900',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    danger: 'border-red-200 bg-red-50 text-red-900',
  }
  return (
    <div className={clsx('rounded-lg border px-4 py-3 text-sm', tones[tone])} role={tone === 'danger' ? 'alert' : 'status'}>
      {title && <p className="mb-0.5 font-semibold">{title}</p>}
      {children}
    </div>
  )
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total <= pageSize) return <p className="px-5 py-3 text-xs text-slate-500">{total} record{total === 1 ? '' : 's'}</p>
  return (
    <div className="flex items-center justify-between gap-3 px-5 py-3 text-sm text-slate-600">
      <span>
        Page {page} of {pages} · {total} records
      </span>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </Button>
        <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight className="h-4 w-4" aria-hidden />
        </Button>
      </div>
    </div>
  )
}

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm">{children}</table>
    </div>
  )
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return <th scope="col" className={clsx('whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500', className)}>{children}</th>
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={clsx('px-4 py-3 align-top text-slate-700', className)}>{children}</td>
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-600">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function Modal({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[1000] flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:max-w-lg sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <button className="rounded p-1 text-slate-500 hover:bg-slate-100" onClick={onClose} aria-label="Close dialog">
            ✕
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  )
}

export function Stat({ label, value, tone = 'default', hint, icon }: { label: string; value: ReactNode; tone?: 'default' | 'good' | 'warn' | 'bad' | 'muted'; hint?: string; icon?: ReactNode }) {
  const tones = {
    default: 'text-ink',
    good: 'text-emerald-700',
    warn: 'text-amber-700',
    bad: 'text-red-700',
    muted: 'text-slate-600',
  }
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
        {icon}
      </div>
      <p className={clsx('mt-2 text-2xl font-semibold tabular-nums', tones[tone])}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </Card>
  )
}
