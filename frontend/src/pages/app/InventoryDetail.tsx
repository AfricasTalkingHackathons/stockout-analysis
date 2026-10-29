import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { StatusBadge } from '../../components/StatusBadge'
import { Button, Card, CardHeader, ErrorState, Field, Input, Notice, Pagination, Spinner, Stat, Table, Td, Textarea, Th } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { formatDate, formatDateTime, humanize } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { InventoryItem, Movement, Page } from '../../lib/types'
import { MovementForm } from './Inventory'

interface History {
  item: InventoryItem
  movements: Page<Movement>
  levels: { at: string; quantity: number }[]
}

export default function InventoryDetail() {
  const { id } = useParams()
  const { can } = useAuth()
  const [page, setPage] = useState(1)
  const [formKey, setFormKey] = useState(0)
  const h = useAsync(() => api.get<History>(`/api/inventory/${id}/history`, { page, page_size: 20, days: 60 }), [id, page])
  const item = h.data?.item

  return (
    <div>
      <Link to="/app/inventory" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Inventory
      </Link>
      {h.loading && !h.data && <Spinner />}
      <ErrorState error={h.error} onRetry={h.reload} />
      {item && h.data && (
        <>
          <div className="mb-6 mt-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{item.medicine.display_name}</h1>
              <p className="text-sm text-slate-600">
                {item.medicine.code} · {item.facility_name} · unit: {item.unit}
              </p>
            </div>
            <StatusBadge status={item.stock_status} />
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="On hand" value={`${item.quantity.toLocaleString()}`} hint={`${item.unit}s`} />
            <Stat label="Minimum threshold" value={item.min_threshold.toLocaleString()} />
            <Stat
              label="Est. days remaining"
              value={item.estimate?.days_remaining != null ? `~${item.estimate.days_remaining}` : 'n/a'}
              hint={item.estimate?.days_remaining != null ? `Avg ${item.estimate.avg_daily}/day over recent dispensing` : item.estimate?.reason}
            />
            <Stat label="Last updated" value={<span className="text-base">{formatDateTime(item.last_updated_at)}</span>} hint={item.last_updated_by ?? undefined} />
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[1.5fr_1fr]">
            <Card>
              <CardHeader title="Stock level history" subtitle="Quantity after each recorded movement (last 60 days)" />
              <div className="h-64 px-2 py-4">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={h.data.levels.map((l) => ({ ...l, label: formatDate(l.at) }))} margin={{ left: -10, right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="label" fontSize={11} interval="preserveStartEnd" />
                    <YAxis fontSize={11} />
                    <Tooltip />
                    <ReferenceLine y={item.min_threshold} stroke="#d97706" strokeDasharray="4 4" label={{ value: 'Minimum', fontSize: 11, fill: '#92400e' }} />
                    <Line type="stepAfter" dataKey="quantity" stroke="#0b5d57" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
            {can('inventory.update') && (
              <Card>
                <CardHeader title="Record a stock movement" />
                <div className="p-5">
                  <MovementForm key={formKey + item.version} item={item} onDone={() => (h.reload(), setTimeout(() => setFormKey((k) => k + 1), 2500))} />
                </div>
              </Card>
            )}
          </div>

          {can('inventory.update') && <SettingsCard item={item} onSaved={h.reload} />}

          <Card className="mt-6">
            <CardHeader title="Movement history" subtitle="Every change is kept; history is never overwritten." />
            <Table>
              <thead className="bg-slate-50">
                <tr>
                  <Th>When</Th>
                  <Th>Type</Th>
                  <Th className="text-right">Before</Th>
                  <Th className="text-right">Change</Th>
                  <Th className="text-right">After</Th>
                  <Th>Reason</Th>
                  <Th>By</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {h.data.movements.items.map((m) => (
                  <tr key={m.id}>
                    <Td className="whitespace-nowrap text-xs">{formatDateTime(m.created_at)}</Td>
                    <Td>
                      {humanize(m.movement_type)}
                      <span className="block text-xs text-slate-500">via {m.source}</span>
                    </Td>
                    <Td className="text-right tabular-nums">{m.quantity_before}</Td>
                    <Td className={`text-right tabular-nums ${m.quantity_delta < 0 ? 'text-red-700' : 'text-emerald-700'}`}>
                      {m.quantity_delta > 0 ? '+' : ''}
                      {m.quantity_delta}
                    </Td>
                    <Td className="text-right font-medium tabular-nums">{m.quantity_after}</Td>
                    <Td className="text-xs">{m.reason ?? 'n/a'}</Td>
                    <Td className="text-xs">{m.performed_by ?? 'n/a'}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} pageSize={20} total={h.data.movements.total} onPage={setPage} />
          </Card>
        </>
      )}
    </div>
  )
}

function SettingsCard({ item, onSaved }: { item: InventoryItem; onSaved: () => void }) {
  const [min, setMin] = useState(String(item.min_threshold))
  const [batch, setBatch] = useState(item.batch_number ?? '')
  const [expiry, setExpiry] = useState(item.expiry_date ?? '')
  const [notes, setNotes] = useState(item.internal_notes ?? '')
  const [msg, setMsg] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <Card className="mt-6">
      <CardHeader title="Thresholds and batch details" subtitle="Internal notes are never shown publicly." />
      <form
        className="grid gap-4 p-5 md:grid-cols-4"
        onSubmit={async (e) => {
          e.preventDefault()
          const n = Number(min)
          if (!Number.isInteger(n) || n < 0) return setMsg({ tone: 'danger', text: 'Minimum must be a whole number ≥ 0' })
          setBusy(true)
          try {
            await api.patch(`/api/inventory/${item.id}`, {
              min_threshold: n,
              batch_number: batch || null,
              expiry_date: expiry || null,
              internal_notes: notes || null,
              expected_version: item.version,
            })
            setMsg({ tone: 'success', text: 'Saved.' })
            onSaved()
          } catch (err) {
            setMsg({ tone: 'danger', text: err instanceof ApiError ? err.message : 'Failed' })
          } finally {
            setBusy(false)
          }
        }}
      >
        <Field label="Minimum threshold">{(id) => <Input id={id} type="number" min={0} value={min} onChange={(e) => setMin(e.target.value)} />}</Field>
        <Field label="Batch number">{(id) => <Input id={id} value={batch} onChange={(e) => setBatch(e.target.value)} />}</Field>
        <Field label="Expiry date">{(id) => <Input id={id} type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} />}</Field>
        <Field label="Internal notes">{(id) => <Textarea id={id} className="min-h-10" value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <div className="flex items-center gap-3 md:col-span-4">
          <Button type="submit" variant="secondary" loading={busy}>
            Save details
          </Button>
          {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
        </div>
      </form>
    </Card>
  )
}
