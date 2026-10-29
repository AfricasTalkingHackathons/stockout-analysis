import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, EmptyState, ErrorState, Input, PageHeader, Pagination, Spinner, Table, Td, Th } from '../../components/ui'
import { api } from '../../lib/api'
import { formatDateTime, humanize } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { Movement, Page } from '../../lib/types'
import { FilterSelect, useFacilityOptions, useMedicines } from './common'

export default function Movements() {
  const [facilityId, setFacilityId] = useState('')
  const [medicineId, setMedicineId] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const facilities = useFacilityOptions()
  const medicines = useMedicines()
  const list = useAsync(
    () =>
      api.get<Page<Movement>>('/api/inventory/movements', {
        facility_id: facilityId,
        medicine_id: medicineId,
        date_from: from ? new Date(from).toISOString() : '',
        date_to: to ? new Date(to + 'T23:59:59').toISOString() : '',
        page,
        page_size: 30,
      }),
    [facilityId, medicineId, from, to, page],
  )
  return (
    <div>
      <PageHeader title="Stock movement history" description="An append-only record of every receipt, dispensing, count and adjustment." />
      <Card className="mb-4 p-4">
        <div className="flex flex-wrap gap-3">
          {(facilities.data?.length ?? 0) > 1 && (
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
          <label className="text-xs font-medium text-slate-600">
            From
            <Input type="date" className="mt-1" value={from} onChange={(e) => (setFrom(e.target.value), setPage(1))} />
          </label>
          <label className="text-xs font-medium text-slate-600">
            To
            <Input type="date" className="mt-1" value={to} onChange={(e) => (setTo(e.target.value), setPage(1))} />
          </label>
        </div>
      </Card>
      <Card>
        {list.loading && !list.data && <Spinner />}
        <ErrorState error={list.error} onRetry={list.reload} />
        {list.data?.items.length === 0 && <EmptyState title="No movements for these filters" />}
        {!!list.data?.items.length && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>When</Th>
                <Th>Medicine</Th>
                <Th>Facility</Th>
                <Th>Type</Th>
                <Th className="text-right">Before</Th>
                <Th className="text-right">Change</Th>
                <Th className="text-right">After</Th>
                <Th>Reason</Th>
                <Th>By</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((m) => (
                <tr key={m.id}>
                  <Td className="whitespace-nowrap text-xs">{formatDateTime(m.created_at)}</Td>
                  <Td>
                    <Link to={`/app/inventory/${m.inventory_id}`} className="text-brand-700 hover:underline">
                      {m.medicine}
                    </Link>
                  </Td>
                  <Td className="text-xs">{m.facility_name}</Td>
                  <Td>
                    {humanize(m.movement_type)} <span className="text-xs text-slate-500">({m.source})</span>
                  </Td>
                  <Td className="text-right tabular-nums">{m.quantity_before}</Td>
                  <Td className={`text-right tabular-nums ${m.quantity_delta < 0 ? 'text-red-700' : 'text-emerald-700'}`}>
                    {m.quantity_delta > 0 ? '+' : ''}
                    {m.quantity_delta}
                  </Td>
                  <Td className="text-right tabular-nums">{m.quantity_after}</Td>
                  <Td className="text-xs">{m.reason ?? 'n/a'}</Td>
                  <Td className="text-xs">{m.performed_by ?? 'n/a'}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && <Pagination page={page} pageSize={30} total={list.data.total} onPage={setPage} />}
      </Card>
    </div>
  )
}
