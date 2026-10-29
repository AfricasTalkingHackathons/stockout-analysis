import { MessageSquare, Phone, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { DeliveryStatusPill } from '../../components/StatusBadge'
import { Button, Card, Field, Input, Notice } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { useAuth } from '../../lib/auth'

interface SimResponse {
  response: string
  continue: boolean
  text: string
  sms: { id: string; status: string; message: string; recipient: string }[]
}

function newSession() {
  return Math.random().toString(36).slice(2, 10)
}

export default function UssdSimulator() {
  const { meta } = useAuth()
  const [phone, setPhone] = useState('0712000111')
  const [session, setSession] = useState(newSession)
  const [inputs, setInputs] = useState<string[]>([])
  const [screen, setScreen] = useState<SimResponse | null>(null)
  const [entry, setEntry] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const send = async (path: string[], sess: string = session) => {
    setBusy(true)
    setError(null)
    try {
      const r = await api.post<SimResponse>('/api/simulator/ussd', { session_id: sess, phone, text: path.join('*') })
      setScreen(r)
      setInputs(path)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Simulator unavailable')
    } finally {
      setBusy(false)
      setEntry('')
      inputRef.current?.focus()
    }
  }

  const dial = () => {
    const s = newSession()
    setSession(s)
    setInputs([])
    setScreen(null)
    send([], s)
  }

  useEffect(() => {
    send([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (meta && !meta.demo_mode)
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        <Notice tone="info" title="USSD access">
          {meta.ussd_service_code ? `Dial ${meta.ussd_service_code} from any phone.` : 'USSD is being configured.'}
        </Notice>
      </div>
    )

  return (
    <div className="mx-auto grid max-w-5xl gap-8 px-4 py-10 md:grid-cols-[360px_1fr]">
      <div>
        <div className="mx-auto w-full max-w-[340px] rounded-[2.5rem] bg-slate-900 p-4 shadow-2xl">
          <div className="rounded-[1.75rem] bg-slate-800 p-3">
            <div className="mb-2 flex items-center justify-between px-1 text-[10px] text-slate-400">
              <span>SIMULATED · Safaricom</span>
              <span>{phone}</span>
            </div>
            <div className="min-h-[260px] rounded-xl bg-[#d9e6d2] p-3 font-mono text-[13px] leading-snug text-slate-900" aria-live="polite">
              {busy && !screen ? 'Running USSD code…' : screen ? <pre className="whitespace-pre-wrap font-mono">{screen.text}</pre> : null}
              {screen && !screen.continue && <p className="mt-3 border-t border-slate-500/30 pt-2 text-[11px] text-slate-600">Session ended.</p>}
            </div>
            <form
              className="mt-3 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                if (screen?.continue && entry.trim()) send([...inputs, entry.trim()])
              }}
            >
              <label htmlFor="ussd-entry" className="sr-only">
                Reply
              </label>
              <input
                id="ussd-entry"
                ref={inputRef}
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
                disabled={!screen?.continue || busy}
                className="h-11 min-w-0 flex-1 rounded-lg bg-slate-100 px-3 font-mono text-sm disabled:opacity-50"
                placeholder={screen?.continue ? 'Type reply' : ''}
                autoComplete="off"
              />
              <button type="submit" disabled={!screen?.continue || busy} className="h-11 rounded-lg bg-emerald-600 px-4 text-sm font-semibold text-white disabled:opacity-50">
                Send
              </button>
            </form>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {['1', '2', '3', '4', '9', '0'].map((k) => (
                <button
                  key={k}
                  disabled={!screen?.continue || busy}
                  onClick={() => send([...inputs, k])}
                  className="h-10 rounded-lg bg-slate-700 font-mono text-white hover:bg-slate-600 disabled:opacity-40"
                >
                  {k}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="space-y-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">USSD for basic phones</h1>
          <p className="mt-1 text-sm text-slate-600">
            This simulator sends exactly the same requests Africa's Talking would send to <code>/api/webhooks/ussd</code>, and runs the same
            backend logic. Nothing is sent to a real phone network.
          </p>
        </div>
        <Notice tone="info" title="Simulated session">
          Session <code>SIM-{session}</code> · input so far: <code>{inputs.join('*') || '(empty)'}</code>
        </Notice>
        <Card className="space-y-4 p-5">
          <Field label="Simulated caller number">
            {(id) => <Input id={id} value={phone} inputMode="tel" onChange={(e) => setPhone(e.target.value)} />}
          </Field>
          <Button variant="outline" onClick={dial}>
            <Phone className="h-4 w-4" aria-hidden /> Dial again (new session)
          </Button>
          {error && <Notice tone="danger">{error}</Notice>}
        </Card>
        {screen && screen.sms.length > 0 && (
          <Card className="p-5">
            <h2 className="flex items-center gap-2 font-semibold">
              <MessageSquare className="h-4 w-4 text-brand-700" aria-hidden /> SMS triggered by this session
            </h2>
            {screen.sms.map((s) => (
              <div key={s.id} className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-xs text-slate-500">To {s.recipient}</span>
                  <DeliveryStatusPill status={s.status} />
                </div>
                {s.message}
              </div>
            ))}
          </Card>
        )}
        <Card className="p-5 text-sm text-slate-700">
          <h2 className="font-semibold text-ink">Try this</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5">
            <li>Press 1 (Find medicine), choose Nairobi, type “amoxicillin”.</li>
            <li>Choose a facility to see its status and last update, then press 1 to request an SMS.</li>
            <li>Dial again and press 2 to report a medicine unavailable. You get a reference number.</li>
          </ol>
          <button className="mt-3 inline-flex items-center gap-1 text-brand-700 underline" onClick={dial}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden /> Restart
          </button>
        </Card>
      </div>
    </div>
  )
}
