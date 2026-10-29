import { ArrowRight, Bell, Building2, Clock, MapPin, MessageSquare, Phone, Radar, Search, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { MedicinePicker } from '../../components/MedicinePicker'
import { StatusBadge } from '../../components/StatusBadge'
import { Button } from '../../components/ui'
import { useAuth } from '../../lib/auth'
import type { Medicine } from '../../lib/types'

export default function Landing() {
  const [med, setMed] = useState<Medicine | null>(null)
  const navigate = useNavigate()
  const { meta } = useAuth()

  return (
    <div>
      <section className="relative overflow-hidden bg-gradient-to-b from-brand-900 to-brand-800 text-white">
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: 'radial-gradient(circle at 1px 1px, #fff 1px, transparent 0)', backgroundSize: '22px 22px' }} />
        <div className="relative mx-auto grid max-w-6xl gap-10 px-4 py-14 md:grid-cols-[1.1fr_1fr] md:py-20">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-brand-100">
              <MapPin className="h-3.5 w-3.5" aria-hidden /> Built for Kenya · web, USSD and SMS
            </p>
            <h1 className="mt-5 text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
              Know where your medicine was last reported in stock, <span className="text-brand-200">before you travel.</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-brand-100">
              StockOut Alert shows recently reported medicine availability at participating pharmacies, clinics and hospitals, and helps
              facilities spot shortages early so they can respond sooner.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/search" className="inline-flex h-12 items-center gap-2 rounded-lg bg-white px-6 font-semibold text-brand-800 hover:bg-brand-50">
                <Search className="h-5 w-5" aria-hidden /> Find medicine
              </Link>
              <Link to="/refill" className="inline-flex h-12 items-center gap-2 rounded-lg bg-brand-500 px-6 font-semibold text-white hover:bg-brand-400">
                <Bell className="h-5 w-5" aria-hidden /> Pickup reminders
              </Link>
              <Link to="/register" className="inline-flex h-12 items-center gap-2 rounded-lg px-5 font-medium text-white ring-1 ring-inset ring-white/40 hover:bg-white/10">
                <Building2 className="h-5 w-5" aria-hidden /> Register a facility
              </Link>
              <Link to="/login" className="inline-flex h-12 items-center px-3 font-medium text-brand-100 underline-offset-4 hover:underline">
                Sign in
              </Link>
            </div>
          </div>
          <div className="rounded-2xl bg-white p-5 text-ink shadow-2xl md:p-6">
            <h2 className="text-lg font-semibold">Search availability</h2>
            <p className="mt-1 text-sm text-slate-600">Search by generic or brand name.</p>
            <form
              className="mt-4 space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                navigate(med ? `/search?medicine=${med.id}` : '/search')
              }}
            >
              <MedicinePicker value={med} onChange={setMed} />
              <Button type="submit" size="lg" className="w-full">
                Search participating facilities <ArrowRight className="h-4 w-4" aria-hidden />
              </Button>
            </form>
            <div className="mt-5 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
              <p className="flex items-center gap-2 font-medium">
                <Phone className="h-4 w-4 text-brand-700" aria-hidden /> No smartphone or data?
              </p>
              <p className="mt-1 text-slate-600">
                {meta?.ussd_service_code ? (
                  <>Dial <strong>{meta.ussd_service_code}</strong> from any phone.</>
                ) : (
                  <>A USSD menu works on basic phones. <Link className="text-brand-700 underline" to="/ussd">Try the USSD demo</Link>.</>
                )}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16">
        <div className="grid gap-10 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">The problem</h2>
            <p className="mt-3 leading-relaxed text-slate-700">
              Patients and caregivers often travel from pharmacy to pharmacy looking for a medicine, spending time and transport money,
              while another nearby facility may have stock. Facilities, in turn, often discover a shortage only when the shelf is empty.
            </p>
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">What StockOut Alert does</h2>
            <ul className="mt-3 space-y-2 text-slate-700">
              <li>• Shows the latest stock report from participating facilities, with the time it was last updated.</li>
              <li>• Separates confirmed reports from stale, unverified or unknown information.</li>
              <li>• Warns facility teams when stock runs low or out, and flags possible local shortages early.</li>
              <li>• Helps people on repeating treatment find another participating facility when their usual clinic is short, and send a pickup reminder, without storing a diagnosis.</li>
            </ul>
            <p className="mt-3 text-sm text-slate-500">
              It improves visibility and coordination. It does not supply medicines or guarantee that reported stock is still available.
            </p>
          </div>
        </div>
      </section>

      <section className="border-y border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-16">
          <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
          <div className="mt-8 grid gap-6 md:grid-cols-3">
            {[
              { icon: Building2, title: 'Facilities report stock', body: 'Authorised staff update inventory on the web dashboard or with a short SMS command such as “STOCK MED001 12”. Every change is audited.' },
              { icon: Search, title: 'Patients search', body: 'Search on the web, through USSD on any phone, or request an SMS summary. Results show status and how recent the report is.' },
              { icon: Bell, title: 'Early warnings', body: 'Rules raise low-stock and stockout alerts, estimate days remaining where data allows, and request fresh updates when reports go stale.' },
            ].map(({ icon: Icon, title, body }) => (
              <div key={title} className="rounded-xl border border-slate-200 p-6">
                <Icon className="h-6 w-6 text-brand-700" aria-hidden />
                <h3 className="mt-4 font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-slate-200 bg-brand-50/60">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 md:grid-cols-2">
          <div>
            <p className="text-sm font-semibold text-brand-700">Repeating treatment</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">When one clinic is short, see who recently reported stock, then get a reminder before collection day</h2>
            <p className="mt-3 leading-relaxed text-slate-700">
              People collecting the same medicine every few weeks should not have to take a lower dose while they wait.
              Search participating facilities, and set an SMS reminder a few days before you are due. If your usual site
              has no recent available report, the reminder lists other participating facilities.
            </p>
            <p className="mt-3 text-sm text-slate-500">
              We never store a diagnosis. Reminder messages do not name the medicine. We never tell anyone to skip, split
              or reduce a dose, and we never move stock between facilities automatically.
            </p>
            <Link to="/refill" className="mt-6 inline-flex h-11 items-center gap-2 rounded-lg bg-brand-700 px-5 font-medium text-white hover:bg-brand-800">
              Find a facility and set a reminder <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm leading-relaxed text-slate-700">
            <p className="font-medium text-slate-800">How a reminder looks</p>
            <p className="mt-3 rounded-lg bg-slate-50 p-3 font-mono text-xs text-slate-600">
              StockOut Alert [DEMO] reminder: scheduled medicine pickup on 31 Oct 2026 at Tumaini Health Centre (Demo).
              Your selected facility recently reported low stock. Other sites with a recent report: Baraka Medical Clinic
              (Westlands). Confirm with the facility before you travel.
            </p>
            <p className="mt-3 text-xs text-slate-500">Example of a simulated demo message. Nothing in that text names a medicine or a condition.</p>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16">
        <div className="grid items-center gap-10 md:grid-cols-2">
          <div>
            <p className="inline-flex items-center gap-2 text-sm font-semibold text-brand-700">
              <Radar className="h-4 w-4" aria-hidden /> Stockout Ripple Alert
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">Spot a possible local shortage before it spreads</h2>
            <p className="mt-3 leading-relaxed text-slate-700">
              When several facilities in the same county report the same medicine low or out of stock within a short window, the system
              raises a <em>potential local shortage signal</em> for administrators and nearby facility teams. Verified data counts more
              than unverified reports, stale data is excluded, and duplicate reports from one facility count once.
            </p>
            <p className="mt-3 text-sm text-slate-500">
              A signal is a prompt to investigate, not a confirmed regional shortage. Stock is never transferred or ordered automatically.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6">
            <p className="text-sm font-medium text-slate-500">How the platform labels availability</p>
            <ul className="mt-4 space-y-3">
              {(['available', 'low', 'out_of_stock', 'stale', 'unknown'] as const).map((s) => (
                <li key={s} className="flex items-start gap-3">
                  <StatusBadge status={s} />
                </li>
              ))}
            </ul>
            <p className="mt-4 flex items-center gap-2 text-xs text-slate-500">
              <Clock className="h-3.5 w-3.5" aria-hidden />
              Reports older than {meta?.fresh_hours ?? 72} hours are shown as stale; older than {meta?.unknown_after_days ?? 30} days as unknown.
            </p>
          </div>
        </div>
      </section>

      <section className="border-t border-slate-200 bg-white">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-16 md:grid-cols-3">
          {[
            { icon: ShieldCheck, title: 'Privacy first', body: 'No diagnoses or prescriptions are collected. Phone numbers are masked in dashboards and USSD sessions store only a keyed hash.' },
            { icon: MessageSquare, title: 'Works on any phone', body: "USSD and SMS through Africa's Talking mean no smartphone, app or mobile data is needed." },
            { icon: Building2, title: 'For facilities', body: 'Inventory, stock movements, thresholds, alerts, staff roles and CSV exports in one place. Public listing begins after approval.' },
          ].map(({ icon: Icon, title, body }) => (
            <div key={title}>
              <Icon className="h-6 w-6 text-brand-700" aria-hidden />
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-slate-600">{body}</p>
            </div>
          ))}
        </div>
        <div className="mx-auto max-w-6xl px-4 pb-16">
          <div className="flex flex-col items-start justify-between gap-4 rounded-2xl bg-brand-50 p-6 md:flex-row md:items-center">
            <div>
              <h2 className="text-lg font-semibold">Run a pharmacy, clinic or hospital?</h2>
              <p className="text-sm text-slate-600">Register your facility. An administrator verifies it before its stock is shown publicly.</p>
            </div>
            <Link to="/register" className="inline-flex h-11 items-center gap-2 rounded-lg bg-brand-700 px-5 font-medium text-white hover:bg-brand-800">
              Register a facility <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
