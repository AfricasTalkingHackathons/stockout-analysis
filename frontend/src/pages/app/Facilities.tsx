import { zodResolver } from '@hookform/resolvers/zod'
import { UserPlus } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { Pill } from '../../components/StatusBadge'
import { Button, Card, CardHeader, EmptyState, ErrorState, Field, Input, Modal, Notice, PageHeader, Pagination, Select, Spinner, Table, Td, Th } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { FACILITY_TYPES, formatDate, humanize } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { FacilityPrivate, Page, StaffMember } from '../../lib/types'
import { optionalPhone } from '../../lib/validation'
import { FilterSelect } from './common'

function statusTone(s: string) {
  return s === 'approved' ? 'green' : s === 'pending' ? 'amber' : 'red'
}

export function FacilitiesList() {
  const { can } = useAuth()
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? ''
  const [page, setPage] = useState(1)
  const [action, setAction] = useState<{ f: FacilityPrivate; kind: 'approve' | 'suspend' | 'reject' } | null>(null)
  const list = useAsync(() => api.get<Page<FacilityPrivate>>('/api/manage/facilities', { status, page, page_size: 25 }), [status, page])
  return (
    <div>
      <PageHeader
        title="Facilities"
        description={can('facility.approve') ? 'Approve registrations before their stock appears publicly. Suspended facilities are hidden from search and cannot submit SMS updates.' : 'Your facility profile and staff.'}
      />
      {can('facility.approve') && (
        <Card className="mb-4 p-4">
          <FilterSelect label="Status" value={status} onChange={(v) => (setParams(v ? { status: v } : {}), setPage(1))}>
            <option value="">All</option>
            <option value="pending">Pending approval</option>
            <option value="approved">Approved</option>
            <option value="suspended">Suspended</option>
            <option value="rejected">Rejected</option>
          </FilterSelect>
        </Card>
      )}
      <Card>
        {list.loading && !list.data && <Spinner />}
        <ErrorState error={list.error} onRetry={list.reload} />
        {list.data?.items.length === 0 && <EmptyState title="No facilities" />}
        {!!list.data?.items.length && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>Facility</Th>
                <Th>Location</Th>
                <Th>Licence</Th>
                <Th>Status</Th>
                <Th>Registered</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((f) => (
                <tr key={f.id}>
                  <Td>
                    <Link to={`/app/facilities/${f.id}`} className="font-medium text-ink hover:text-brand-700 hover:underline">
                      {f.name}
                    </Link>
                    <span className="block text-xs text-slate-500">
                      {f.code} · {FACILITY_TYPES[f.facility_type]}
                      {f.is_demo && ' · demo'}
                    </span>
                  </Td>
                  <Td className="text-xs">{[f.location?.name, f.county.name].filter(Boolean).join(', ')}</Td>
                  <Td className="text-xs">{f.license_number ?? 'n/a'}</Td>
                  <Td>
                    <Pill tone={statusTone(f.status)}>{humanize(f.status)}</Pill>
                    {f.status_reason && <span className="mt-1 block text-xs text-slate-500">{f.status_reason}</span>}
                  </Td>
                  <Td className="text-xs">{formatDate(f.created_at)}</Td>
                  <Td>
                    {can('facility.approve') && (
                      <div className="flex flex-wrap gap-2">
                        {f.status !== 'approved' && (
                          <Button size="sm" onClick={() => setAction({ f, kind: 'approve' })}>
                            Approve
                          </Button>
                        )}
                        {f.status === 'approved' && (
                          <Button size="sm" variant="outline" onClick={() => setAction({ f, kind: 'suspend' })}>
                            Suspend
                          </Button>
                        )}
                        {f.status === 'pending' && (
                          <Button size="sm" variant="ghost" onClick={() => setAction({ f, kind: 'reject' })}>
                            Reject
                          </Button>
                        )}
                      </div>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && <Pagination page={page} pageSize={25} total={list.data.total} onPage={setPage} />}
      </Card>
      <Modal open={!!action} title={action ? `${humanize(action.kind)} ${action.f.name}` : ''} onClose={() => setAction(null)}>
        {action && (
          <StatusAction
            facility={action.f}
            kind={action.kind}
            onDone={() => {
              setAction(null)
              list.reload()
            }}
          />
        )}
      </Modal>
    </div>
  )
}

function StatusAction({ facility, kind, onDone }: { facility: FacilityPrivate; kind: 'approve' | 'suspend' | 'reject'; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        try {
          await api.post(`/api/admin/facilities/${facility.id}/${kind}`, { reason: reason || null })
          onDone()
        } catch (err) {
          setError(err instanceof ApiError ? err.message : 'Failed')
        } finally {
          setBusy(false)
        }
      }}
    >
      {kind === 'approve' ? (
        <Notice tone="info">
          Approving makes this facility a trusted source: its stock reports will appear in public search. Confirm you have checked its licence
          ({facility.license_number ?? 'not provided'}) and contact details.
        </Notice>
      ) : (
        <Notice tone="warning">{kind === 'suspend' ? 'The facility will disappear from public search and SMS stock updates will be refused.' : 'The registration will be rejected.'}</Notice>
      )}
      <Field label={kind === 'approve' ? 'Note (optional)' : 'Reason (required)'}>{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
      {error && <Notice tone="danger">{error}</Notice>}
      <Button type="submit" variant={kind === 'approve' ? 'primary' : 'danger'} loading={busy}>
        {humanize(kind)}
      </Button>
    </form>
  )
}

const staffSchema = z.object({
  full_name: z.string().trim().min(3, 'Enter a name'),
  email: z.email('Enter a valid email'),
  phone: optionalPhone,
  sms_phone: optionalPhone,
  role: z.enum(['facility_staff', 'facility_admin']),
  can_update_stock: z.boolean(),
  password: z.string().min(10, 'At least 10 characters'),
})

export function FacilityManage() {
  const { id } = useParams()
  const { user, can } = useAuth()
  const f = useAsync(() => api.get<FacilityPrivate>(`/api/manage/facilities/${id}`), [id])
  const staff = useAsync(() => api.get<StaffMember[]>(`/api/manage/facilities/${id}/staff`), [id])
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const isFacAdmin = user?.role === 'system_admin' || user?.memberships.some((m) => m.facility_id === id && m.role === 'facility_admin')

  const patchStaff = async (m: StaffMember, body: Partial<StaffMember>) => {
    try {
      await api.patch(`/api/manage/facilities/${id}/staff/${m.id}`, body)
      staff.reload()
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : 'Failed')
    }
  }

  return (
    <div>
      <Link to="/app/facilities" className="text-sm text-brand-700 hover:underline">
        ← Facilities
      </Link>
      {f.loading && !f.data && <Spinner />}
      <ErrorState error={f.error} />
      {f.data && (
        <>
          <PageHeader title={f.data.name} description={`${f.data.code} · ${FACILITY_TYPES[f.data.facility_type]} · ${f.data.county.name}`} actions={<Pill tone={statusTone(f.data.status)}>{humanize(f.data.status)}</Pill>} />
          {isFacAdmin && can('facility.manage') && <ProfileForm facility={f.data} onSaved={f.reload} />}
          <Card className="mt-6">
            <CardHeader
              title="Staff and permissions"
              subtitle="The SMS number is the only number allowed to send STOCK commands for this facility."
              action={
                isFacAdmin && can('staff.manage') ? (
                  <Button size="sm" onClick={() => setAdding(true)}>
                    <UserPlus className="h-4 w-4" aria-hidden /> Add staff
                  </Button>
                ) : null
              }
            />
            {msg && (
              <div className="px-5 pt-3">
                <Notice tone="danger">{msg}</Notice>
              </div>
            )}
            {staff.data && (
              <Table>
                <thead className="bg-slate-50">
                  <tr>
                    <Th>Name</Th>
                    <Th>Role</Th>
                    <Th>SMS stock number</Th>
                    <Th>Can update stock</Th>
                    <Th>Receives alerts</Th>
                    <Th>Active</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {staff.data.map((m) => (
                    <tr key={m.id}>
                      <Td>
                        <span className="font-medium text-ink">{m.full_name}</span>
                        <span className="block text-xs text-slate-500">{m.email}</span>
                      </Td>
                      <Td>
                        {isFacAdmin && can('staff.manage') ? (
                          <Select value={m.role} onChange={(e) => patchStaff(m, { role: e.target.value })} aria-label={`Role for ${m.full_name}`}>
                            <option value="facility_staff">Staff</option>
                            <option value="facility_admin">Administrator</option>
                          </Select>
                        ) : (
                          humanize(m.role)
                        )}
                      </Td>
                      <Td className="text-xs">{m.sms_phone ?? 'n/a'}</Td>
                      {(['can_update_stock', 'receive_alerts', 'is_active'] as const).map((k) => (
                        <Td key={k}>
                          <input
                            type="checkbox"
                            className="h-4 w-4"
                            checked={m[k]}
                            disabled={!(isFacAdmin && can('staff.manage'))}
                            onChange={(e) => patchStaff(m, { [k]: e.target.checked })}
                            aria-label={`${humanize(k)} for ${m.full_name}`}
                          />
                        </Td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
          <Modal open={adding} title="Add staff member" onClose={() => setAdding(false)}>
            <AddStaffForm
              facilityId={f.data.id}
              onDone={() => {
                setAdding(false)
                staff.reload()
              }}
            />
          </Modal>
        </>
      )}
    </div>
  )
}

function ProfileForm({ facility, onSaved }: { facility: FacilityPrivate; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: facility.name,
    address: facility.address ?? '',
    phone: facility.phone ?? '',
    latitude: facility.latitude?.toString() ?? '',
    longitude: facility.longitude?.toString() ?? '',
    public_show_quantity: facility.public_show_quantity,
  })
  const [msg, setMsg] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  return (
    <Card>
      <CardHeader title="Facility profile" subtitle="Shown to the public once the facility is approved." />
      <form
        className="grid gap-4 p-5 md:grid-cols-3"
        onSubmit={async (e) => {
          e.preventDefault()
          try {
            await api.patch(`/api/manage/facilities/${facility.id}`, {
              name: form.name,
              address: form.address || null,
              phone: form.phone || null,
              latitude: form.latitude ? Number(form.latitude) : null,
              longitude: form.longitude ? Number(form.longitude) : null,
              public_show_quantity: form.public_show_quantity,
            })
            setMsg({ tone: 'success', text: 'Saved' })
            onSaved()
          } catch (err) {
            setMsg({ tone: 'danger', text: err instanceof ApiError ? (err.details?.map((d) => d.message).join('; ') || err.message) : 'Failed' })
          }
        }}
      >
        <Field label="Name">{(id) => <Input id={id} value={form.name} onChange={set('name')} />}</Field>
        <Field label="Address / landmark">{(id) => <Input id={id} value={form.address} onChange={set('address')} />}</Field>
        <Field label="Public phone">{(id) => <Input id={id} value={form.phone} onChange={set('phone')} inputMode="tel" />}</Field>
        <Field label="Latitude" hint="Used for distance sorting and maps">
          {(id, d) => <Input id={id} aria-describedby={d} value={form.latitude} onChange={set('latitude')} inputMode="decimal" />}
        </Field>
        <Field label="Longitude">{(id) => <Input id={id} value={form.longitude} onChange={set('longitude')} inputMode="decimal" />}</Field>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" className="h-4 w-4" checked={form.public_show_quantity} onChange={set('public_show_quantity')} />
          Show approximate quantities publicly
        </label>
        <div className="flex items-center gap-3 md:col-span-3">
          <Button type="submit" variant="secondary">
            Save profile
          </Button>
          {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
        </div>
      </form>
    </Card>
  )
}

function AddStaffForm({ facilityId, onDone }: { facilityId: string; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof staffSchema>, unknown, z.output<typeof staffSchema>>({
    resolver: zodResolver(staffSchema),
    defaultValues: { role: 'facility_staff', can_update_stock: true, phone: '', sms_phone: '' },
  })
  const e = formState.errors
  return (
    <form
      noValidate
      className="space-y-3"
      onSubmit={handleSubmit(async (v) => {
        setError(null)
        try {
          await api.post(`/api/manage/facilities/${facilityId}/staff`, { ...v, phone: v.phone || null, sms_phone: v.sms_phone || null })
          onDone()
        } catch (err) {
          setError(err instanceof ApiError ? err.message : 'Failed')
        }
      })}
    >
      <Field label="Full name" error={e.full_name?.message}>{(id) => <Input id={id} {...register('full_name')} />}</Field>
      <Field label="Email" error={e.email?.message}>{(id) => <Input id={id} type="email" {...register('email')} />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Mobile" error={e.phone?.message}>{(id) => <Input id={id} inputMode="tel" {...register('phone')} />}</Field>
        <Field label="SMS stock-update number" error={e.sms_phone?.message}>{(id) => <Input id={id} inputMode="tel" {...register('sms_phone')} />}</Field>
      </div>
      <Field label="Role">
        {(id) => (
          <Select id={id} {...register('role')}>
            <option value="facility_staff">Staff</option>
            <option value="facility_admin">Administrator</option>
          </Select>
        )}
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="h-4 w-4" {...register('can_update_stock')} /> Can update stock
      </label>
      <Field label="Temporary password" error={e.password?.message} hint="Share securely; ask them to change it.">
        {(id, d) => <Input id={id} type="password" aria-describedby={d} {...register('password')} />}
      </Field>
      {error && <Notice tone="danger">{error}</Notice>}
      <Button type="submit" loading={formState.isSubmitting}>
        Add staff member
      </Button>
    </form>
  )
}
