import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../lib/auth'
import Login from '../pages/public/Login'
import SearchPage from '../pages/public/Search'
import { AppLayout } from '../components/Layout'

type Handler = (url: URL, init?: RequestInit) => unknown

function mockFetch(routes: Record<string, Handler>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost')
    const handler = Object.entries(routes).find(([p]) => url.pathname === p)?.[1]
    if (!handler) return new Response(JSON.stringify({ error: { code: 'not_found', message: 'nf' } }), { status: 404 })
    const body = handler(url, init)
    if (body instanceof Response) return body
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
}

const META = { app_name: 'StockOut Alert', demo_mode: true, sms_mode: 'simulated', fresh_hours: 72, unknown_after_days: 30, ussd_service_code: null }
const MED = {
  id: 'm1', code: 'MED001', generic_name: 'Amoxicillin', brand_names: ['Amoxil'], strength: '500 mg', dosage_form: 'capsule',
  base_unit: 'capsule', display_name: 'Amoxicillin 500 mg capsule', requires_prescription: true,
}
const facility = (id: string, name: string) => ({
  id, code: id, name, facility_type: 'pharmacy', county: { id: 47, name: 'Nairobi' }, town: 'Westlands', address: null,
  phone: null, latitude: -1.26, longitude: 36.8, is_demo: true,
})

function renderAt(path: string, element: React.ReactNode, routePath = '*') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path={routePath} element={element} />
          <Route path="/login" element={<p>login page</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Search page', () => {
  it('shows availability with freshness, stale labelling and safety notice', async () => {
    const now = new Date().toISOString()
    mockFetch({
      '/api/public/meta': () => META,
      '/api/locations/counties': () => [{ id: 47, code: '047', name: 'Nairobi', participating_facilities: 3 }],
      '/api/locations': () => [],
      '/api/medicines/m1': () => MED,
      '/api/availability/search': () => ({
        medicines: [MED],
        county: 'Nairobi',
        notice: 'Availability is self-reported. Contact the facility before travelling.',
        alternatives: null,
        results: [
          { facility: facility('f1', 'Mwangaza Community Pharmacy (Demo)'), medicine: MED, status: 'available', status_label: 'Reported available', confirmed: true, last_updated_at: now, age_hours: 1, source: 'facility_inventory', quantity: 400, unit: 'capsule', distance_km: 0.4, notes: [] },
          { facility: facility('f4', 'Upendo Chemist (Demo)'), medicine: MED, status: 'stale', status_label: 'Stale', confirmed: false, last_updated_at: '2026-10-19T10:00:00Z', age_hours: 240, source: 'facility_inventory', quantity: null, unit: null, distance_km: 2, notes: ['This report may be out of date.'] },
          { facility: facility('f9', 'Other Facility (Demo)'), medicine: MED, status: 'unknown', status_label: 'Unknown', confirmed: false, last_updated_at: null, age_hours: null, source: null, quantity: null, unit: null, distance_km: null, notes: [] },
        ],
      }),
    })
    renderAt('/search?medicine=m1&county=47', <SearchPage />)
    expect(await screen.findByText('Mwangaza Community Pharmacy (Demo)')).toBeInTheDocument()
    expect(screen.getByText('Reported available')).toBeInTheDocument()
    expect(screen.getByText('Stale: needs confirmation')).toBeInTheDocument()
    expect(screen.getByText('Not currently confirmed')).toBeInTheDocument()
    expect(screen.getByText(/Contact the facility before travelling/)).toBeInTheDocument()
    expect(screen.getByText(/About 400 capsules reported/)).toBeInTheDocument()
    expect(screen.getByText(/1 participating facility has no recent report/)).toBeInTheDocument()
    expect(screen.getAllByText('Demo facility: no real phone number').length).toBeGreaterThan(0)
    expect(screen.getByText(/needs a prescription/)).toBeInTheDocument()
  })

  it('offers alternatives and subscription when nothing is available', async () => {
    mockFetch({
      '/api/public/meta': () => META,
      '/api/locations/counties': () => [{ id: 47, code: '047', name: 'Nairobi', participating_facilities: 3 }],
      '/api/locations': () => [],
      '/api/medicines/m1': () => MED,
      '/api/availability/search': () => ({
        medicines: [MED], county: 'Nairobi', notice: 'n', results: [],
        alternatives: { other_areas: [{ county_id: 22, county: 'Kiambu', facilities: 1 }], can_subscribe: true, message: 'No participating facility in this area has recently reported this medicine as available.' },
      }),
    })
    renderAt('/search?medicine=m1&county=47', <SearchPage />)
    expect(await screen.findByText(/No recent “available” report here/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kiambu (1)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Notify me' })).toBeInTheDocument()
  })

  it('requires consent before subscribing', async () => {
    const calls: string[] = []
    mockFetch({
      '/api/public/meta': () => META,
      '/api/locations/counties': () => [],
      '/api/locations': () => [],
      '/api/medicines/m1': () => MED,
      '/api/availability/search': () => ({ medicines: [MED], notice: 'n', results: [], alternatives: { other_areas: [], can_subscribe: true, message: 'none' } }),
      '/api/notifications/subscriptions': () => (calls.push('sub'), { message: 'ok' }),
    })
    renderAt('/search?medicine=m1&county=47', <SearchPage />)
    const user = userEvent.setup()
    const phoneInputs = await screen.findAllByLabelText('Mobile number')
    await user.type(phoneInputs[0], '0712345678')
    await user.click(screen.getByRole('button', { name: 'Notify me' }))
    expect(await screen.findByText(/confirm you agree/)).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })
})

describe('Auth', () => {
  it('validates the login form and shows server errors', async () => {
    mockFetch({
      '/api/public/meta': () => META,
      '/api/auth/login': () => new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'Incorrect email or password' } }), { status: 401 }),
    })
    renderAt('/signin', <Login />, '/signin')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Email'), 'admin@demo.stockout.example')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Incorrect email or password')).toBeInTheDocument()
    expect(screen.getByText('Demo accounts')).toBeInTheDocument()
  })

  it('redirects anonymous users away from the dashboard', async () => {
    mockFetch({ '/api/public/meta': () => META })
    renderAt('/app', <AppLayout />, '/app')
    await waitFor(() => expect(screen.getByText('login page')).toBeInTheDocument())
  })

  it('hides admin navigation from facility staff', async () => {
    sessionStorage.setItem('stockout.token', 't')
    mockFetch({
      '/api/public/meta': () => META,
      '/api/auth/me': () => ({
        id: 'u', email: 's@x', full_name: 'Staff Person', role: 'facility_staff', phone: null,
        memberships: [{ facility_id: 'f1', facility_name: 'Mwangaza', facility_code: 'F1', facility_status: 'approved', role: 'facility_staff', can_update_stock: true }],
        permissions: ['inventory.view', 'inventory.update', 'alerts.view', 'alerts.manage'],
      }),
    })
    renderAt('/app', <AppLayout />, '/app')
    expect((await screen.findAllByText('Inventory')).length).toBeGreaterThan(0)
    expect(screen.queryByText('Audit logs')).toBeNull()
    expect(screen.queryByText('Medicine catalog')).toBeNull()
    expect(screen.queryByText('Settings & integrations')).toBeNull()
  })
})

