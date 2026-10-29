import { zodResolver } from '@hookform/resolvers/zod'
import { Plus, RefreshCcw, Send } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { DeliveryStatusPill, Pill } from '../../components/StatusBadge'
import { Button, Card, CardHeader, EmptyState, ErrorState, Field, Input, Modal, Notice, PageHeader, Pagination, Spinner, Table, Td, Th } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { formatDateTime, humanize, timeAgo } from '../../lib/format'
import { useAsync, useDebounced } from '../../lib/hooks'
import type { Delivery, Medicine, Page } from '../../lib/types'
import { phoneSchema } from '../../lib/validation'
import { FilterSelect } from './common'

/* ---------------------------------------------------------------- catalog */

const medSchema = z.object({
  code: z.string().regex(/^[A-Z0-9-]{3,12}$/, '3 to 12 capitals/digits, e.g. MED019'),
  generic_name: z.string().trim().min(2),
  brand_names: z.string().optional(),
  strength: z.string().trim().min(1),
  dosage_form: z.string().trim().min(2),
  base_unit: z.string().trim().min(2),
  category: z.string().optional(),
  requires_prescription: z.boolean(),
  is_long_term: z.boolean(),
})

export function Catalog() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const dq = useDebounced(q)
  const list = useAsync(() => api.get<Page<Medicine>>('/api/admin/medicines', { q: dq, page, page_size: 25 }), [dq, page])
  const toggle = async (m: Medicine) => {
    await api.patch(`/api/admin/medicines/${m.id}`, { is_active: !m.is_active })
    list.reload()
  }
  return (
    <div>
      <PageHeader
        title="Medicine catalog"
        description="One entry per generic, strength and dosage form. Every facility records quantities in the entry's base unit so reports are comparable."
        actions={
          <Button onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" aria-hidden /> Add medicine
          </Button>
        }
      />
      <Card className="mb-4 p-4">
        <Input placeholder="Search generic, brand or code" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} aria-label="Search catalog" />
      </Card>
      <Card>
        {list.loading && !list.data && <Spinner />}
        <ErrorState error={list.error} onRetry={list.reload} />
        {!!list.data?.items.length && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>Code</Th>
                <Th>Generic name</Th>
                <Th>Strength / form</Th>
                <Th>Base unit</Th>
                <Th>Brand aliases</Th>
                <Th>Rx</Th>
                <Th>Repeating</Th>
                <Th>Active</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((m) => (
                <tr key={m.id}>
                  <Td className="font-mono text-xs">{m.code}</Td>
                  <Td className="font-medium text-ink">{m.generic_name}</Td>
                  <Td>
                    {m.strength} {m.dosage_form}
                  </Td>
                  <Td>{m.base_unit}</Td>
                  <Td className="text-xs">{m.brand_names.join(', ') || 'n/a'}</Td>
                  <Td>{m.requires_prescription ? <Pill tone="violet">Rx</Pill> : 'n/a'}</Td>
                  <Td>{m.is_long_term ? <Pill tone="slate">Repeating</Pill> : 'n/a'}</Td>
                  <Td>
                    <input type="checkbox" className="h-4 w-4" checked={!!m.is_active} onChange={() => toggle(m)} aria-label={`Active: ${m.generic_name}`} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && <Pagination page={page} pageSize={25} total={list.data.total} onPage={setPage} />}
      </Card>
      <Modal open={adding} title="Add catalog entry" onClose={() => setAdding(false)}>
        <MedicineForm
          onDone={() => {
            setAdding(false)
            list.reload()
          }}
        />
      </Modal>
    </div>
  )
}

