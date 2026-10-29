import 'leaflet/dist/leaflet.css'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'

export interface MapPoint {
  id: string
  name: string
  latitude: number
  longitude: number
  status: string
  detail?: string
  href?: string
}

const COLORS: Record<string, string> = {
  available: '#047857',
  low: '#b45309',
  out_of_stock: '#b91c1c',
  stale: '#78716c',
  unknown: '#64748b',
}

export default function FacilityMap({ points, height = 320, center }: { points: MapPoint[]; height?: number; center?: [number, number] }) {
  if (!points.length) return null
  const lat = center?.[0] ?? points.reduce((s, p) => s + p.latitude, 0) / points.length
  const lng = center?.[1] ?? points.reduce((s, p) => s + p.longitude, 0) / points.length
  return (
    <div style={{ height }} className="overflow-hidden rounded-xl border border-slate-200">
      <MapContainer center={[lat, lng]} zoom={12} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {points.map((p) => (
          <CircleMarker
            key={p.id}
            center={[p.latitude, p.longitude]}
            radius={10}
            pathOptions={{ color: '#fff', weight: 2, fillColor: COLORS[p.status] ?? COLORS.unknown, fillOpacity: 0.95 }}
          >
            <Popup>
              <strong>{p.name}</strong>
              {p.detail && <div>{p.detail}</div>}
              {p.href && (
                <a href={p.href} style={{ display: 'block', marginTop: 4 }}>
                  View details
                </a>
              )}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
