import { useState } from 'react'
import { Pill } from '../../components/StatusBadge'
import { Button, Card, EmptyState, ErrorState, Input, Notice, PageHeader, Pagination, Spinner, Table, Td, Th } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { formatDateTime, humanize } from '../../lib/format'
import { useAsync } from '../../lib/hooks'
import type { Page, StockReport } from '../../lib/types'
import { FilterSelect } from './common'

export default function Reports() {
  const { can } = useAuth()
  const [status, setStatus] = useState('unverified')
  const [page, setPage] = useState(1)
  const [note, setNote] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const list = useAsync(() => api.get<Page<StockReport>>('/api/reports/stockout', { verification_status: status, page, page_size: 25 }), [status, page])

  const decide = async (r: StockReport, decision: string) => {
    setError(null)
    try {
      await api.post(`/api/reports/${r.id}/verify`, { decision, note: note[r.id] || null })
      list.reload()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed')
    }
  }

  return (
    <div>
      <PageHeader
        title="Public availability reports"
        description="Reports from the public via web and USSD. They are treated as unverified until a facility team or administrator confirms them; only verified reports carry full weight in ripple detection."
      />
      <Card className="mb-4 p-4">
        <FilterSelect label="Verification status" value={status} onChange={(v) => (setStatus(v), setPage(1))}>
          <option value="unverified">Unverified</option>
          <option value="verified">Verified</option>
          <option value="disputed">Disputed</option>
          <option value="rejected">Rejected</option>
          <option value="">All</option>
        </FilterSelect>
      </Card>
      {error && (
        <div className="mb-4">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}
      <Card>
        {list.loading && !list.data && <Spinner />}
        <ErrorState error={list.error} onRetry={list.reload} />
        {list.data?.items.length === 0 && <EmptyState title="No reports for this filter" />}
        {!!list.data?.items.length && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>Reference</Th>
                <Th>Medicine / facility</Th>
                <Th>Reported</Th>
                <Th>Source</Th>
                <Th>Status</Th>
                <Th>Decision</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((r) => (
                <tr key={r.id}>
                  <Td className="font-mono text-xs">{r.reference}</Td>
                  <Td>
                    <span className="font-medium text-ink">{r.medicine.display_name}</span>
                    <span className="block text-xs text-slate-500">{r.facility.name}</span>
                    {r.comment && <span className="mt-1 block text-xs italic text-slate-600">“{r.comment}”</span>}
                  </Td>
                  <Td>
                    {r.reported_status_label}
                    <span className="block text-xs text-slate-500">{formatDateTime(r.created_at)}</span>
                  </Td>
                  <Td className="uppercase text-xs">{r.source}</Td>
                  <Td>
                    <Pill tone={r.verification_status === 'verified' ? 'green' : r.verification_status === 'unverified' ? 'amber' : 'slate'}>
                      {humanize(r.verification_status)}
                    </Pill>
                  </Td>
                  <Td>
                    {can('reports.verify') && r.verification_status === 'unverified' ? (
                      <div className="flex min-w-[260px] flex-col gap-2">
                        <Input placeholder="Note (optional)" value={note[r.id] ?? ''} onChange={(e) => setNote((n) => ({ ...n, [r.id]: e.target.value }))} />
                        <div className="flex flex-wrap gap-2">
                          <Button size="sm" onClick={() => decide(r, 'verified')}>
                            Confirm
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => decide(r, 'disputed')}>
                            Dispute
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => decide(r, 'rejected')}>
                            Reject
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-500">{r.verified_at ? formatDateTime(r.verified_at) : 'n/a'}</span>
                    )}
                  </Td>
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
