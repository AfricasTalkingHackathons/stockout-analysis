import { Clock, Crosshair, ExternalLink, Flag, Map as MapIcon, MapPin, MessageSquare, Phone, Search as SearchIcon } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MedicinePicker } from '../../components/MedicinePicker'
import { ReportForm, SmsSummaryForm, SubscribeForm } from '../../components/PublicForms'
import { StatusBadge } from '../../components/StatusBadge'
import { Button, Card, EmptyState, ErrorState, Field, Modal, Notice, Select, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { FACILITY_TYPES, formatDateTime, timeAgo } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { County, Location, Medicine, SearchResponse, SearchResult } from '../../lib/types'

const FacilityMap = lazy(() => import('../../components/FacilityMap'))

export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const medicineId = params.get('medicine')
  const countyId = params.get('county') ? Number(params.get('county')) : null
  const locationId = params.get('location') ? Number(params.get('location')) : null
  const facilityType = params.get('type') ?? ''
  const lat = params.get('lat')
  const lng = params.get('lng')

  const [medicine, setMedicine] = useState<Medicine | null>(null)
  const [showMap, setShowMap] = useState(false)
  const [locating, setLocating] = useState(false)
  const [reporting, setReporting] = useState<SearchResult | null>(null)

  const counties = useAsync(() => api.get<County[]>('/api/locations/counties'), [])
  const locations = useAsync(() => (countyId ? api.get<Location[]>('/api/locations', { county_id: countyId }) : Promise.resolve([])), [countyId])

  useEffect(() => {
    if (medicineId && medicine?.id !== medicineId) {
      api.get<Medicine>(`/api/medicines/${medicineId}`).then(setMedicine).catch(() => setMedicine(null))
    }
    if (!medicineId) setMedicine(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [medicineId])

  const search = useAsync(
    () =>
      medicineId
        ? api.get<SearchResponse>('/api/availability/search', {
            medicine_id: medicineId,
            county_id: countyId,
            location_id: locationId,
            facility_type: facilityType,
            lat,
            lng,
          })
        : Promise.resolve(null),
    [medicineId, countyId, locationId, facilityType, lat, lng],
  )

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: false })
  }

  const useMyLocation = () => {
    if (!navigator.geolocation || locating) return
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        update({ lat: pos.coords.latitude.toFixed(5), lng: pos.coords.longitude.toFixed(5) })
      },
      () => {
        setLocating(false)
      },
      { enableHighAccuracy: false, timeout: 20000, maximumAge: 300000 },
    )
  }

  const data = search.data
  const results = data?.results ?? []
  const known = results.filter((r) => r.status !== 'unknown')
  const unknown = results.filter((r) => r.status === 'unknown')
  const mapPoints = results
    .filter((r) => r.facility.latitude != null && r.facility.longitude != null)
    .map((r) => ({
      id: r.facility.id,
      name: r.facility.name,
      latitude: r.facility.latitude!,
      longitude: r.facility.longitude!,
      status: r.status,
      detail: `${r.status_label} · ${timeAgo(r.last_updated_at)}`,
      href: `/facilities/${r.facility.id}`,
    }))
  const countyName = counties.data?.find((c) => c.id === countyId)?.name
  const subcountyName = locations.data?.find((l) => l.id === locationId)?.name

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Find medicine</h1>
      <p className="mt-1 text-sm text-slate-600">Recently reported availability at participating facilities. Always call before you travel.</p>

      <Card className="mt-6 p-4 md:p-5">
        <form
          className="grid gap-4 md:grid-cols-[2fr_1fr_1fr_1fr]"
          onSubmit={(e) => {
            e.preventDefault()
            if (medicine) update({ medicine: medicine.id })
          }}
        >
          <MedicinePicker
            value={medicine}
            onChange={(m) => {
              setMedicine(m)
              if (m) update({ medicine: m.id })
            }}
          />
          <Field label="County">
            {(id) => (
              <Select id={id} value={countyId ?? ''} onChange={(e) => update({ county: e.target.value || null, location: null })}>
                <option value="">All counties</option>
                {counties.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.participating_facilities ? ` (${c.participating_facilities})` : ''}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Sub-county">
            {(id) => (
              <Select id={id} value={locationId ?? ''} disabled={!countyId} onChange={(e) => update({ location: e.target.value || null })}>
                <option value="">{countyId ? 'All sub-counties' : 'Choose a county first'}</option>
                {locations.data?.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Facility type">
            {(id) => (
              <Select id={id} value={facilityType} onChange={(e) => update({ type: e.target.value || null })}>
                <option value="">Any type</option>
                {Object.entries(FACILITY_TYPES).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </form>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
          <Button type="button" variant="outline" size="sm" onClick={useMyLocation} loading={locating} disabled={locating}>
            <Crosshair className="h-4 w-4" aria-hidden />{' '}
            {locating ? 'Finding your location' : lat ? 'Location in use (update)' : 'Sort by distance from me'}
          </Button>
          {lat && (
            <button className="text-slate-600 underline" onClick={() => update({ lat: null, lng: null })}>
              Stop using my location
            </button>
          )}
          {mapPoints.length > 0 && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setShowMap(!showMap)} aria-pressed={showMap}>
              <MapIcon className="h-4 w-4" aria-hidden /> {showMap ? 'Hide map' : 'Show map'}
            </Button>
          )}
          <span className="text-xs text-slate-500">Optional. You can search by county and sub-county instead.</span>
        </div>
        {countyId && (locations.data?.length ?? 0) > 0 && (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <p className="text-sm font-medium text-slate-700">Sub-counties in {countyName}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className={`rounded-full px-3 py-1 text-sm ${!locationId ? 'bg-brand-700 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                onClick={() => update({ location: null })}
              >
                All
              </button>
              {locations.data?.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  className={`rounded-full px-3 py-1 text-sm ${locationId === l.id ? 'bg-brand-700 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                  onClick={() => update({ location: String(l.id) })}
                >
                  {l.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      <div className="mt-6">
        {!medicineId && (
          <EmptyState title="Search for a medicine to begin" icon={<SearchIcon className="h-6 w-6" />}>
            Type a generic name (such as amoxicillin) or a brand name (such as Panadol), then choose it from the list.
          </EmptyState>
        )}
        {medicineId && search.loading && <Spinner label="Checking participating facilities…" />}
        <ErrorState error={search.error} onRetry={search.reload} />

        {data && !search.loading && (
          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <div className="space-y-4">
              <Notice tone="warning">{data.notice}</Notice>
              {medicine?.is_long_term && (
                <Notice tone="info" title="Collecting this medicine regularly?">
                  <Link to={`/refill?medicine=${medicine.id}${countyId ? `&county=${countyId}` : ''}`} className="underline">
                    Find a facility with a recent available report and set a pickup reminder
                  </Link>
                  . Reminder SMS will not name the medicine. Do not skip or reduce your dose while you wait.
                </Notice>
              )}
              {showMap && (
                <Suspense fallback={<Spinner label="Loading map…" />}>
                  <FacilityMap points={mapPoints} />
                </Suspense>
              )}
              <h2 className="text-sm font-medium text-slate-600" aria-live="polite">
                {known.length} facilit{known.length === 1 ? 'y' : 'ies'} with a report
                {countyName ? ` in ${subcountyName ? `${subcountyName}, ` : ''}${countyName}` : ''}
                {medicine ? ` for ${medicine.display_name}` : ''}
              </h2>
              {known.map((r) => (
                <ResultCard key={r.facility.id + r.medicine.id} r={r} onReport={() => setReporting(r)} />
              ))}

              {data.alternatives && (
                <Card className="p-5">
                  <h3 className="font-semibold">No recent “available” report here</h3>
                  <p className="mt-1 text-sm text-slate-600">{data.alternatives.message}</p>
                  {data.alternatives.other_areas.length > 0 && (
                    <div className="mt-3">
                      <p className="text-sm font-medium">Reported available in other counties:</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {data.alternatives.other_areas.map((a) => (
                          <Button key={a.county_id} size="sm" variant="secondary" onClick={() => update({ county: String(a.county_id), location: null })}>
                            {a.county} ({a.facilities})
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}
                  {countyId && (
                    <Button size="sm" variant="outline" className="mt-3" onClick={() => update({ county: null, location: null })}>
                      Search all counties
                    </Button>
                  )}
                  {data.alternatives.can_subscribe && medicine && countyId && (
                    <div className="mt-5 border-t border-slate-100 pt-4">
                      <SubscribeForm medicineId={medicine.id} countyId={countyId} countyName={countyName} medicineName={medicine.generic_name} />
                    </div>
                  )}
                </Card>
              )}

              {unknown.length > 0 && (
                <details className="rounded-xl border border-slate-200 bg-white p-4">
                  <summary className="cursor-pointer text-sm font-medium">
                    {unknown.length} participating facilit{unknown.length === 1 ? 'y has' : 'ies have'} no recent report for this medicine
                  </summary>
                  <ul className="mt-3 divide-y divide-slate-100">
                    {unknown.map((r) => (
                      <li key={r.facility.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                        <Link to={`/facilities/${r.facility.id}`} className="font-medium text-brand-700 hover:underline">
                          {r.facility.name}
                        </Link>
                        <StatusBadge status="unknown" />
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {results.length === 0 && (
                <EmptyState title="No participating facilities match these filters">
                  Try another sub-county, facility type, or search all counties.
                </EmptyState>
              )}
            </div>

            <aside className="space-y-4">
              {medicine && (
                <Card className="p-5">
                  <h3 className="flex items-center gap-2 font-semibold">
                    <MessageSquare className="h-4 w-4 text-brand-700" aria-hidden /> Get these results by SMS
                  </h3>
                  <p className="mb-3 mt-1 text-sm text-slate-600">Up to three facilities with a recent available or low-stock report.</p>
                  <SmsSummaryForm medicineId={medicine.id} countyId={countyId} />
                </Card>
              )}
              {medicine?.requires_prescription && (
                <Notice tone="info" title="Prescription medicine">
                  This medicine normally needs a prescription. Do not switch to a different medicine without advice from a qualified
                  health professional.
                </Notice>
              )}
            </aside>
          </div>
        )}
      </div>

      <Modal open={!!reporting} title="Report availability" onClose={() => setReporting(null)}>
        {reporting && (
          <ReportForm
            facilityId={reporting.facility.id}
            medicineId={reporting.medicine.id}
            facilityName={reporting.facility.name}
            medicineName={reporting.medicine.display_name}
            onDone={() => setReporting(null)}
          />
        )}
      </Modal>
    </div>
  )
}

function ResultCard({ r, onReport }: { r: SearchResult; onReport: () => void }) {
  const f = r.facility
  const hasCoords = f.latitude != null && f.longitude != null
  return (
    <Card className="p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/facilities/${f.id}`} className="text-base font-semibold text-ink hover:text-brand-700 hover:underline">
            {f.name}
          </Link>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
            <span>{FACILITY_TYPES[f.facility_type] ?? f.facility_type}</span>
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" aria-hidden />
              {[f.town, f.county?.name].filter(Boolean).join(', ')}
            </span>
            {r.distance_km != null && <span>{r.distance_km < 1 ? `${Math.round(r.distance_km * 1000)} m` : `${r.distance_km.toFixed(1)} km`} away</span>}
          </p>
        </div>
        <StatusBadge status={r.status} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-700">
        <span className="inline-flex items-center gap-1">
          <Clock className="h-3.5 w-3.5 text-slate-500" aria-hidden />
          Last updated <strong className="font-medium">{timeAgo(r.last_updated_at)}</strong>
          <span className="text-slate-500">({formatDateTime(r.last_updated_at)})</span>
        </span>
        {r.quantity != null && (
          <span>
            About {r.quantity.toLocaleString()} {r.unit}s reported
          </span>
        )}
        {!r.confirmed && r.status !== 'out_of_stock' && <span className="text-amber-800">Not currently confirmed</span>}
      </div>
      {r.notes.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-600">
          {r.notes.map((n) => (
            <li key={n}>• {n}</li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {f.phone ? (
          <a href={`tel:${f.phone}`} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-700 px-3 text-sm font-medium text-white hover:bg-brand-800">
            <Phone className="h-4 w-4" aria-hidden /> Call {f.phone}
          </a>
        ) : (
          <span className="inline-flex h-9 items-center rounded-lg bg-slate-100 px-3 text-xs text-slate-600">{f.is_demo ? 'Demo facility: no real phone number' : 'No phone listed'}</span>
        )}
        {hasCoords && (
          <a
            href={`https://www.openstreetmap.org/directions?to=${f.latitude}%2C${f.longitude}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50"
          >
            <ExternalLink className="h-4 w-4" aria-hidden /> Directions
          </a>
        )}
        <button onClick={onReport} className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-100">
          <Flag className="h-4 w-4" aria-hidden /> Report what you found
        </button>
      </div>
    </Card>
  )
}
