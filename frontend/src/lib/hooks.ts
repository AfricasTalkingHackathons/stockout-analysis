import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api'

export interface AsyncState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  reload: () => void
}

/** Runs `fn` whenever `deps` change; ignores stale responses. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const seq = useRef(0)

  useEffect(() => {
    const id = ++seq.current
    setLoading(true)
    setError(null)
    fn()
      .then((d) => {
        if (id === seq.current) setData(d)
      })
      .catch((e: unknown) => {
        if (id === seq.current) setError(e instanceof ApiError ? e : new ApiError(0, 'error', String(e)))
      })
      .finally(() => {
        if (id === seq.current) setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, error, loading, reload }
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}
