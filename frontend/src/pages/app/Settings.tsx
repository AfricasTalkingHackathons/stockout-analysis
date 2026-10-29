import { CheckCircle2, MessageSquare, Play, RotateCcw, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Pill } from '../../components/StatusBadge'
import { Button, Card, CardHeader, ErrorState, Field, Input, Notice, PageHeader, Spinner, Table, Td, Th } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { formatDateTime, humanize, timeAgo } from '../../lib/format'
import { useAsync } from '../../lib/hooks'

interface Integrations {
  demo_mode: boolean
  sms_mode: string
  africastalking: {
    credentials_configured: boolean
    username: string | null
    environment: string
    sender_id_configured: boolean
    webhook_token_configured: boolean
    ip_allowlist_configured: boolean
    ussd_service_code: string | null
    demo_sms_allowlist_count: number
  }
  callbacks: Record<string, string>
  scheduler_enabled: boolean
}

interface ConfigRow {
  key: string
  value: number
  default: number
  description: string
  minimum: number
  maximum: number
}

interface Freshness {
  fresh_hours: number
  facilities: { facility_id: string; name: string; code: string; is_demo: boolean; items: number; stale_items: number; oldest_update: string | null; latest_update: string | null }[]
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      {ok ? <CheckCircle2 className="h-4 w-4 text-emerald-700" aria-hidden /> : <XCircle className="h-4 w-4 text-slate-400" aria-hidden />}
      <span className={ok ? '' : 'text-slate-500'}>{label}</span>
      <span className="sr-only">{ok ? 'configured' : 'not configured'}</span>
    </li>
  )
}

