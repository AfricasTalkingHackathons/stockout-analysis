import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { Button, Card, Field, Input, Notice, Select } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { FACILITY_TYPES } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { County, Location } from '../../lib/types'
import { optionalPhone } from '../../lib/validation'

const schema = z
  .object({
    name: z.string().trim().min(3, 'Enter the facility name'),
    facility_type: z.enum(['pharmacy', 'clinic', 'health_centre', 'dispensary', 'hospital']),
    county_id: z.string().min(1, 'Choose a county'),
    location_id: z.string().optional(),
    address: z.string().max(255).optional(),
    phone: optionalPhone,
    license_number: z.string().max(60).optional(),
    admin_full_name: z.string().trim().min(3, 'Enter your full name'),
    admin_email: z.email('Enter a valid email'),
    admin_phone: optionalPhone,
    admin_password: z.string().min(10, 'Use at least 10 characters'),
    confirm: z.string(),
    accept_terms: z.boolean().refine((v) => v, 'You must confirm before registering'),
  })
  .refine((v) => v.admin_password === v.confirm, { path: ['confirm'], message: 'Passwords do not match' })

type In = z.input<typeof schema>
type Out = z.output<typeof schema>

export default function Register() {
  const [done, setDone] = useState<{ code: string; message: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const counties = useAsync(() => api.get<County[]>('/api/locations/counties'), [])
  const { register, handleSubmit, watch, formState } = useForm<In, unknown, Out>({
    resolver: zodResolver(schema),
    defaultValues: { facility_type: 'pharmacy', accept_terms: false, phone: '', admin_phone: '' },
  })
  const countyId = watch('county_id')
  const locations = useAsync(() => (countyId ? api.get<Location[]>('/api/locations', { county_id: countyId }) : Promise.resolve([])), [countyId])
  const err = formState.errors

  if (done)
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        <Notice tone="success" title={`Registration received (${done.code})`}>
          {done.message}
        </Notice>
        <Link to="/login" className="mt-4 inline-block text-brand-700 underline">
          Sign in to set up inventory
        </Link>
      </div>
    )

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Register a facility</h1>
      <p className="mt-1 text-sm text-slate-600">
        A system administrator reviews every registration. Your stock is shown publicly only after approval.
      </p>
      <form
        noValidate
        onSubmit={handleSubmit(async (v) => {
          setError(null)
          try {
            const r = await api.post<{ code: string; message: string }>('/api/facilities/register', {
              name: v.name,
              facility_type: v.facility_type,
              county_id: Number(v.county_id),
              location_id: v.location_id ? Number(v.location_id) : null,
              address: v.address || null,
              phone: v.phone || null,
              license_number: v.license_number || null,
              admin_full_name: v.admin_full_name,
              admin_email: v.admin_email,
              admin_phone: v.admin_phone || null,
              admin_password: v.admin_password,
              accept_terms: true,
            })
            setDone(r)
          } catch (e) {
            setError(e instanceof ApiError ? (e.details?.map((d) => `${d.field}: ${d.message}`).join('; ') || e.message) : 'Registration failed')
          }
        })}
        className="mt-6 space-y-6"
      >
        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">Facility</h2>
          <Field label="Facility name" required error={err.name?.message}>
            {(id) => <Input id={id} aria-invalid={!!err.name} {...register('name')} />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Type" required>
              {(id) => (
                <Select id={id} {...register('facility_type')}>
                  {Object.entries(FACILITY_TYPES).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Licence / registration number" hint="e.g. PPB or KMPDC number, if applicable">
              {(id, d) => <Input id={id} aria-describedby={d} {...register('license_number')} />}
            </Field>
            <Field label="County" required error={err.county_id?.message}>
              {(id) => (
                <Select id={id} aria-invalid={!!err.county_id} {...register('county_id')}>
                  <option value="">Choose…</option>
                  {counties.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Town / area">
              {(id) => (
                <Select id={id} disabled={!countyId} {...register('location_id')}>
                  <option value="">Not listed</option>
                  {locations.data?.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Street address / landmark">
              {(id) => <Input id={id} {...register('address')} />}
            </Field>
            <Field label="Public phone number" error={err.phone?.message}>
              {(id) => <Input id={id} inputMode="tel" aria-invalid={!!err.phone} {...register('phone')} />}
            </Field>
          </div>
        </Card>
        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">Facility administrator account</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name" required error={err.admin_full_name?.message}>
              {(id) => <Input id={id} autoComplete="name" aria-invalid={!!err.admin_full_name} {...register('admin_full_name')} />}
            </Field>
            <Field label="Email" required error={err.admin_email?.message}>
              {(id) => <Input id={id} type="email" autoComplete="email" aria-invalid={!!err.admin_email} {...register('admin_email')} />}
            </Field>
            <Field label="Mobile (for alerts and SMS stock updates)" error={err.admin_phone?.message}>
              {(id) => <Input id={id} inputMode="tel" aria-invalid={!!err.admin_phone} {...register('admin_phone')} />}
            </Field>
            <div />
            <Field label="Password" required error={err.admin_password?.message}>
              {(id) => <Input id={id} type="password" autoComplete="new-password" aria-invalid={!!err.admin_password} {...register('admin_password')} />}
            </Field>
            <Field label="Confirm password" required error={err.confirm?.message}>
              {(id) => <Input id={id} type="password" autoComplete="new-password" aria-invalid={!!err.confirm} {...register('confirm')} />}
            </Field>
          </div>
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input type="checkbox" className="mt-0.5 h-4 w-4" {...register('accept_terms')} />
            <span>
              I am authorised to register this facility and will report stock accurately. I understand availability shown to the public must
              reflect actual recorded stock.
            </span>
          </label>
          {err.accept_terms && <p className="text-sm text-red-700">{err.accept_terms.message}</p>}
        </Card>
        {error && <Notice tone="danger">{error}</Notice>}
        <Button type="submit" size="lg" loading={formState.isSubmitting}>
          Submit registration
        </Button>
      </form>
    </div>
  )
}
