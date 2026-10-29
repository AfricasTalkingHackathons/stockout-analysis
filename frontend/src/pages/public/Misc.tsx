import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { MedicinePicker } from '../../components/MedicinePicker'
import { ReportForm } from '../../components/PublicForms'
import { Button, Card, Field, Input, Notice, Select } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { useAsync } from '../../lib/hooks'
import type { County, Medicine, Page, PublicFacility } from '../../lib/types'
import { phoneSchema } from '../../lib/validation'

const unsubSchema = z.object({ phone: phoneSchema })

export function Unsubscribe() {
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof unsubSchema>, unknown, z.output<typeof unsubSchema>>({
    resolver: zodResolver(unsubSchema),
  })
  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <Card className="p-6">
        <h1 className="text-xl font-semibold">Stop SMS alerts and pickup reminders</h1>
        <p className="mt-1 text-sm text-slate-600">You can also reply STOP to any message. This stops availability alerts and collection reminders for this number.</p>
        {msg ? (
          <div className="mt-4">
            <Notice tone="success">{msg}</Notice>
          </div>
        ) : (
          <form
            className="mt-5 space-y-4"
            noValidate
            onSubmit={handleSubmit(async (v) => {
              setError(null)
              try {
                const r = await api.post<{ message: string }>('/api/notifications/unsubscribe', { phone: v.phone })
                setMsg(r.message)
              } catch (e) {
                setError(e instanceof ApiError ? e.message : 'Failed')
              }
            })}
          >
            <Field label="Mobile number" error={formState.errors.phone?.message}>
              {(id) => <Input id={id} inputMode="tel" aria-invalid={!!formState.errors.phone} {...register('phone')} />}
            </Field>
            {error && <Notice tone="danger">{error}</Notice>}
            <Button type="submit" loading={formState.isSubmitting}>
              Stop all alerts
            </Button>
          </form>
        )}
      </Card>
    </div>
  )
}

export function ReportPage() {
  const [med, setMed] = useState<Medicine | null>(null)
  const [countyId, setCountyId] = useState('')
  const [facilityId, setFacilityId] = useState('')
  const counties = useAsync(() => api.get<County[]>('/api/locations/counties'), [])
  const facilities = useAsync(
    () => (countyId ? api.get<Page<PublicFacility>>('/api/facilities', { county_id: countyId, page_size: 100 }) : Promise.resolve(null)),
    [countyId],
  )
  const facility = facilities.data?.items.find((f) => f.id === facilityId)
  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Report unavailable medicine</h1>
      <p className="mt-1 text-sm text-slate-600">
        Your report helps facilities and administrators notice shortages sooner. It is shown as unverified until confirmed.
      </p>
      <Card className="mt-6 space-y-4 p-5">
        <MedicinePicker value={med} onChange={setMed} />
        <Field label="County">
          {(id) => (
            <Select id={id} value={countyId} onChange={(e) => (setCountyId(e.target.value), setFacilityId(''))}>
              <option value="">Choose…</option>
              {counties.data
                ?.filter((c) => c.participating_facilities > 0)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </Select>
          )}
        </Field>
        <Field label="Facility">
          {(id) => (
            <Select id={id} value={facilityId} disabled={!countyId} onChange={(e) => setFacilityId(e.target.value)}>
              <option value="">Choose…</option>
              {facilities.data?.items.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {med && facility && (
          <div className="border-t border-slate-100 pt-4">
            <ReportForm key={facility.id + med.id} facilityId={facility.id} medicineId={med.id} facilityName={facility.name} medicineName={med.display_name} />
          </div>
        )}
      </Card>
    </div>
  )
}

export function NotFound() {
  return (
    <div className="mx-auto max-w-md px-4 py-20 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="mt-4 inline-block text-brand-700 underline">
        Go to the home page
      </Link>
    </div>
  )
}