export default function Settings() {
  const { refreshMeta } = useAuth()
  const integ = useAsync(() => api.get<Integrations>('/api/admin/integrations'), [])
  const cfg = useAsync(() => api.get<ConfigRow[]>('/api/admin/config'), [])
  const fresh = useAsync(() => api.get<Freshness>('/api/admin/freshness'), [])
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<{ tone: 'success' | 'danger' | 'info'; text: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const run = async (key: string, fn: () => Promise<string>) => {
    setBusy(key)
    setMsg(null)
    try {
      setMsg({ tone: 'success', text: await fn() })
    } catch (e) {
      setMsg({ tone: 'danger', text: e instanceof ApiError ? e.message : 'Failed' })
    } finally {
      setBusy(null)
    }
  }
  const origin = window.location.origin

  return (
    <div>
      <PageHeader title="Settings & integrations" description="Integration status, alert rules and demonstration controls." />
      {msg && (
        <div className="mb-4">
          <Notice tone={msg.tone}>{msg.text}</Notice>
        </div>
      )}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Africa's Talking" subtitle="Credentials are read from server environment variables and never shown here." />
          {integ.loading && <Spinner />}
          <ErrorState error={integ.error} />
          {integ.data && (
            <div className="space-y-4 p-5">
              <div className="flex flex-wrap gap-2">
                <Pill tone={integ.data.sms_mode.startsWith('live') ? 'green' : 'violet'}>SMS mode: {integ.data.sms_mode}</Pill>
                {integ.data.demo_mode && <Pill tone="violet">Demo mode on</Pill>}
                <Pill>Scheduler {integ.data.scheduler_enabled ? 'on' : 'off'}</Pill>
              </div>
              <ul className="space-y-1.5">
                <Check ok={integ.data.africastalking.credentials_configured} label={`API credentials (username: ${integ.data.africastalking.username ?? 'not set'}, ${integ.data.africastalking.environment})`} />
                <Check ok={integ.data.africastalking.sender_id_configured} label="Approved sender ID configured" />
                <Check ok={integ.data.africastalking.webhook_token_configured} label="Webhook token configured (required outside demo mode)" />
                <Check ok={integ.data.africastalking.ip_allowlist_configured} label="Callback IP allowlist" />
                <Check ok={!!integ.data.africastalking.ussd_service_code} label={`USSD service code ${integ.data.africastalking.ussd_service_code ?? '(not set)'}`} />
                {integ.data.demo_mode && (
                  <Check ok={integ.data.africastalking.demo_sms_allowlist_count > 0} label={`${integ.data.africastalking.demo_sms_allowlist_count} number(s) allowed to receive live SMS in demo mode`} />
                )}
              </ul>
              <div>
                <p className="text-sm font-medium">Callback URLs to set in the Africa's Talking dashboard</p>
                <ul className="mt-2 space-y-1 text-xs">
                  {Object.entries(integ.data.callbacks).map(([k, v]) => (
                    <li key={k}>
                      <span className="text-slate-500">{humanize(k)}:</span> <code className="break-all">{'<API base URL>'}{v}</code>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-slate-500">The API base URL is your backend's public HTTPS address (this page is served from {origin}).</p>
              </div>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Operations" />
          <div className="space-y-4 p-5">
            <div>
              <Button
                variant="secondary"
                loading={busy === 'jobs'}
                onClick={() =>
                  run('jobs', async () => {
                    const r = await api.post<Record<string, number>>('/api/admin/jobs/run')
                    fresh.reload()
                    return `Checks complete: ${r.stale} stale facility alert(s), ${r.expiring} expiry alert(s), ${r.escalated} escalation(s), ${r.dispatched} message(s) dispatched.`
                  })
                }
              >
                <Play className="h-4 w-4" aria-hidden /> Run scheduled checks now
              </Button>
              <p className="mt-1 text-xs text-slate-500">Stale-report requests, expiry warnings, escalation and SMS retries normally run in the background.</p>
            </div>
            <div>
              <Button
                variant="outline"
                loading={busy === 'ripple'}
                onClick={() =>
                  run('ripple', async () => {
                    const r = await api.post<{ evaluated: number; created: string[] }>('/api/admin/ripple/scan')
                    return `Ripple scan evaluated ${r.evaluated} medicine/county pairs; ${r.created.length} new signal(s).`
                  })
                }
              >
                Re-scan ripple signals
              </Button>
            </div>
            {integ.data?.demo_mode && (
              <div className="rounded-lg border border-violet-200 bg-violet-50 p-4">
                <p className="text-sm font-semibold text-violet-900">Demo data</p>
                <p className="mt-1 text-xs text-violet-900">
                  Restores the fictional “(Demo)” facilities, stock and alerts to the starting scenario. Real facilities, users and audit logs are not touched.
                </p>
                <Button
                  className="mt-3"
                  variant="outline"
                  loading={busy === 'reset'}
                  onClick={() =>
                    window.confirm('Reset all demo data to the starting scenario?') &&
                    run('reset', async () => {
                      const r = await api.post<Record<string, number>>('/api/admin/demo/reset')
                      refreshMeta()
                      fresh.reload()
                      return `Demo reset: ${r.facilities} facilities and ${r.inventory_items} inventory records restored.`
                    })
                  }
                >
                  <RotateCcw className="h-4 w-4" aria-hidden /> Reset demo data
                </Button>
              </div>
            )}
          </div>
        </Card>
      </div>

      {integ.data?.demo_mode && <InboundSmsSimulator />}

      <Card className="mt-6">
        <CardHeader title="Alert rules and freshness thresholds" subtitle="Changes take effect immediately and are audited." />
        {cfg.data && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              const values = Object.fromEntries(Object.entries(edits).map(([k, v]) => [k, Number(v)]))
              if (!Object.keys(values).length) return
              run('cfg', async () => {
                await api.put('/api/admin/config', { values })
                setEdits({})
                cfg.reload()
                refreshMeta()
                return 'Settings saved.'
              })
            }}
          >
            <Table>
              <thead className="bg-slate-50">
                <tr>
                  <Th>Setting</Th>
                  <Th>Value</Th>
                  <Th>Default</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {cfg.data.map((c) => (
                  <tr key={c.key}>
                    <Td>
                      <span className="font-medium text-ink">{humanize(c.key)}</span>
                      <span className="block text-xs text-slate-500">{c.description}</span>
                    </Td>
                    <Td>
                      <Input
                        aria-label={humanize(c.key)}
                        type="number"
                        step="any"
                        min={c.minimum}
                        max={c.maximum}
                        className="w-28"
                        value={edits[c.key] ?? String(c.value)}
                        onChange={(e) => setEdits((s) => ({ ...s, [c.key]: e.target.value }))}
                      />
                    </Td>
                    <Td className="text-xs text-slate-500">{c.default}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="p-4">
              <Button type="submit" loading={busy === 'cfg'} disabled={!Object.keys(edits).length}>
                Save changes
              </Button>
            </div>
          </form>
        )}
      </Card>

      <Card className="mt-6">
        <CardHeader title="Data freshness by facility" subtitle={fresh.data ? `Records older than ${fresh.data.fresh_hours} h are stale.` : undefined} />
        {fresh.data && (
          <Table>
            <thead className="bg-slate-50">
              <tr>
                <Th>Facility</Th>
                <Th className="text-right">Records</Th>
                <Th className="text-right">Stale</Th>
                <Th>Oldest update</Th>
                <Th>Latest update</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {fresh.data.facilities.map((f) => (
                <tr key={f.facility_id}>
                  <Td>
                    {f.name} <span className="text-xs text-slate-500">{f.code}</span>
                  </Td>
                  <Td className="text-right tabular-nums">{f.items}</Td>
                  <Td className={`text-right tabular-nums ${f.stale_items ? 'font-semibold text-amber-800' : ''}`}>{f.stale_items}</Td>
                  <Td className="text-xs">{f.oldest_update ? `${formatDateTime(f.oldest_update)} (${timeAgo(f.oldest_update)})` : 'n/a'}</Td>
                  <Td className="text-xs">{f.latest_update ? timeAgo(f.latest_update) : 'n/a'}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  )
}

function InboundSmsSimulator() {
  const [phone, setPhone] = useState('+254700000011')
  const [text, setText] = useState('STOCK MED001 12')
  const [res, setRes] = useState<{ outcome: string; reply: string | null; message_id: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <Card className="mt-6">
      <CardHeader
        title="Inbound SMS simulator"
        subtitle="Runs the same handler as the /api/webhooks/sms callback. Demo staff numbers: Mwangaza +254700000011, Tumaini +254700000021, Baraka +254700000031."
      />
      <form
        className="grid gap-3 p-5 md:grid-cols-[1fr_2fr_auto] md:items-end"
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          setError(null)
          try {
            setRes(await api.post('/api/simulator/sms', { phone, text }))
          } catch (err) {
            setError(err instanceof ApiError ? err.message : 'Failed')
          } finally {
            setBusy(false)
          }
        }}
      >
        <Field label="From (sender number)">{(id) => <Input id={id} value={phone} onChange={(e) => setPhone(e.target.value)} />}</Field>
        <Field label="Message text">{(id) => <Input id={id} value={text} onChange={(e) => setText(e.target.value)} className="font-mono" />}</Field>
        <Button type="submit" loading={busy}>
          <MessageSquare className="h-4 w-4" aria-hidden /> Simulate SMS
        </Button>
      </form>
      {(res || error) && (
        <div className="px-5 pb-5">
          {error && <Notice tone="danger">{error}</Notice>}
          {res && (
            <Notice tone={res.outcome === 'recorded' ? 'success' : 'warning'} title={`Outcome: ${humanize(res.outcome)} (simulated)`}>
              Reply: {res.reply ?? 'n/a'}
            </Notice>
          )}
        </div>
      )}
    </Card>
  )
}