describe('Refill page', () => {
  it('shows safety copy and another clinic when the usual site is short', async () => {
    const tld = {
      ...MED,
      id: 'm16',
      code: 'MED016',
      generic_name: 'Tenofovir + Lamivudine + Dolutegravir',
      brand_names: ['TLD'],
      display_name: 'Tenofovir + Lamivudine + Dolutegravir 300/300/50 mg tablet',
      is_long_term: true,
    }
    mockFetch({
      '/api/public/meta': () => META,
      '/api/locations/counties': () => [{ id: 47, code: '047', name: 'Nairobi', participating_facilities: 3 }],
      '/api/medicines': () => ({ items: [tld], total: 1, page: 1, page_size: 50 }),
      '/api/availability/search': () => ({
        medicines: [tld],
        county: 'Nairobi',
        notice: 'Availability is self-reported. Do not change prescribed medicines without a qualified health professional.',
        alternatives: null,
        results: [
          { facility: facility('f2', 'Tumaini Health Centre (Demo)'), medicine: tld, status: 'low', status_label: 'Reported low stock', confirmed: true, last_updated_at: new Date().toISOString(), age_hours: 1, source: 'facility_inventory', quantity: 18, unit: 'tablet', distance_km: 1, notes: [] },
          { facility: facility('f3', 'Baraka Medical Clinic (Demo)'), medicine: tld, status: 'available', status_label: 'Reported available', confirmed: true, last_updated_at: new Date().toISOString(), age_hours: 1, source: 'facility_inventory', quantity: 400, unit: 'tablet', distance_km: 2, notes: [] },
        ],
      }),
    })
    const { default: Refill } = await import('../pages/public/Refill')
    renderAt('/refill?medicine=m16&county=47', <Refill />)
    expect(await screen.findByText(/Do not skip, split or reduce your dose/)).toBeInTheDocument()
    expect(screen.getByText('Baraka Medical Clinic (Demo)')).toBeInTheDocument()
    expect(screen.getByText('Tumaini Health Centre (Demo)')).toBeInTheDocument()
    expect(screen.getByText(/never names the medicine/i)).toBeInTheDocument()
    expect(screen.queryByText(/take half/i)).toBeNull()
  })
})
