import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppLayout, PublicLayout } from './components/Layout'
import { Spinner } from './components/ui'
import FacilityDetail from './pages/public/FacilityDetail'
import Landing from './pages/public/Landing'
import Login from './pages/public/Login'
import { NotFound, ReportPage, Unsubscribe } from './pages/public/Misc'
import Register from './pages/public/Register'
import Refill from './pages/public/Refill'
import SearchPage from './pages/public/Search'

const UssdSimulator = lazy(() => import('./pages/public/UssdSimulator'))
const Dashboard = lazy(() => import('./pages/app/Dashboard'))
const Inventory = lazy(() => import('./pages/app/Inventory'))
const InventoryDetail = lazy(() => import('./pages/app/InventoryDetail'))
const Movements = lazy(() => import('./pages/app/Movements'))
const Reports = lazy(() => import('./pages/app/Reports'))
const Settings = lazy(() => import('./pages/app/Settings'))
const AlertsList = lazy(() => import('./pages/app/Alerts').then((m) => ({ default: m.AlertsList })))
const AlertDetail = lazy(() => import('./pages/app/Alerts').then((m) => ({ default: m.AlertDetail })))
const FacilitiesList = lazy(() => import('./pages/app/Facilities').then((m) => ({ default: m.FacilitiesList })))
const FacilityManage = lazy(() => import('./pages/app/Facilities').then((m) => ({ default: m.FacilityManage })))
const Catalog = lazy(() => import('./pages/app/Admin').then((m) => ({ default: m.Catalog })))
const Notifications = lazy(() => import('./pages/app/Admin').then((m) => ({ default: m.Notifications })))
const AuditLogs = lazy(() => import('./pages/app/Admin').then((m) => ({ default: m.AuditLogs })))

const RippleList = () => <AlertsList ripple />

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<Landing />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="refill" element={<Refill />} />
          <Route path="facilities/:id" element={<FacilityDetail />} />
          <Route path="login" element={<Login />} />
          <Route path="register" element={<Register />} />
          <Route path="ussd" element={<UssdSimulator />} />
          <Route path="unsubscribe" element={<Unsubscribe />} />
          <Route path="report" element={<ReportPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="app" element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="inventory" element={<Inventory />} />
          <Route path="inventory/:id" element={<InventoryDetail />} />
          <Route path="movements" element={<Movements />} />
          <Route path="alerts" element={<AlertsList />} />
          <Route path="alerts/:id" element={<AlertDetail />} />
          <Route path="ripple" element={<RippleList />} />
          <Route path="ripple/:id" element={<AlertDetail />} />
          <Route path="reports" element={<Reports />} />
          <Route path="facilities" element={<FacilitiesList />} />
          <Route path="facilities/:id" element={<FacilityManage />} />
          <Route path="catalog" element={<Catalog />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="audit" element={<AuditLogs />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
