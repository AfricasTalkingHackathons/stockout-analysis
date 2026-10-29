import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useAsync } from '../../lib/hooks'
import type { County, FacilityPrivate, Medicine, Page } from '../../lib/types'
import { Select } from '../../components/ui'

export function useFacilityOptions() {
  const { user } = useAuth()
  return useAsync(async () => {
    if (user?.role === 'system_admin') {
      const r = await api.get<Page<FacilityPrivate>>('/api/manage/facilities', { page_size: 100 })
      return r.items.map((f) => ({ id: f.id, name: f.name, status: f.status }))
    }
    return (user?.memberships ?? []).map((m) => ({ id: m.facility_id, name: m.facility_name, status: m.facility_status }))
  }, [user?.id])
}

export function useCounties() {
  return useAsync(() => api.get<County[]>('/api/locations/counties'), [])
}

export function useMedicines() {
  return useAsync(() => api.get<Page<Medicine>>('/api/admin/medicines', { page_size: 100 }).then((r) => r.items), [])
}

export function FilterSelect({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <label className="block min-w-[150px] flex-1 text-xs font-medium text-slate-600">
      {label}
      <Select className="mt-1" value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </Select>
    </label>
  )
}
