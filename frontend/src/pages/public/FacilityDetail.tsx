import { ArrowLeft, ExternalLink, MapPin, Phone } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ReportForm } from '../../components/PublicForms'
import { StatusBadge } from '../../components/StatusBadge'
import { Card, CardHeader, EmptyState, ErrorState, Modal, Notice, Spinner, Table, Td, Th } from '../../components/ui'
import { api } from '../../lib/api'
import { FACILITY_TYPES, formatDateTime, timeAgo } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { Medicine, PublicFacility, PublicStatus } from '../../lib/types'

const FacilityMap = lazy(() => import('../../components/FacilityMap'))

interface Detail extends PublicFacility {
  availability: { medicine: Medicine; status: PublicStatus; status_label: string; confirmed: boolean; last_updated_at: string | null; notes: string[]; quantity: number | null; unit: string | null }[]
}

export default function FacilityDetail() {
  const { id } = useParams()
  const { data, error, loading, reload } = useAsync(() => api.get<Detail>(`/api/facilities/${id}`), [id])
  const [reportMed, setReportMed] = useState<Medicine | null>(null)

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Link to="/search" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Back to search
      </Link>
      {loading && <Spinner />}
      <ErrorState error={error} onRetry={reload} />
      {data && (
        <>
          <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
              <p className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-slate-600">
                <span>{FACILITY_TYPES[data.facility_type]}</span>
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" aria-hidden /> {[data.address, data.town, data.county?.name].filter(Boolean).join(', ')}
                </span>
              </p>
            </div>
            <div className="flex gap-2">
              {data.phone ? (
                <a href={`tel:${data.phone}`} className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-700 px-4 text-sm font-medium text-white">
                  <Phone className="h-4 w-4" aria-hidden /> Call {data.phone}
                </a>
              ) : (
                <span className="rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-600">{data.is_demo ? 'Demo facility: no real phone number' : 'No phone listed'}</span>
              )}
              {data.latitude != null && (
                <a
                  href={`https://www.openstreetmap.org/directions?to=${data.latitude}%2C${data.longitude}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-10 items-center gap-2 rounded-lg px-4 text-sm font-medium ring-1 ring-inset ring-slate-300"
                >
                  <ExternalLink className="h-4 w-4" aria-hidden /> Directions
                </a>
              )}
            </div>
          </div>
          {data.is_demo && (
            <div className="mt-4">
              <Notice tone="info">This is a fictional demonstration facility. Its stock information is synthetic.</Notice>
            </div>
          )}
          <div className="mt-4">
            <Notice tone="warning">Stock may change at any time and nothing is reserved for you. Please call before travelling.</Notice>
          </div>
          {data.latitude != null && data.longitude != null && (
            <div className="mt-6">
              <Suspense fallback={<Spinner label="Loading map…" />}>
                <FacilityMap height={220} points={[{ id: data.id, name: data.name, latitude: data.latitude, longitude: data.longitude, status: 'available' }]} />
              </Suspense>
            </div>
          )}
          <Card className="mt-6">
            <CardHeader title="Reported medicine availability" subtitle="Only medicines this facility has reported are listed." />
            {data.availability.length === 0 ? (
              <EmptyState title="No medicine reports yet" />
            ) : (
              <Table>
                <thead className="bg-slate-50">
                  <tr>
                    <Th>Medicine</Th>
                    <Th>Status</Th>
                    <Th>Last updated</Th>
                    <Th>
                      <span className="sr-only">Actions</span>
                    </Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.availability.map((a) => (
                    <tr key={a.medicine.id}>
                      <Td>
                        <p className="font-medium text-ink">{a.medicine.generic_name}</p>
                        <p className="text-xs text-slate-500">
                          {a.medicine.strength} {a.medicine.dosage_form}
                          {a.quantity != null && ` · about ${a.quantity.toLocaleString()} ${a.unit}s`}
                        </p>
                        {a.notes.map((n) => (
                          <p key={n} className="mt-1 text-xs text-slate-500">
                            {n}
                          </p>
                        ))}
                      </Td>
                      <Td>
                        <StatusBadge status={a.status} />
                      </Td>
                      <Td>
                        <span className="block">{timeAgo(a.last_updated_at)}</span>
                        <span className="text-xs text-slate-500">{formatDateTime(a.last_updated_at)}</span>
                      </Td>
                      <Td>
                        <button className="text-sm text-brand-700 underline" onClick={() => setReportMed(a.medicine)}>
                          Report
                        </button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
          <Modal open={!!reportMed} title="Report availability" onClose={() => setReportMed(null)}>
            {reportMed && (
              <ReportForm facilityId={data.id} medicineId={reportMed.id} facilityName={data.name} medicineName={reportMed.display_name} onDone={() => setReportMed(null)} />
            )}
          </Modal>
        </>
      )}
    </div>
  )
}
