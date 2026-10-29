import { ArrowLeft, CheckCircle2, Eye, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertStatusPill, Pill, SeverityBadge, StatusBadge } from '../../components/StatusBadge'
import { Button, Card, CardHeader, EmptyState, ErrorState, Field, Notice, PageHeader, Pagination, Select, Spinner, Table, Td, Textarea, Th } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { formatDateTime, humanize, timeAgo } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { Alert, Page } from '../../lib/types'
import { FilterSelect, useFacilityOptions, useMedicines } from './common'

export const ALERT_TYPES: Record<string, string> = {
  stockout: 'Stockout',
  low_stock: 'Low stock',
  early_warning: 'Early warning',
  stale_report: 'Stale report',
  expiring: 'Expiring stock',
  ripple: 'Ripple signal',
}

export function AlertsList({ ripple = false }: { ripple?: boolean }) {
  const [status, setStatus] = useState('active')
  const [type, setType] = useState(ripple ? 'ripple' : '')
  const [severity, setSeverity] = useState('')
  const [facilityId, setFacilityId] = useState('')
  const [medicineId, setMedicineId] = useState('')
  const [page, setPage] = useState(1)
  const facilities = useFacilityOptions()
  const medicines = useMedicines()
  const list = useAsync(
    () =>
      api.get<Page<Alert>>('/api/alerts', {
        status,
        alert_type: ripple ? 'ripple' : type,
        severity,
        facility_id: ripple ? '' : facilityId,
        medicine_id: medicineId,
        page,
        page_size: 25,
      }),
    [status, type, severity, facilityId, medicineId, page, ripple],
  )
  const base = ripple ? '/app/ripple' : '/app/alerts'

  return (
    <div>
      <PageHeader
        title={ripple ? 'Ripple monitoring' : 'Stockout alerts'}
        description={
          ripple
            ? 'Potential local shortage signals: several facilities in one county reporting the same medicine low or out within the configured window. Signals are prompts to investigate, not confirmed shortages.'
            : 'Generated automatically from inventory changes and scheduled checks. One open alert per event; repeat triggers update the evidence instead of duplicating.'
        }
      />
      <Card className="mb-4 p-4">
        <div className="flex flex-wrap gap-3">
          <FilterSelect label="Status" value={status} onChange={(v) => (setStatus(v), setPage(1))}>
            <option value="active">Active (open, acknowledged, investigating)</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="investigating">Investigating</option>
            <option value="resolved">Resolved</option>
            <option value="dismissed">Dismissed</option>
            <option value="">All</option>
          </FilterSelect>
          {!ripple && (
            <FilterSelect label="Type" value={type} onChange={(v) => (setType(v), setPage(1))}>
              <option value="">All types</option>
              {Object.entries(ALERT_TYPES)
                .filter(([k]) => k !== 'ripple')
                .map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
            </FilterSelect>
          )}
          <FilterSelect label="Severity" value={severity} onChange={(v) => (setSeverity(v), setPage(1))}>
            <option value="">Any</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </FilterSelect>
          {!ripple && (facilities.data?.length ?? 0) > 1 && (
            <FilterSelect label="Facility" value={facilityId} onChange={(v) => (setFacilityId(v), setPage(1))}>
              <option value="">All</option>
              {facilities.data?.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </FilterSelect>
          )}
          <FilterSelect label="Medicine" value={medicineId} onChange={(v) => (setMedicineId(v), setPage(1))}>
            <option value="">All</option>
            {medicines.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.generic_name} {m.strength}
              </option>
            ))}
          </FilterSelect>
        </div>
      </Card>
      <Card>
        {list.loading && !list.data && <Spinner />}
        <ErrorState error={list.error} onRetry={list.reload} />
        {list.data?.items.length === 0 && <EmptyState title={ripple ? 'No ripple signals for these filters' : 'No alerts for these filters'} />}
        {!!list.data?.items.length && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>Alert</Th>
                <Th>Severity</Th>
                <Th>Status</Th>
                <Th>{ripple ? 'Evidence' : 'Type'}</Th>
                <Th>Created</Th>
                <Th>Assigned</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((a) => (
                <tr key={a.id} className="hover:bg-slate-50/60">
                  <Td>
                    <Link to={`${a.alert_type === 'ripple' ? '/app/ripple' : base}/${a.id}`} className="font-medium text-ink hover:text-brand-700 hover:underline">
                      {a.title}
                    </Link>
                    {a.escalation_level > 0 && <Pill tone="red">Escalated</Pill>}
                  </Td>
                  <Td>
                    <SeverityBadge severity={a.severity} />
                  </Td>
                  <Td>
                    <AlertStatusPill status={a.status} />
                  </Td>
                  <Td className="text-xs">
                    {ripple
                      ? `${String(a.evidence.facilities_counted ?? '?')} facilities · score ${String(a.evidence.score ?? '?')}`
                      : ALERT_TYPES[a.alert_type] ?? a.alert_type}
                  </Td>
                  <Td className="whitespace-nowrap text-xs">{timeAgo(a.created_at)}</Td>
                  <Td className="text-xs">{a.assigned_to?.full_name ?? 'n/a'}</Td>
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

export function AlertDetail() {
  const { id } = useParams()
  const { can } = useAuth()
  const a = useAsync(() => api.get<Alert>(`/api/alerts/${id}`), [id])
  const [notes, setNotes] = useState('')
  const [outcome, setOutcome] = useState<'resolved' | 'dismissed'>('resolved')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const alert = a.data
  const ripple = alert?.alert_type === 'ripple'
  const canManageRipple = can('ripple.manage')

  const act = async (action: string, body?: unknown) => {
    setBusy(action)
    setError(null)
    try {
      await api.post(`/api/alerts/${id}/${action}`, body)
      a.reload()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <Link to={ripple ? '/app/ripple' : '/app/alerts'} className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
        <ArrowLeft className="h-4 w-4" aria-hidden /> {ripple ? 'Ripple monitoring' : 'Alerts'}
      </Link>
      {a.loading && !alert && <Spinner />}
      <ErrorState error={a.error} onRetry={a.reload} />
      {alert && (
        <>
          <div className="mb-6 mt-3">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={alert.severity} />
              <AlertStatusPill status={alert.status} />
              <Pill>{ALERT_TYPES[alert.alert_type] ?? alert.alert_type}</Pill>
              {alert.escalation_level > 0 && <Pill tone="red">Escalated (level {alert.escalation_level})</Pill>}
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">{alert.title}</h1>
            <p className="mt-1 text-sm text-slate-600">
              Created {formatDateTime(alert.created_at)}
              {alert.facility && <> · {alert.facility.name}</>}
              {alert.county && <> · {alert.county.name} County</>}
            </p>
          </div>
          {ripple && (
            <div className="mb-6">
              <Notice tone="warning" title="Potential local shortage signal, not a confirmed shortage">
                Investigate supply with the facilities listed below. StockOut Alert does not transfer stock, place orders, or represent another
                facility's inventory as available without authorisation.
              </Notice>
            </div>
          )}
          <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
            <div className="space-y-6">
              {ripple && alert.ripple_evidence && <RippleEvidenceTable alert={alert} />}
              <Card>
                <CardHeader title="Triggering evidence" />
                <dl className="grid gap-x-6 gap-y-2 px-5 py-4 text-sm sm:grid-cols-2">
                  {Object.entries(alert.evidence)
                    .filter(([, v]) => typeof v !== 'object' || v === null)
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-3 border-b border-slate-100 py-1.5">
                        <dt className="text-slate-500">{humanize(k)}</dt>
                        <dd className="text-right font-medium text-ink">{String(v ?? 'n/a')}</dd>
                      </div>
                    ))}
                </dl>
                {Array.isArray(alert.evidence.stale_items) && (
                  <ul className="px-5 pb-4 text-sm">
                    {(alert.evidence.stale_items as { medicine: string; last_updated_at: string; inventory_id: string }[]).map((s) => (
                      <li key={s.inventory_id}>
                        <Link to={`/app/inventory/${s.inventory_id}`} className="text-brand-700 hover:underline">
                          {s.medicine}
                        </Link>{' '}
                        (last updated {timeAgo(s.last_updated_at)})
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
            <Card>
              <CardHeader title="Workflow" />
              <div className="space-y-4 p-5 text-sm">
                <ol className="space-y-2 text-slate-700">
                  <li>
                    <strong>Created:</strong> {formatDateTime(alert.created_at)}
                  </li>
                  <li>
                    <strong>Acknowledged:</strong> {formatDateTime(alert.acknowledged_at)}
                  </li>
                  <li>
                    <strong>Assigned to:</strong> {alert.assigned_to?.full_name ?? 'n/a'}
                  </li>
                  <li>
                    <strong>Last notification:</strong> {formatDateTime(alert.last_notified_at)}
                  </li>
                  <li>
                    <strong>Closed:</strong> {formatDateTime(alert.resolved_at)}
                  </li>
                </ol>
                {alert.resolution_notes && (
                  <div className="rounded-lg bg-slate-50 p-3">
                    <p className="text-xs font-semibold uppercase text-slate-500">Outcome</p>
                    <p className="mt-1 whitespace-pre-wrap">{alert.resolution_notes}</p>
                  </div>
                )}
                {error && <Notice tone="danger">{error}</Notice>}
                {can('alerts.manage') && !['resolved', 'dismissed'].includes(alert.status) && (
                  <div className="space-y-4 border-t border-slate-100 pt-4">
                    <div className="flex flex-wrap gap-2">
                      {alert.status === 'open' && (
                        <Button variant="secondary" loading={busy === 'acknowledge'} onClick={() => act('acknowledge')}>
                          <Eye className="h-4 w-4" aria-hidden /> Acknowledge
                        </Button>
                      )}
                      {(!ripple || canManageRipple) && ['open', 'acknowledged'].includes(alert.status) && (
                        <Button variant="outline" loading={busy === 'investigate'} onClick={() => act('investigate')}>
                          <Search className="h-4 w-4" aria-hidden /> Mark investigating
                        </Button>
                      )}
                    </div>
                    {(!ripple || canManageRipple) && (
                      <form
                        className="space-y-3"
                        onSubmit={(e) => {
                          e.preventDefault()
                          if (notes.trim().length < 3) return setError('Describe the outcome (at least 3 characters).')
                          act('resolve', { resolution_notes: notes.trim(), outcome })
                        }}
                      >
                        <Field label="Outcome">
                          {(fid) => (
                            <Select id={fid} value={outcome} onChange={(e) => setOutcome(e.target.value as 'resolved' | 'dismissed')}>
                              <option value="resolved">Resolved</option>
                              <option value="dismissed">Dismissed (not a real issue)</option>
                            </Select>
                          )}
                        </Field>
                        <Field label="Resolution / investigation notes">
                          {(fid) => <Textarea id={fid} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Emergency order placed with supplier; delivery expected Friday." />}
                        </Field>
                        <Button type="submit" loading={busy === 'resolve'}>
                          <CheckCircle2 className="h-4 w-4" aria-hidden /> Close alert
                        </Button>
                      </form>
                    )}
                    {ripple && !canManageRipple && <p className="text-xs text-slate-500">Only system administrators can investigate or close ripple signals.</p>}
                  </div>
                )}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

function RippleEvidenceTable({ alert }: { alert: Alert }) {
  const ev = alert.evidence as Record<string, number | string | boolean>
  return (
    <Card>
      <CardHeader
        title="Evidence behind this signal"
        subtitle={`Score ${ev.score} from ${ev.facilities_counted} facilities (needs ≥ ${ev.min_facilities} facilities and score ≥ ${ev.min_score}) within ${ev.window_hours} h. Each facility counts once; unverified reports are down-weighted; stale data is excluded.`}
      />
      <Table>
        <thead className="bg-slate-50">
          <tr>
            <Th>Facility</Th>
            <Th>Source</Th>
            <Th>Observed</Th>
            <Th>Verified</Th>
            <Th className="text-right">Weight</Th>
            <Th>Counted</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {alert.ripple_evidence!.map((e) => (
            <tr key={e.source_id} className={e.counted ? '' : 'text-slate-400'}>
              <Td className="font-medium">{e.facility_name}</Td>
              <Td className="text-xs">{e.source_type === 'inventory' ? 'Facility inventory' : 'Public report'}</Td>
              <Td>
                <StatusBadge status={e.observed_status} short />
                <span className="mt-1 block text-xs text-slate-500">{formatDateTime(e.observed_at)}</span>
              </Td>
              <Td>{e.verified ? <Pill tone="green">Verified</Pill> : <Pill tone="amber">Unverified</Pill>}</Td>
              <Td className="text-right tabular-nums">{e.weight.toFixed(2)}</Td>
              <Td>{e.counted ? 'Yes' : 'No (duplicate or superseded)'}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  )
}