function MedicineForm({ onDone }: { onDone: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof medSchema>, unknown, z.output<typeof medSchema>>({
    resolver: zodResolver(medSchema),
    defaultValues: { requires_prescription: false, is_long_term: false },
  })
  const e = formState.errors
  return (
    <form
      noValidate
      className="space-y-3"
      onSubmit={handleSubmit(async (v) => {
        setError(null)
        try {
          await api.post('/api/admin/medicines', {
            ...v,
            brand_names: (v.brand_names ?? '').split(',').map((s) => s.trim()).filter(Boolean),
            category: v.category || null,
          })
          onDone()
        } catch (err) {
          setError(err instanceof ApiError ? err.message : 'Failed')
        }
      })}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Code" error={e.code?.message}>{(id) => <Input id={id} {...register('code')} placeholder="MED019" />}</Field>
        <Field label="Generic name" error={e.generic_name?.message}>{(id) => <Input id={id} {...register('generic_name')} />}</Field>
        <Field label="Strength" error={e.strength?.message}>{(id) => <Input id={id} {...register('strength')} placeholder="250 mg" />}</Field>
        <Field label="Dosage form" error={e.dosage_form?.message}>{(id) => <Input id={id} {...register('dosage_form')} placeholder="tablet" />}</Field>
        <Field label="Base unit" error={e.base_unit?.message} hint="Smallest countable unit">
          {(id, d) => <Input id={id} aria-describedby={d} {...register('base_unit')} placeholder="tablet" />}
        </Field>
        <Field label="Category">{(id) => <Input id={id} {...register('category')} />}</Field>
      </div>
      <Field label="Brand aliases (comma separated)" hint="Used only to help people search">
        {(id, d) => <Input id={id} aria-describedby={d} {...register('brand_names')} />}
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="h-4 w-4" {...register('requires_prescription')} /> Prescription-only medicine
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="h-4 w-4" {...register('is_long_term')} /> Typically collected on a repeating schedule
      </label>
      {error && <Notice tone="danger">{error}</Notice>}
      <Button type="submit" loading={formState.isSubmitting}>
        Add to catalog
      </Button>
    </form>
  )
}

/* ---------------------------------------------------------------- notifications */

export function Notifications() {
  const { can } = useAuth()
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const list = useAsync(() => api.get<Page<Delivery>>('/api/notifications/history', { status, page, page_size: 25 }), [status, page])
  return (
    <div>
      <PageHeader
        title="Notification history"
        description="“Accepted” means Africa's Talking accepted the message; only a delivery report marks it “Delivered”. “Simulated” messages never left the server."
        actions={
          <Button variant="outline" onClick={list.reload}>
            <RefreshCcw className="h-4 w-4" aria-hidden /> Refresh
          </Button>
        }
      />
      {can('notifications.test') && <TestSms onSent={list.reload} />}
      <Card className="mb-4 mt-6 p-4">
        <FilterSelect label="Delivery status" value={status} onChange={(v) => (setStatus(v), setPage(1))}>
          <option value="">All</option>
          {['queued', 'simulated', 'accepted', 'delivered', 'retrying', 'failed'].map((s) => (
            <option key={s} value={s}>
              {humanize(s)}
            </option>
          ))}
        </FilterSelect>
      </Card>
      <Card>
        {list.loading && !list.data && <Spinner />}
        <ErrorState error={list.error} onRetry={list.reload} />
        {list.data?.items.length === 0 && <EmptyState title="No notifications yet" />}
        {!!list.data?.items.length && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>When</Th>
                <Th>To</Th>
                <Th>Purpose</Th>
                <Th>Message</Th>
                <Th>Status</Th>
                <Th>Attempts</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((d) => (
                <tr key={d.id}>
                  <Td className="whitespace-nowrap text-xs">{formatDateTime(d.created_at)}</Td>
                  <Td className="font-mono text-xs">{d.recipient}</Td>
                  <Td className="text-xs">{humanize(d.purpose)}</Td>
                  <Td className="max-w-md text-xs">{d.message}</Td>
                  <Td>
                    <DeliveryStatusPill status={d.status} />
                    {d.failure_reason && <span className="mt-1 block text-xs text-red-700">{d.failure_reason}</span>}
                    {d.provider_status && <span className="mt-1 block text-xs text-slate-500">{d.provider_status}</span>}
                  </Td>
                  <Td className="tabular-nums">{d.attempts}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && <Pagination page={page} pageSize={25} total={list.data.total} onPage={setPage} />}
      </Card>
    </div>
  )
}

const testSchema = z.object({ phone: phoneSchema, message: z.string().min(3).max(300) })

function TestSms({ onSent }: { onSent: () => void }) {
  const [result, setResult] = useState<Delivery | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof testSchema>, unknown, z.output<typeof testSchema>>({
    resolver: zodResolver(testSchema),
    defaultValues: { message: 'StockOut Alert test message.' },
  })
  return (
    <Card>
      <CardHeader title="Send a test SMS" subtitle="Uses the configured provider. In demo mode, only numbers on DEMO_SMS_ALLOWLIST are sent live." />
      <form
        noValidate
        className="grid gap-3 p-5 md:grid-cols-[1fr_2fr_auto] md:items-end"
        onSubmit={handleSubmit(async (v) => {
          setError(null)
          try {
            setResult(await api.post<Delivery>('/api/notifications/test', v))
            onSent()
          } catch (err) {
            setError(err instanceof ApiError ? err.message : 'Failed')
          }
        })}
      >
        <Field label="Phone" error={formState.errors.phone?.message}>{(id) => <Input id={id} inputMode="tel" {...register('phone')} />}</Field>
        <Field label="Message" error={formState.errors.message?.message}>{(id) => <Input id={id} {...register('message')} />}</Field>
        <Button type="submit" loading={formState.isSubmitting}>
          <Send className="h-4 w-4" aria-hidden /> Send
        </Button>
      </form>
      {(result || error) && (
        <div className="px-5 pb-5">
          {error && <Notice tone="danger">{error}</Notice>}
          {result && (
            <Notice tone={result.status === 'failed' ? 'danger' : 'info'}>
              Result: <strong>{humanize(result.status)}</strong> via {result.provider}
              {result.failure_reason && ` (${result.failure_reason})`}
              {result.provider_status && ` (${result.provider_status})`}
            </Notice>
          )}
        </div>
      )}
    </Card>
  )
}

/* ---------------------------------------------------------------- audit */

interface AuditRow {
  id: string
  actor_label: string
  action: string
  entity_type: string
  entity_id: string | null
  details: Record<string, unknown>
  ip_address: string | null
  created_at: string
}

export function AuditLogs() {
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('')
  const [page, setPage] = useState(1)
  const da = useDebounced(actor)
  const list = useAsync(() => api.get<Page<AuditRow>>('/api/admin/audit-logs', { action, actor: da, page, page_size: 40 }), [action, da, page])
  return (
    <div>
      <PageHeader title="Audit logs" description="Inventory changes, verification decisions, administrative actions and sign-ins. Audit entries are never deleted by demo resets." />
      <Card className="mb-4 p-4">
        <div className="flex flex-wrap gap-3">
          <FilterSelect label="Action" value={action} onChange={(v) => (setAction(v), setPage(1))}>
            <option value="">All</option>
            {['inventory', 'facility', 'alert', 'report', 'staff', 'catalog', 'config', 'auth', 'sms', 'demo', 'notification'].map((a) => (
              <option key={a} value={a}>
                {humanize(a)}
              </option>
            ))}
          </FilterSelect>
          <label className="block min-w-[200px] text-xs font-medium text-slate-600">
            Actor
            <Input className="mt-1" value={actor} onChange={(e) => (setActor(e.target.value), setPage(1))} placeholder="email or label" />
          </label>
        </div>
      </Card>
      <Card>
        {list.loading && !list.data && <Spinner />}
        <ErrorState error={list.error} onRetry={list.reload} />
        {!!list.data?.items.length && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>When</Th>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Entity</Th>
                <Th>Details</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((r) => (
                <tr key={r.id}>
                  <Td className="whitespace-nowrap text-xs">
                    {formatDateTime(r.created_at)}
                    <span className="block text-slate-500">{timeAgo(r.created_at)}</span>
                  </Td>
                  <Td className="text-xs">{r.actor_label}</Td>
                  <Td>
                    <code className="text-xs">{r.action}</code>
                  </Td>
                  <Td className="text-xs">
                    {r.entity_type}
                    {r.entity_id && <span className="block font-mono text-slate-500">{r.entity_id.slice(0, 8)}</span>}
                  </Td>
                  <Td className="max-w-md">
                    <code className="block whitespace-pre-wrap break-all text-[11px] text-slate-600">{JSON.stringify(r.details)}</code>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && <Pagination page={page} pageSize={40} total={list.data.total} onPage={setPage} />}
      </Card>
    </div>
  )
}
