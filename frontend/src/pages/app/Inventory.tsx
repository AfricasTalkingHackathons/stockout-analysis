import { zodResolver } from '@hookform/resolvers/zod'
import { Download, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { MedicinePicker } from '../../components/MedicinePicker'
import { StatusBadge } from '../../components/StatusBadge'
import { Button, Card, EmptyState, ErrorState, Field, Input, Modal, Notice, PageHeader, Pagination, Select, Spinner, Table, Td, Th, Textarea } from '../../components/ui'
import { ApiError, api, newClientToken } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { formatDate, timeAgo } from '../../lib/format'
import { useAsync, useDebounced } from '../../lib/hooks'
import type { Alert, InventoryItem, Medicine, Page } from '../../lib/types'
import { FilterSelect, useFacilityOptions } from './common'

export default function Inventory() {
  const { can, user } = useAuth()
  const [facilityId, setFacilityId] = useState('')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const [moving, setMoving] = useState<InventoryItem | null>(null)
  const dq = useDebounced(q)
  const facilities = useFacilityOptions()
  const list = useAsync(
    () => api.get<Page<InventoryItem>>('/api/inventory', { facility_id: facilityId, status, q: dq, page, page_size: 25 }),
    [facilityId, status, dq, page],
  )
  const canExport = can('inventory.export') || can('facility.view_all')
  const canEdit = can('inventory.update') && (user?.role === 'system_admin' || user?.memberships.some((m) => m.can_update_stock))

  return (
    <div>
      <PageHeader
        title="Inventory"
        description="Quantities are recorded in each medicine's catalog base unit (e.g. tablets, capsules, vials)."
        actions={
          <>
            {canExport && (
              <Button variant="outline" onClick={() => api.download('/api/inventory/export.csv', { facility_id: facilityId, status }, 'inventory.csv')}>
                <Download className="h-4 w-4" aria-hidden /> Export CSV
              </Button>
            )}
            {canEdit && (
              <Button onClick={() => setAdding(true)}>
                <Plus className="h-4 w-4" aria-hidden /> Add medicine
              </Button>
            )}
          </>
        }
      />
      <Card className="mb-4 p-4">
        <div className="flex flex-wrap gap-3">
          <label className="block min-w-[200px] flex-[2] text-xs font-medium text-slate-600">
            Search
            <Input className="mt-1" placeholder="Medicine name or code" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} />
          </label>
          {(facilities.data?.length ?? 0) > 1 && (
            <FilterSelect label="Facility" value={facilityId} onChange={(v) => (setFacilityId(v), setPage(1))}>
              <option value="">All facilities</option>
              {facilities.data?.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </FilterSelect>
          )}
          <FilterSelect label="Status" value={status} onChange={(v) => (setStatus(v), setPage(1))}>
            <option value="">All</option>
            <option value="available">Available</option>
            <option value="low">Low</option>
            <option value="out_of_stock">Out of stock</option>
            <option value="stale">Stale (needs update)</option>
            <option value="expiring">Expiring soon</option>
          </FilterSelect>
        </div>
      </Card>
      <Card>
        {list.loading && !list.data && <Spinner />}
        <div className="p-4">
          <ErrorState error={list.error} onRetry={list.reload} />
        </div>
        {list.data && list.data.items.length === 0 && <EmptyState title="No inventory records match">Add a medicine to start tracking stock.</EmptyState>}
        {list.data && list.data.items.length > 0 && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>Medicine</Th>
                <Th>Facility</Th>
                <Th>Status</Th>
                <Th className="text-right">Quantity</Th>
                <Th className="text-right">Minimum</Th>
                <Th>Expiry</Th>
                <Th>Last updated</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((i) => (
                <tr key={i.id} className="hover:bg-slate-50/60">
                  <Td>
                    <Link to={`/app/inventory/${i.id}`} className="font-medium text-ink hover:text-brand-700 hover:underline">
                      {i.medicine.generic_name}
                    </Link>
                    <span className="block text-xs text-slate-500">
                      {i.medicine.code} · {i.medicine.strength} {i.medicine.dosage_form}
                    </span>
                  </Td>
                  <Td className="text-xs">{i.facility_name}</Td>
                  <Td>
                    <StatusBadge status={i.stock_status} short />
                  </Td>
                  <Td className="text-right font-medium tabular-nums">
                    {i.quantity.toLocaleString()} <span className="text-xs font-normal text-slate-500">{i.unit}</span>
                  </Td>
                  <Td className="text-right tabular-nums">{i.min_threshold.toLocaleString()}</Td>
                  <Td className="text-xs">{i.expiry_date ? formatDate(i.expiry_date) : 'n/a'}</Td>
                  <Td className="whitespace-nowrap text-xs">
                    {timeAgo(i.last_updated_at)}
                    {i.last_updated_by && <span className="block text-slate-500">{i.last_updated_by}</span>}
                  </Td>
                  <Td>
                    {canEdit && (
                      <Button size="sm" variant="secondary" onClick={() => setMoving(i)}>
                        Update stock
                      </Button>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && <Pagination page={page} pageSize={25} total={list.data.total} onPage={setPage} />}
      </Card>

      <Modal open={adding} title="Add medicine to inventory" onClose={() => setAdding(false)}>
        <AddInventoryForm
          facilities={(facilities.data ?? []).filter((f) => user?.role === 'system_admin' || user?.memberships.find((m) => m.facility_id === f.id)?.can_update_stock)}
          onDone={() => {
            setAdding(false)
            list.reload()
          }}
        />
      </Modal>
      <Modal open={!!moving} title={moving ? `Update stock: ${moving.medicine.display_name}` : ''} onClose={() => setMoving(null)}>
        {moving && <MovementForm item={moving} onDone={() => list.reload()} onClose={() => setMoving(null)} />}
      </Modal>
    </div>
  )
}

const addSchema = z.object({
  facility_id: z.string().min(1, 'Choose a facility'),
  quantity: z.coerce.number<string>().int('Whole numbers only').min(0, 'Cannot be negative'),
  min_threshold: z.coerce.number<string>().int('Whole numbers only').min(0, 'Cannot be negative'),
  batch_number: z.string().max(60).optional(),
  expiry_date: z.string().optional(),
})

function AddInventoryForm({ facilities, onDone }: { facilities: { id: string; name: string }[]; onDone: () => void }) {
  const [med, setMed] = useState<Medicine | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [alerts, setAlerts] = useState<Alert[] | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof addSchema>, unknown, z.output<typeof addSchema>>({
    resolver: zodResolver(addSchema),
    defaultValues: { facility_id: facilities[0]?.id ?? '', quantity: '0', min_threshold: '0' },
  })
  const e = formState.errors
  if (alerts)
    return (
      <div className="space-y-3">
        <Notice tone="success">Inventory record created.</Notice>
        {alerts.map((a) => (
          <Notice key={a.id} tone="warning">
            Alert raised: {a.title}
          </Notice>
        ))}
        <Button onClick={onDone}>Done</Button>
      </div>
    )
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit(async (v) => {
        if (!med) return setError('Choose a medicine from the catalog')
        setError(null)
        try {
          const r = await api.post<{ alerts: Alert[] }>('/api/inventory', {
            facility_id: v.facility_id,
            medicine_id: med.id,
            quantity: v.quantity,
            min_threshold: v.min_threshold,
            batch_number: v.batch_number || null,
            expiry_date: v.expiry_date || null,
          })
          setAlerts(r.alerts)
        } catch (err) {
          setError(err instanceof ApiError ? err.message : 'Failed')
        }
      })}
    >
      <Field label="Facility" error={e.facility_id?.message}>
        {(id) => (
          <Select id={id} {...register('facility_id')}>
            {facilities.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <MedicinePicker value={med} onChange={setMed} label="Medicine (from catalog)" />
      {med && <p className="text-xs text-slate-600">Record quantities in <strong>{med.base_unit}s</strong>. Convert packs to individual units before saving.</p>}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Current quantity" error={e.quantity?.message}>
          {(id) => <Input id={id} type="number" min={0} inputMode="numeric" {...register('quantity')} />}
        </Field>
        <Field label="Minimum threshold" error={e.min_threshold?.message} hint="Low-stock alert at or below this">
          {(id, d) => <Input id={id} type="number" min={0} aria-describedby={d} {...register('min_threshold')} />}
        </Field>
        <Field label="Batch number">{(id) => <Input id={id} {...register('batch_number')} />}</Field>
        <Field label="Expiry date">{(id) => <Input id={id} type="date" {...register('expiry_date')} />}</Field>
      </div>
      {error && <Notice tone="danger">{error}</Notice>}
      <Button type="submit" loading={formState.isSubmitting}>
        Save
      </Button>
    </form>
  )
}

const moveSchema = z.object({
  movement_type: z.enum(['count', 'receipt', 'dispense', 'adjustment']),
  quantity: z.coerce.number<string>().int('Whole numbers only'),
  reason: z.string().max(255).optional(),
})

export function MovementForm({ item, onDone, onClose }: { item: InventoryItem; onDone: () => void; onClose?: () => void }) {
  const key = useMemo(() => newClientToken(), [])
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ item: InventoryItem; alerts: Alert[] } | null>(null)
  const { register, handleSubmit, watch, formState } = useForm<z.input<typeof moveSchema>, unknown, z.output<typeof moveSchema>>({
    resolver: zodResolver(moveSchema),
    defaultValues: { movement_type: 'count', quantity: String(item.quantity) },
  })
  const type = watch('movement_type')
  if (result)
    return (
      <div className="space-y-3">
        <Notice tone="success">
          Recorded. {item.medicine.generic_name} is now {result.item.quantity.toLocaleString()} {result.item.unit}s.
        </Notice>
        {result.alerts.map((a) => (
          <Notice key={a.id} tone={a.severity === 'critical' ? 'danger' : 'warning'} title={a.alert_type === 'ripple' ? 'Ripple signal raised' : 'Alert raised'}>
            {a.title}
          </Notice>
        ))}
        {onClose && <Button onClick={onClose}>Close</Button>}
      </div>
    )
  const labels = {
    count: 'Counted quantity on hand',
    receipt: 'Quantity received',
    dispense: 'Quantity dispensed',
    adjustment: 'Adjustment (+/−)',
  }
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit(async (v) => {
        setError(null)
        try {
          const r = await api.post<{ item: InventoryItem; alerts: Alert[] }>(`/api/inventory/${item.id}/movements`, {
            movement_type: v.movement_type,
            quantity: v.quantity,
            reason: v.reason || null,
            idempotency_key: key,
            expected_version: item.version,
          })
          setResult(r)
          onDone()
        } catch (err) {
          setError(err instanceof ApiError ? err.message : 'Failed')
        }
      })}
    >
      <p className="text-sm text-slate-600">
        Recorded now: <strong>{item.quantity.toLocaleString()} {item.unit}s</strong> (minimum {item.min_threshold}) at {item.facility_name}.
      </p>
      <Field label="Type of update">
        {(id) => (
          <Select id={id} {...register('movement_type')}>
            <option value="count">Physical count (set quantity)</option>
            <option value="receipt">Delivery received</option>
            <option value="dispense">Dispensed / issued</option>
            <option value="adjustment">Adjustment (damage, expiry, correction)</option>
          </Select>
        )}
      </Field>
      <Field label={`${labels[type as keyof typeof labels]} (${item.unit}s)`} error={formState.errors.quantity?.message}>
        {(id) => <Input id={id} type="number" inputMode="numeric" {...register('quantity')} />}
      </Field>
      <Field label={type === 'adjustment' ? 'Reason (required)' : 'Note (optional)'}>
        {(id) => <Textarea id={id} {...register('reason')} placeholder={type === 'receipt' ? 'e.g. delivery note number' : ''} />}
      </Field>
      {error && <Notice tone="danger">{error}</Notice>}
      <Button type="submit" loading={formState.isSubmitting}>
        Record update
      </Button>
    </form>
  )
}
