import { zodResolver } from '@hookform/resolvers/zod'
import { Bell, CalendarClock, MapPin, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { MedicinePicker } from '../../components/MedicinePicker'
import { StatusBadge } from '../../components/StatusBadge'
import { Button, Card, EmptyState, ErrorState, Field, Input, Notice, Select, Spinner } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { formatDate, timeAgo } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { County, Medicine, Page, PickupSchedule, SearchResponse, SearchResult } from '../../lib/types'
import { phoneSchema } from '../../lib/validation'

const schema = z.object({
  phone: phoneSchema,
  next_pickup_on: z.string().min(1, 'Choose your next collection date'),
  interval_days: z.coerce.number<string>().refine((n) => [14, 28, 30, 60, 90].includes(Number(n)), 'Choose how often you collect'),
  remind_days_before: z.coerce.number<string>().refine((n) => [1, 2, 3, 7].includes(Number(n))),
  preferred_facility_id: z.string().optional(),
  consent: z.boolean().refine((v) => v, 'Confirm you agree to receive reminder SMS'),
})
function isoToday() {
  const d = new Date()
  const off = d.getTimezoneOffset()
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10)
}

export default function Refill() {
  const [params, setParams] = useSearchParams()
  const medicineId = params.get('medicine')
  const countyId = params.get('county') ? Number(params.get('county')) : null
  const [medicine, setMedicine] = useState<Medicine | null>(null)
  const [saved, setSaved] = useState<PickupSchedule | null>(null)
  const [lookupPhone, setLookupPhone] = useState('')
  const [lookedUp, setLookedUp] = useState<PickupSchedule[] | null>(null)

  const counties = useAsync(() => api.get<County[]>('/api/locations/counties'), [])
  const longTerm = useAsync(() => api.get<Page<Medicine>>('/api/medicines', { long_term: true, page_size: 50 }), [])

  useEffect(() => {
    if (medicineId && medicine?.id !== medicineId) {
      api.get<Medicine>(`/api/medicines/${medicineId}`).then(setMedicine).catch(() => setMedicine(null))
    }
    if (!medicineId) setMedicine(null)
  }, [medicineId])

  const search = useAsync(
    () =>
      medicineId && countyId
        ? api.get<SearchResponse>('/api/availability/search', { medicine_id: medicineId, county_id: countyId })
        : Promise.resolve(null),
    [medicineId, countyId],
  )

  const setMed = (m: Medicine | null) => {
    setMedicine(m)
    const next = new URLSearchParams(params)
    if (m) next.set('medicine', m.id)
    else next.delete('medicine')
    setParams(next, { replace: false })
    setSaved(null)
  }

  const setCounty = (id: string) => {
    const next = new URLSearchParams(params)
    if (id) next.set('county', id)
    else next.delete('county')
    setParams(next, { replace: false })
    setSaved(null)
  }

  const data = search.data
  const usable = useMemo(() => (data?.results ?? []).filter((r) => r.status === 'available' || r.status === 'low'), [data])
  const others = useMemo(
    () => (data?.results ?? []).filter((r) => r.status !== 'available' && r.status !== 'low' && r.status !== 'unknown'),
    [data],
  )

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <p className="text-sm font-semibold text-brand-700">Ongoing treatment</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-tight">Find a facility for your next collection, and get a reminder</h1>
      <p className="mt-3 max-w-3xl text-slate-700">
        If the clinic you usually visit has recently reported this medicine low or out of stock, check another participating
        facility <em>before</em> you travel. We do not ask for a diagnosis. Reminder SMS never names the medicine.
      </p>
      <div className="mt-4">
        <Notice tone="warning" title="This is not medical advice">
          Do not skip, split or reduce your dose while you wait. If your usual site has no recent available report, look for
          another participating facility and ask a qualified health worker. Stock is not reserved and is not transferred
          between facilities automatically.
        </Notice>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_280px]">
        <Card className="p-5">
          <h2 className="font-semibold">1. Choose the medicine you collect</h2>
          <p className="mt-1 text-sm text-slate-600">Search by generic or brand name. Common repeating treatments are listed below.</p>
          <div className="mt-4">
            <MedicinePicker value={medicine} onChange={setMed} placeholder="e.g. metformin, TLD, insulin" />
          </div>
          <ul className="mt-3 flex flex-wrap gap-2">
            {(longTerm.data?.items ?? []).slice(0, 12).map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => setMed(m)}
                  className={`rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset ${
                    medicineId === m.id ? 'bg-brand-700 text-white ring-brand-700' : 'bg-white text-slate-700 ring-slate-300 hover:bg-slate-50'
                  }`}
                >
                  {m.generic_name} {m.strength}
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Privacy</h2>
          <ul className="mt-3 space-y-2 text-sm text-slate-600">
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
              No HIV, TB or other condition is stored. You only tell us a medicine and a collection date.
            </li>
            <li className="flex gap-2">
              <Bell className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
              SMS says “scheduled medicine pickup” plus the date and place, not the medicine name.
            </li>
            <li className="flex gap-2">
              <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
              Reply STOP to any message, or use the unsubscribe page, to end reminders.
            </li>
          </ul>
        </Card>
      </div>

      <Card className="mt-6 p-5">
        <h2 className="font-semibold">2. Where do you collect?</h2>
        <div className="mt-3 max-w-sm">
          <Field label="County">
            {(id) => (
              <Select id={id} value={countyId ?? ''} onChange={(e) => setCounty(e.target.value)}>
                <option value="">Choose a county</option>
                {counties.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.participating_facilities ? ` (${c.participating_facilities})` : ''}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
      </Card>

      {medicineId && countyId && (
        <div className="mt-6">
          {search.loading && <Spinner label="Checking participating facilities…" />}
          <ErrorState error={search.error} onRetry={search.reload} />
          {data && !search.loading && (
            <>
              <h2 className="font-semibold">3. Facilities with a recent available or low-stock report</h2>
              <p className="mt-1 text-sm text-slate-600">{data.notice}</p>
              {usable.length === 0 ? (
                <EmptyState title="No recent “available” or “low stock” report in this county">
                  {data.alternatives?.other_areas?.length ? (
                    <p className="mt-2 text-sm">
                      Recently reported elsewhere:{' '}
                      {data.alternatives.other_areas.map((a) => (
                        <button key={a.county_id} className="mr-2 text-brand-700 underline" onClick={() => setCounty(String(a.county_id))}>
                          {a.county} ({a.facilities})
                        </button>
                      ))}
                    </p>
                  ) : (
                    <p className="mt-2 text-sm">Ask a qualified health worker. Do not change how you take your medicine.</p>
                  )}
                </EmptyState>
              ) : (
                <ul className="mt-4 space-y-3">
                  {usable.map((r) => (
                    <ResultCard key={r.facility.id} r={r} />
                  ))}
                </ul>
              )}
              {others.length > 0 && (
                <details className="mt-4">
                  <summary className="cursor-pointer text-sm font-medium text-slate-700">
                    {others.length} participating {others.length === 1 ? 'facility' : 'facilities'} without a recent available report
                  </summary>
                  <ul className="mt-3 space-y-3">
                    {others.map((r) => (
                      <ResultCard key={r.facility.id} r={r} muted />
                    ))}
                  </ul>
                </details>
              )}
              {medicine && countyId && (
                <ReminderForm
                  medicine={medicine}
                  countyId={countyId}
                  options={(data.results ?? []).filter((r) => r.status !== 'unknown')}
                  onSaved={setSaved}
                />
              )}
            </>
          )}
        </div>
      )}

      {saved && (
        <div className="mt-6">
          <Notice tone="success" title="Reminder saved">
            {saved.message} Next collection {formatDate(saved.next_pickup_on)}. We will remind you {saved.remind_days_before}{' '}
            day{saved.remind_days_before === 1 ? '' : 's'} before.
            {saved.preferred_status?.status && saved.preferred_status.status !== 'available' && saved.alternatives.length > 0 && (
              <span> Other sites with a recent report: {saved.alternatives.map((a) => a.name).join(', ')}.</span>
            )}
          </Notice>
        </div>
      )}

      <Card className="mt-10 p-5">
        <h2 className="font-semibold">Already set a reminder?</h2>
        <p className="mt-1 text-sm text-slate-600">Enter the same mobile number to see active reminders (numbers are masked).</p>
        <form
          className="mt-3 flex flex-wrap items-end gap-3"
          onSubmit={async (e) => {
            e.preventDefault()
            const r = await api.post<{ items: PickupSchedule[] }>('/api/pickup-schedules/lookup', { phone: lookupPhone })
            setLookedUp(r.items)
          }}
        >
          <Field label="Mobile number">
            {(id) => <Input id={id} inputMode="tel" value={lookupPhone} onChange={(e) => setLookupPhone(e.target.value)} />}
          </Field>
          <Button type="submit">Look up</Button>
        </form>
        {lookedUp && (
          <ul className="mt-4 space-y-2 text-sm">
            {lookedUp.length === 0 && <li className="text-slate-600">No active reminders for this number.</li>}
            {lookedUp.map((s) => (
              <li key={s.id} className="rounded-lg border border-slate-200 p-3">
                {s.medicine.display_name} · {s.county.name} · next {formatDate(s.next_pickup_on)}
                {s.preferred_facility ? ` · ${s.preferred_facility.name}` : ''}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-slate-500">
          <Link to="/unsubscribe" className="text-brand-700 underline">
            Stop SMS alerts and reminders
          </Link>
        </p>
      </Card>
    </div>
  )
}

function ResultCard({ r, muted }: { r: SearchResult; muted?: boolean }) {
  return (
    <li className={`rounded-xl border p-4 ${muted ? 'border-slate-200 bg-slate-50' : 'border-slate-200 bg-white'}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link to={`/facilities/${r.facility.id}`} className="font-semibold text-ink hover:text-brand-700 hover:underline">
            {r.facility.name}
          </Link>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-slate-600">
            <MapPin className="h-3.5 w-3.5" aria-hidden />
            {r.facility.town}, {r.facility.county?.name}
          </p>
        </div>
        <StatusBadge status={r.status} />
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Last updated {timeAgo(r.last_updated_at)}
        {r.quantity != null && r.status !== 'stale' ? ` · About ${r.quantity} ${r.unit}s reported` : ''}
      </p>
      {r.facility.is_demo && <p className="mt-1 text-xs text-violet-800">Demo facility: no real phone number</p>}
    </li>
  )
}

function ReminderForm({
  medicine,
  countyId,
  options,
  onSaved,
}: {
  medicine: Medicine
  countyId: number
  options: SearchResult[]
  onSaved: (s: PickupSchedule) => void
}) {
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof schema>, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      next_pickup_on: isoToday(),
      interval_days: '30',
      remind_days_before: '3',
      consent: false,
    },
  })
  return (
    <Card className="mt-8 p-5">
      <h2 className="font-semibold">4. Remind me before collection day</h2>
      <p className="mt-1 text-sm text-slate-600">
        We will SMS you before the date you choose, then keep reminding on that interval. The message will not name the
        medicine.
      </p>
      <form
        className="mt-4 grid gap-4 md:grid-cols-2"
        noValidate
        onSubmit={handleSubmit(async (v) => {
          setError(null)
          try {
            const r = await api.post<PickupSchedule>('/api/pickup-schedules', {
              phone: v.phone,
              medicine_id: medicine.id,
              county_id: countyId,
              preferred_facility_id: v.preferred_facility_id || null,
              next_pickup_on: v.next_pickup_on,
              interval_days: Number(v.interval_days),
              remind_days_before: Number(v.remind_days_before),
              consent: true,
            })
            onSaved(r)
          } catch (e) {
            setError(e instanceof ApiError ? e.message : 'Could not save the reminder')
          }
        })}
      >
        <Field label="Mobile number" error={formState.errors.phone?.message}>
          {(id) => <Input id={id} inputMode="tel" aria-invalid={!!formState.errors.phone} {...register('phone')} />}
        </Field>
        <Field label="Next collection date" error={formState.errors.next_pickup_on?.message}>
          {(id) => <Input id={id} type="date" min={isoToday()} {...register('next_pickup_on')} />}
        </Field>
        <Field label="How often do you collect?">
          {(id) => (
            <Select id={id} {...register('interval_days')}>
              <option value={14}>Every 14 days</option>
              <option value={28}>Every 28 days</option>
              <option value={30}>Every 30 days (monthly)</option>
              <option value={60}>Every 60 days</option>
              <option value={90}>Every 90 days</option>
            </Select>
          )}
        </Field>
        <Field label="Remind me">
          {(id) => (
            <Select id={id} {...register('remind_days_before')}>
              <option value={1}>1 day before</option>
              <option value={2}>2 days before</option>
              <option value={3}>3 days before</option>
              <option value={7}>7 days before</option>
            </Select>
          )}
        </Field>
        <Field label="Usual facility (optional)" hint="If this site is low or out, the reminder will list other participating facilities.">
          {(id) => (
            <Select id={id} {...register('preferred_facility_id')}>
              <option value="">Any participating facility in this county</option>
              {options.map((r) => (
                <option key={r.facility.id} value={r.facility.id}>
                  {r.facility.name} ({r.status_label})
                </option>
              ))}
            </Select>
          )}
        </Field>
        <label className="flex items-start gap-2 text-sm text-slate-700 md:col-span-2">
          <input type="checkbox" className="mt-1 h-4 w-4" {...register('consent')} />
          I agree to receive SMS pickup reminders on this number. I understand they do not reserve stock, are not a clinic
          appointment, and are not medical advice. Reply STOP to opt out.
        </label>
        {formState.errors.consent && <p className="text-sm text-red-700 md:col-span-2">{formState.errors.consent.message}</p>}
        {error && <Notice tone="danger">{error}</Notice>}
        <div className="md:col-span-2">
          <Button type="submit" loading={formState.isSubmitting}>
            Save pickup reminder
          </Button>
        </div>
      </form>
    </Card>
  )
}
