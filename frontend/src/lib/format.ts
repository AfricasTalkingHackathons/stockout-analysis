const dtf = new Intl.DateTimeFormat('en-KE', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Africa/Nairobi',
})
const df = new Intl.DateTimeFormat('en-KE', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Africa/Nairobi' })

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'n/a'
  return `${dtf.format(new Date(iso))} EAT`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return 'n/a'
  return df.format(new Date(iso))
}

export function timeAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return 'never'
  const diff = (now.getTime() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
  const days = Math.floor(diff / 86400)
  return days === 1 ? '1 day ago' : `${days} days ago`
}

export function humanize(s: string): string {
  return s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

export const FACILITY_TYPES: Record<string, string> = {
  pharmacy: 'Pharmacy',
  clinic: 'Clinic',
  health_centre: 'Health centre',
  dispensary: 'Dispensary',
  hospital: 'Hospital',
}
