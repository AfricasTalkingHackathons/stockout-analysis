import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { Button, Card, Field, Input, Notice } from '../../components/ui'
import { ApiError } from '../../lib/api'
import { useAuth } from '../../lib/auth'

const schema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
})
type Values = z.infer<typeof schema>

const DEMO_ACCOUNTS = [
  { email: 'admin@demo.stockout.example', role: 'System administrator' },
  { email: 'pharmacist.mwangaza@demo.stockout.example', role: 'Facility administrator (Mwangaza)' },
  { email: 'staff.mwangaza@demo.stockout.example', role: 'Facility staff (Mwangaza)' },
  { email: 'admin.baraka@demo.stockout.example', role: 'Facility administrator (Baraka)' },
]

export default function Login() {
  const { login, user, meta } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, setValue, formState } = useForm<Values>({ resolver: zodResolver(schema) })
  if (user) return <Navigate to="/app" replace />
  const from = (location.state as { from?: string } | null)?.from ?? '/app'

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <Card className="p-6">
        <h1 className="text-xl font-semibold">Sign in</h1>
        <p className="mt-1 text-sm text-slate-600">For facility staff and administrators.</p>
        <form
          noValidate
          className="mt-6 space-y-4"
          onSubmit={handleSubmit(async (v) => {
            setError(null)
            try {
              await login(v.email, v.password)
              navigate(from, { replace: true })
            } catch (e) {
              setError(e instanceof ApiError ? e.message : 'Sign in failed')
            }
          })}
        >
          <Field label="Email" error={formState.errors.email?.message}>
            {(id, d) => <Input id={id} type="email" autoComplete="username" aria-describedby={d} aria-invalid={!!formState.errors.email} {...register('email')} />}
          </Field>
          <Field label="Password" error={formState.errors.password?.message}>
            {(id, d) => <Input id={id} type="password" autoComplete="current-password" aria-describedby={d} aria-invalid={!!formState.errors.password} {...register('password')} />}
          </Field>
          {error && <Notice tone="danger">{error}</Notice>}
          <Button type="submit" className="w-full" loading={formState.isSubmitting}>
            Sign in
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-600">
          New facility? <Link to="/register" className="text-brand-700 underline">Register here</Link>
        </p>
      </Card>
      {meta?.demo_mode && (
        <Card className="mt-4 p-5">
          <h2 className="text-sm font-semibold">Demo accounts</h2>
          <p className="mt-1 text-xs text-slate-600">
            Fictional accounts for the demonstration. The password is set by <code>DEMO_PASSWORD</code> (default documented in the README).
          </p>
          <ul className="mt-3 space-y-1.5">
            {DEMO_ACCOUNTS.map((a) => (
              <li key={a.email}>
                <button type="button" className="w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-slate-50" onClick={() => setValue('email', a.email)}>
                  <span className="block font-medium text-ink">{a.role}</span>
                  <span className="text-xs text-slate-500">{a.email}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
