import { AlertTriangle, Bell, Boxes, Building2, CheckCircle2, Clock, Radar, XCircle } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertStatusPill, SeverityBadge, StatusBadge } from '../../components/StatusBadge'
import { Card, CardHeader, EmptyState, ErrorState, Input, Notice, PageHeader, Spinner, Stat, Table, Td, Th } from '../../components/ui'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { formatDate, formatDateTime, humanize, timeAgo } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { Overview } from '../../lib/types'
import { FilterSelect, useCounties, useFacilityOptions, useMedicines } from './common'

const FacilityMap = lazy(() => import('../../components/FacilityMap'))

export default function Dashboard() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'system_admin'
  const [f, setF] = useState({ county_id: '', facility_id: '', medicine_id: '', status: '', severity: '', date_from: '', date_to: '' })
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }))
  const facilities = useFacilityOptions()
  const counties = useCounties()
  const medicines = useMedicines()
  const ov = useAsync(
    () =>
      api.get<Overview>(isAdmin ? '/api/admin/overview' : '/api/dashboard/overview', {
        ...f,
        date_from: f.date_from ? new Date(f.date_from).toISOString() : '',
        date_to: f.date_to ? new Date(f.date_to + 'T23:59:59').toISOString() : '',
      }),
    [JSON.stringify(f), isAdmin],
  )
  const d = ov.data
  const pending = user?.memberships.some((m) => m.facility_status === 'pending')

  return (
    <div>
      <PageHeader
        title={isAdmin ? 'Platform overview' : 'Facility dashboard'}
        description={d ? `All figures computed from the database at ${formatDateTime(d.generated_at)}. Records older than ${d.freshness.fresh_hours} h count as stale.` : undefined}
      />
      {pending && (
        <div className="mb-4">
          <Notice tone="warning" title="Facility awaiting approval">
            You can set up inventory now. Your stock will appear in public search after a system administrator approves the facility.
          </Notice>
        </div>
      )}
      <Card className="mb-6 p-4">
        <div className="flex flex-wrap gap-3">
          {isAdmin && (
            <FilterSelect label="County" value={f.county_id} onChange={set('county_id')}>
              <option value="">All counties</option>
              {counties.data?.filter((c) => c.participating_facilities > 0).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </FilterSelect>
          )}
          {(facilities.data?.length ?? 0) > 1 && (
            <FilterSelect label="Facility" value={f.facility_id} onChange={set('facility_id')}>
              <option value="">All facilities</option>
              {facilities.data?.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </FilterSelect>
          )}
          <FilterSelect label="Medicine" value={f.medicine_id} onChange={set('medicine_id')}>
            <option value="">All medicines</option>
            {medicines.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.generic_name} {m.strength}
              </option>
            ))}
          </FilterSelect>
          <FilterSelect label="Stock status" value={f.status} onChange={set('status')}>
            <option value="">Any</option>
            <option value="out_of_stock">Out of stock</option>
            <option value="low">Low</option>
            <option value="stale">Stale</option>
          </FilterSelect>
          <FilterSelect label="Alert severity" value={f.severity} onChange={set('severity')}>
            <option value="">Any</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </FilterSelect>
          <label className="block text-xs font-medium text-slate-600">
            From
            <Input type="date" className="mt-1" value={f.date_from} onChange={(e) => set('date_from')(e.target.value)} />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            To
            <Input type="date" className="mt-1" value={f.date_to} onChange={(e) => set('date_to')(e.target.value)} />
          </label>
        </div>
      </Card>

      {ov.loading && !d && <Spinner />}
      <ErrorState error={ov.error} onRetry={ov.reload} />
      {d && (
        <div className={ov.loading ? 'opacity-60 transition-opacity' : ''}>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            <Stat label="Facilities" value={d.totals.facilities} icon={<Building2 className="h-4 w-4" />} hint={isAdmin ? 'Approved' : undefined} />
            <Stat label="Medicine records" value={d.totals.medicine_records} icon={<Boxes className="h-4 w-4" />} />
            <Stat label="Available" value={d.totals.available} tone="good" icon={<CheckCircle2 className="h-4 w-4" />} />
            <Stat label="Low stock" value={d.totals.low_stock} tone="warn" icon={<AlertTriangle className="h-4 w-4" />} />
            <Stat label="Out of stock" value={d.totals.out_of_stock} tone="bad" icon={<XCircle className="h-4 w-4" />} />
            <Stat label="Stale" value={d.totals.stale} tone="muted" icon={<Clock className="h-4 w-4" />} />
            <Stat label="Unresolved alerts" value={d.totals.unresolved_alerts} tone={d.totals.unresolved_alerts ? 'bad' : 'default'} icon={<Bell className="h-4 w-4" />} />
            <Stat label="Ripple signals" value={d.totals.ripple_signals_open} tone={d.totals.ripple_signals_open ? 'warn' : 'default'} icon={<Radar className="h-4 w-4" />} />
          </div>

          {d.platform && (
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
              <Link to="/app/facilities?status=pending" className="rounded-md bg-amber-50 px-2 py-1 text-amber-900 hover:underline">
                {d.platform.pending_facilities} pending registration(s)
              </Link>
              <span className="rounded-md bg-slate-100 px-2 py-1">{d.totals.unverified_reports} unverified public report(s)</span>
              <span className="rounded-md bg-slate-100 px-2 py-1">
                {d.platform.searches_last_7d} searches in 7 days ({Object.entries(d.platform.searches_by_channel_7d).map(([k, v]) => `${k}: ${v}`).join(', ') || 'none'})
              </span>
              <span className="rounded-md bg-slate-100 px-2 py-1">
                SMS: {Object.entries(d.platform.deliveries_by_status).map(([k, v]) => `${humanize(k)} ${v}`).join(' · ') || 'none yet'}
              </span>
            </div>
          )}

          <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
            <Card>
              <CardHeader title="Medicines requiring attention" subtitle="Out of stock, low, stale or expiring, with estimated days remaining where history allows." />
              {d.attention.length === 0 ? (
                <EmptyState title="Nothing needs attention for these filters" />
              ) : (
                <Table>
                  <thead className="bg-slate-50">
                    <tr>
                      <Th>Medicine</Th>
                      <Th>Status</Th>
                      <Th className="text-right">Qty / min</Th>
                      <Th>Est. days left</Th>
                      <Th>Updated</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {d.attention.slice(0, 12).map((a) => (
                      <tr key={a.inventory_id}>
                        <Td>
                          <Link to={`/app/inventory/${a.inventory_id}`} className="font-medium text-ink hover:text-brand-700 hover:underline">
                            {a.medicine}
                          </Link>
                          <p className="text-xs text-slate-500">{a.facility_name}</p>
                          {a.expiring && <p className="text-xs font-medium text-amber-800">Expiring {formatDate(a.expiry_date)}</p>}
                        </Td>
                        <Td>
                          <StatusBadge status={a.status} short />
                        </Td>
                        <Td className="text-right tabular-nums">
                          {a.quantity.toLocaleString()} / {a.min_threshold.toLocaleString()}
                        </Td>
                        <Td>{a.days_remaining != null ? `~${a.days_remaining}` : <span className="text-xs text-slate-500" title={a.estimate_note ?? ''}>Not enough data</span>}</Td>
                        <Td className="whitespace-nowrap text-xs">{timeAgo(a.last_updated_at)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>
            <Card>
              <CardHeader title="Recent alerts" action={<Link to="/app/alerts" className="text-sm text-brand-700 hover:underline">All alerts</Link>} />
              {d.recent_alerts.length === 0 ? (
                <EmptyState title="No alerts in this period" />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {d.recent_alerts.map((a) => (
                    <li key={a.id} className="px-5 py-3">
                      <Link to={a.alert_type === 'ripple' ? `/app/ripple/${a.id}` : `/app/alerts/${a.id}`} className="block hover:bg-slate-50">
                        <div className="flex flex-wrap items-center gap-2">
                          <SeverityBadge severity={a.severity} />
                          <AlertStatusPill status={a.status} />
                          <span className="text-xs text-slate-500">{timeAgo(a.created_at)}</span>
                        </div>
                        <p className="mt-1 text-sm font-medium text-ink">{a.title}</p>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader title="Stockout and low-stock alerts over time" subtitle="Alerts created per day" />
              <div className="h-64 px-2 py-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.trend} margin={{ left: -20, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} fontSize={11} interval="preserveStartEnd" />
                    <YAxis allowDecimals={false} fontSize={11} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="stockout" name="Stockout" stackId="a" fill="#b91c1c" />
                    <Bar dataKey="low_stock" name="Low stock" stackId="a" fill="#d97706" />
                    <Bar dataKey="ripple" name="Ripple signal" stackId="a" fill="#6d28d9" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <CardHeader title="Facility map" subtitle="Colour shows each facility's worst current stock status; details in the popup." />
              <div className="p-4">
                {d.map.length ? (
                  <Suspense fallback={<Spinner label="Loading map…" />}>
                    <FacilityMap
                      height={240}
                      points={d.map.map((m) => ({
                        id: m.facility_id,
                        name: m.name,
                        latitude: m.latitude,
                        longitude: m.longitude,
                        status: m.worst_status,
                        detail: `${m.available} available · ${m.low} low · ${m.out_of_stock} out · ${m.stale} stale`,
                      }))}
                    />
                  </Suspense>
                ) : (
                  <EmptyState title="No facility coordinates recorded" />
                )}
              </div>
            </Card>
          </div>

          {d.facility_comparison.length > 0 && (
            <Card className="mt-6">
              <CardHeader title="Facility comparison" />
              <Table>
                <thead className="bg-slate-50">
                  <tr>
                    <Th>Facility</Th>
                    <Th>Status</Th>
                    <Th className="text-right">Records</Th>
                    <Th className="text-right">Available</Th>
                    <Th className="text-right">Low</Th>
                    <Th className="text-right">Out</Th>
                    <Th className="text-right">Stale</Th>
                    <Th className="text-right">Open alerts</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {d.facility_comparison.map((c) => (
                    <tr key={c.facility_id}>
                      <Td>
                        <span className="font-medium text-ink">{c.name}</span>
                        <span className="block text-xs text-slate-500">
                          {c.code} · {c.county}
                        </span>
                      </Td>
                      <Td>{humanize(c.status)}</Td>
                      <Td className="text-right tabular-nums">{c.items}</Td>
                      <Td className="text-right tabular-nums text-emerald-700">{c.available}</Td>
                      <Td className="text-right tabular-nums text-amber-700">{c.low}</Td>
                      <Td className="text-right tabular-nums text-red-700">{c.out_of_stock}</Td>
                      <Td className="text-right tabular-nums text-stone-600">{c.stale}</Td>
                      <Td className="text-right tabular-nums">{c.open_alerts}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          )}

          {d.pickup_demand && d.pickup_demand.total_schedules > 0 && (
            <Card className="mt-6">
              <CardHeader
                title="Upcoming collections (next 7 days)"
                subtitle={d.pickup_demand.notice}
              />
              <Table>
                <thead className="bg-slate-50">
                  <tr>
                    <Th>Medicine</Th>
                    <Th>Facility</Th>
                    <Th className="text-right">Reminders</Th>
                    <Th className="text-right">Last reported qty</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {d.pickup_demand.items.map((row) => (
                    <tr key={`${row.facility_id}-${row.medicine_id}`}>
                      <Td>
                        <span className="font-medium text-ink">{row.medicine_name}</span>
                        <span className="block font-mono text-xs text-slate-500">{row.medicine_code}</span>
                      </Td>
                      <Td>{row.facility_name}</Td>
                      <Td className="text-right tabular-nums">{row.scheduled_pickups}</Td>
                      <Td className="text-right">
                        <span className="tabular-nums">{row.current_quantity ?? 'n/a'}</span>
                        {row.note && <p className="mt-1 text-left text-xs text-amber-800">{row.note}</p>}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          )}

          <Card className="mt-6">
            <CardHeader title="Recent stock movements" action={<Link to="/app/movements" className="text-sm text-brand-700 hover:underline">All movements</Link>} />
            {d.recent_movements.length === 0 ? (
              <EmptyState title="No movements in this period" />
            ) : (
              <Table>
                <thead className="bg-slate-50">
                  <tr>
                    <Th>When</Th>
                    <Th>Medicine</Th>
                    <Th>Type</Th>
                    <Th className="text-right">Change</Th>
                    <Th className="text-right">After</Th>
                    <Th>By</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {d.recent_movements.map((m) => (
                    <tr key={m.id}>
                      <Td className="whitespace-nowrap text-xs">{formatDateTime(m.created_at)}</Td>
                      <Td>
                        {m.medicine}
                        <span className="block text-xs text-slate-500">{m.facility_name}</span>
                      </Td>
                      <Td>
                        {humanize(m.movement_type)}
                        {m.source !== 'web' && <span className="ml-1 text-xs text-slate-500">via {m.source}</span>}
                      </Td>
                      <Td className={`text-right tabular-nums ${m.quantity_delta < 0 ? 'text-red-700' : 'text-emerald-700'}`}>
                        {m.quantity_delta > 0 ? '+' : ''}
                        {m.quantity_delta}
                      </Td>
                      <Td className="text-right tabular-nums">{m.quantity_after}</Td>
                      <Td className="text-xs">{m.performed_by ?? 'n/a'}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
