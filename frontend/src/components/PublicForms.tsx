import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError, api, newClientToken } from '../lib/api'
import { phoneSchema } from '../lib/validation'
import { Button, Field, Input, Notice, Select, Textarea } from './ui'

const smsSchema = z.object({ phone: phoneSchema })

export function SmsSummaryForm({ medicineId, countyId, facilityId }: { medicineId: string; countyId?: number | null; facilityId?: string }) {
  const [result, setResult] = useState<{ message: string; preview: string; simulated: boolean } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof smsSchema>, unknown, z.output<typeof smsSchema>>({
    resolver: zodResolver(smsSchema),
  })
  const onSubmit = async (v: z.output<typeof smsSchema>) => {
    setError(null)
    try {
      const r = await api.post<{ message: string; preview: string; simulated: boolean }>('/api/availability/sms-summary', {
        phone: v.phone,
        medicine_id: medicineId,
        county_id: countyId ?? null,
        facility_id: facilityId ?? null,
      })
      setResult(r)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not send')
    }
  }
  if (result)
    return (
      <div className="space-y-3">
        <Notice tone={result.simulated ? 'info' : 'success'} title={result.simulated ? 'Simulated SMS (demo)' : 'SMS sent to provider'}>
          {result.message}
        </Notice>
        <div className="rounded-lg bg-slate-900 p-3 font-mono text-xs leading-relaxed text-slate-100">{result.preview}</div>
      </div>
    )
  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3" noValidate>
      <Field label="Mobile number" error={formState.errors.phone?.message} hint="Used only to send this message. Standard SMS rules apply.">
        {(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!formState.errors.phone} inputMode="tel" placeholder="0712 345 678" {...register('phone')} />}
      </Field>
      {error && <Notice tone="danger">{error}</Notice>}
      <Button type="submit" loading={formState.isSubmitting} className="w-full">
        Send me an SMS summary
      </Button>
    </form>
  )
}

const subSchema = z.object({
  phone: phoneSchema,
  consent: z.boolean().refine((v) => v, 'Please confirm you agree to receive SMS alerts'),
})

export function SubscribeForm({ medicineId, countyId, countyName, medicineName }: { medicineId: string; countyId: number; countyName?: string; medicineName?: string }) {
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof subSchema>, unknown, z.output<typeof subSchema>>({
    resolver: zodResolver(subSchema),
    defaultValues: { consent: false, phone: '' },
  })
  if (done) return <Notice tone="success">{done}</Notice>
  return (
    <form
      onSubmit={handleSubmit(async (v) => {
        setError(null)
        try {
          const r = await api.post<{ message: string }>('/api/notifications/subscriptions', {
            phone: v.phone,
            medicine_id: medicineId,
            county_id: countyId,
            consent: true,
          })
          setDone(r.message)
        } catch (e) {
          setError(e instanceof ApiError ? e.message : 'Could not subscribe')
        }
      })}
      className="space-y-3"
      noValidate
    >
      <p className="text-sm text-slate-700">
        Get one SMS when a participating facility{countyName ? ` in ${countyName}` : ''} reports {medicineName ?? 'this medicine'} available.
      </p>
      <Field label="Mobile number" error={formState.errors.phone?.message}>
        {(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!formState.errors.phone} inputMode="tel" placeholder="0712 345 678" {...register('phone')} />}
      </Field>
      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-700" {...register('consent')} />
        <span>I agree to receive SMS availability alerts. I can stop them any time by replying STOP.</span>
      </label>
      {formState.errors.consent && <p className="text-sm text-red-700">{formState.errors.consent.message}</p>}
      {error && <Notice tone="danger">{error}</Notice>}
      <Button type="submit" variant="secondary" loading={formState.isSubmitting}>
        Notify me
      </Button>
    </form>
  )
}

const reportSchema = z.object({
  reported_status: z.enum(['out_of_stock', 'low', 'available']),
  comment: z.string().max(280, 'Keep it under 280 characters').optional(),
})

export function ReportForm({ facilityId, medicineId, facilityName, medicineName, onDone }: { facilityId: string; medicineId: string; facilityName: string; medicineName: string; onDone?: () => void }) {
  const token = useMemo(() => newClientToken(), [])
  const [ref, setRef] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<z.input<typeof reportSchema>, unknown, z.output<typeof reportSchema>>({
    resolver: zodResolver(reportSchema),
    defaultValues: { reported_status: 'out_of_stock' },
  })
  if (ref)
    return (
      <div className="space-y-3">
        <Notice tone="success" title={`Report received. Reference ${ref}`}>
          Thank you. It stays marked as unverified until the facility or an administrator confirms it.
        </Notice>
        {onDone && (
          <Button variant="outline" onClick={onDone}>
            Close
          </Button>
        )}
      </div>
    )
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit(async (v) => {
        setError(null)
        try {
          const r = await api.post<{ reference: string }>('/api/reports/stockout', {
            facility_id: facilityId,
            medicine_id: medicineId,
            reported_status: v.reported_status,
            comment: v.comment || null,
            client_token: token,
          })
          setRef(r.reference)
        } catch (e) {
          setError(e instanceof ApiError ? e.message : 'Could not submit')
        }
      })}
    >
      <p className="text-sm text-slate-700">
        <strong>{medicineName}</strong> at <strong>{facilityName}</strong>
      </p>
      <Field label="What did you find?">
        {(id) => (
          <Select id={id} {...register('reported_status')}>
            <option value="out_of_stock">Not available / out of stock</option>
            <option value="low">Only a little left</option>
            <option value="available">It was available</option>
          </Select>
        )}
      </Field>
      <Field label="Comment (optional)" error={formState.errors.comment?.message} hint="Please don't include personal or health details.">
        {(id, d) => <Textarea id={id} aria-describedby={d} {...register('comment')} />}
      </Field>
      {error && <Notice tone="danger">{error}</Notice>}
      <Button type="submit" loading={formState.isSubmitting}>
        Submit report
      </Button>
    </form>
  )
}
