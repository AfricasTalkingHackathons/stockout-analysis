export type PublicStatus = 'available' | 'low' | 'out_of_stock' | 'stale' | 'unknown'
export type StockStatus = 'available' | 'low' | 'out_of_stock' | 'stale'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface Medicine {
  id: string
  code: string
  generic_name: string
  brand_names: string[]
  strength: string
  dosage_form: string
  base_unit: string
  display_name: string
  requires_prescription: boolean
  category?: string | null
  is_long_term?: boolean
  is_active?: boolean
}

export interface PickupSchedule {
  id: string
  phone: string
  medicine: Medicine
  county: { id: number; name: string }
  preferred_facility: { id: string; name: string; is_demo: boolean } | null
  interval_days: number
  next_pickup_on: string
  remind_days_before: number
  is_active: boolean
  is_demo: boolean
  preferred_status: { status: PublicStatus; status_label: string; last_updated_at: string | null } | null
  alternatives: {
    facility_id: string
    name: string
    town: string | null
    status: PublicStatus
    status_label: string
    last_updated_at: string | null
    is_demo: boolean
  }[]
  message?: string
}

export interface PickupDemand {
  horizon_days: number
  from: string
  to: string
  total_schedules: number
  notice: string
  items: {
    facility_id: string
    facility_name: string | null
    medicine_id: string
    medicine_code: string
    medicine_name: string
    scheduled_pickups: number
    current_quantity: number | null
    current_status: string | null
    note: string | null
  }[]
}

export interface County {
  id: number
  code: string
  name: string
  participating_facilities: number
}

export interface Location {
  id: number
  name: string
  county_id: number
  latitude: number | null
  longitude: number | null
}

export interface PublicFacility {
  id: string
  code: string
  name: string
  facility_type: string
  county: { id: number; name: string } | null
  town: string | null
  address: string | null
  phone: string | null
  latitude: number | null
  longitude: number | null
  is_demo: boolean
}

export interface SearchResult {
  facility: PublicFacility
  medicine: Medicine
  status: PublicStatus
  status_label: string
  confirmed: boolean
  last_updated_at: string | null
  age_hours: number | null
  source: string | null
  quantity: number | null
  unit: string | null
  distance_km: number | null
  notes: string[]
}

export interface SearchResponse {
  medicines: Medicine[]
  county?: string | null
  results: SearchResult[]
  alternatives: {
    other_areas: { county_id: number; county: string; facilities: number }[]
    can_subscribe: boolean
    message: string
  } | null
  notice: string
}

export interface Meta {
  app_name: string
  demo_mode: boolean
  sms_mode: string
  fresh_hours: number
  unknown_after_days: number
  ussd_service_code: string | null
}

export interface Membership {
  facility_id: string
  facility_name: string
  facility_code: string
  facility_status: string
  role: string
  can_update_stock: boolean
}

export interface User {
  id: string
  email: string
  full_name: string
  role: 'system_admin' | 'facility_admin' | 'facility_staff'
  phone: string | null
  memberships: Membership[]
  permissions: string[]
}

export interface InventoryItem {
  id: string
  facility_id: string
  facility_name: string
  facility_code: string
  medicine: Medicine
  quantity: number
  unit: string
  min_threshold: number
  batch_number: string | null
  expiry_date: string | null
  last_updated_at: string
  last_updated_by: string | null
  verification_status: string
  internal_notes: string | null
  version: number
  stock_status: StockStatus
  estimate?: { days_remaining: number | null; avg_daily: number | null; reason: string }
}

export interface Movement {
  id: string
  inventory_id: string
  movement_type: string
  quantity_delta: number
  quantity_before: number
  quantity_after: number
  reason: string | null
  source: string
  performed_by: string | null
  created_at: string
  medicine: string | null
  facility_name: string | null
}

export interface RippleEvidence {
  facility_id: string
  facility_name: string
  source_type: string
  source_id: string
  observed_status: string
  observed_at: string
  verified: boolean
  weight: number
  counted: boolean
}

export interface Alert {
  id: string
  alert_type: string
  severity: 'info' | 'warning' | 'critical'
  status: 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'dismissed'
  title: string
  facility: { id: string; name: string; is_demo: boolean } | null
  medicine: Medicine | null
  county: { id: number; name: string } | null
  evidence: Record<string, unknown>
  assigned_to: { id: string; full_name: string } | null
  created_at: string
  updated_at: string
  acknowledged_at: string | null
  resolved_at: string | null
  resolution_notes: string | null
  escalation_level: number
  last_notified_at: string | null
  ripple_evidence?: RippleEvidence[]
}

export interface StockReport {
  id: string
  reference: string
  facility: { id: string; name: string; code: string }
  medicine: Medicine
  reported_status: string
  reported_status_label: string
  source: string
  verification_status: string
  created_at: string
  verified_at: string | null
  comment?: string | null
  history?: { decision: string; note: string | null; created_at: string }[]
}

export interface Delivery {
  id: string
  recipient: string
  message: string
  purpose: string
  status: string
  provider: string | null
  provider_status: string | null
  provider_message_id: string | null
  failure_reason: string | null
  attempts: number
  is_demo: boolean
  created_at: string
  delivered_at: string | null
}

export interface FacilityPrivate {
  id: string
  code: string
  name: string
  facility_type: string
  county: { id: number; name: string }
  location: { id: number; name: string } | null
  address: string | null
  phone: string | null
  email: string | null
  license_number: string | null
  latitude: number | null
  longitude: number | null
  status: string
  status_reason: string | null
  public_show_quantity: boolean
  is_demo: boolean
  created_at: string
  approved_at: string | null
}

export interface StaffMember {
  id: string
  user_id: string
  full_name: string
  email: string
  phone: string | null
  sms_phone: string | null
  role: string
  can_update_stock: boolean
  receive_alerts: boolean
  is_active: boolean
}

export interface AttentionItem {
  inventory_id: string
  facility_id: string
  facility_name: string
  medicine: string
  medicine_code: string
  quantity: number
  unit: string
  min_threshold: number
  status: string
  expiry_date: string | null
  expiring: boolean
  last_updated_at: string
  days_remaining: number | null
  estimate_note: string | null
}

export interface Overview {
  generated_at: string
  freshness: { fresh_hours: number; unknown_after_days: number }
  totals: {
    facilities: number
    medicine_records: number
    available: number
    low_stock: number
    out_of_stock: number
    stale: number
    unresolved_alerts: number
    ripple_signals_open: number
    unverified_reports: number
  }
  recent_movements: Movement[]
  recent_alerts: Alert[]
  attention: AttentionItem[]
  trend: { date: string; stockout: number; low_stock: number; ripple: number }[]
  facility_comparison: {
    facility_id: string
    name: string
    code: string
    county: string
    status: string
    is_demo: boolean
    items: number
    available: number
    low: number
    out_of_stock: number
    stale: number
    open_alerts: number
  }[]
  map: {
    facility_id: string
    name: string
    latitude: number
    longitude: number
    worst_status: string
    available: number
    low: number
    out_of_stock: number
    stale: number
  }[]
  has_demo_data: boolean
  pickup_demand?: PickupDemand
  platform?: {
    pending_facilities: number
    suspended_facilities: number
    deliveries_by_status: Record<string, number>
    searches_last_7d: number
    searches_by_channel_7d: Record<string, number>
  }
}
