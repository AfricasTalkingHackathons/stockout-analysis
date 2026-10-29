import { Search } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { api } from '../lib/api'
import { useDebounced } from '../lib/hooks'
import type { Medicine, Page } from '../lib/types'

interface Props {
  value: Medicine | null
  onChange: (m: Medicine | null) => void
  label?: string
  id?: string
  placeholder?: string
  longTerm?: boolean
}

export function MedicinePicker({
  value,
  onChange,
  label = 'Medicine',
  placeholder = 'e.g. amoxicillin, Panadol, metformin',
  longTerm = false,
}: Props) {
  const [text, setText] = useState(value?.display_name ?? '')
  const [options, setOptions] = useState<Medicine[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const q = useDebounced(text, 200)
  const id = useId()

  useEffect(() => {
    setText(value?.display_name ?? '')
  }, [value])

  useEffect(() => {
    if (!open || q.trim().length < 2 || q === value?.display_name) {
      setOptions([])
      return
    }
    let live = true
    api
      .get<Page<Medicine>>('/api/medicines', { q: q.trim(), page_size: 8, long_term: longTerm || undefined })
      .then((r) => live && (setOptions(r.items), setActive(0)))
      .catch(() => live && setOptions([]))
    return () => {
      live = false
    }
  }, [q, open, value, longTerm])

  const choose = (m: Medicine) => {
    onChange(m)
    setText(m.display_name)
    setOpen(false)
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-800">
        {label}
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <input
          id={id}
          role="combobox"
          aria-expanded={open && options.length > 0}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          autoComplete="off"
          className="block h-11 w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
          placeholder={placeholder}
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setOpen(true)
            if (value) onChange(null)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (!options.length) return
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => Math.min(a + 1, options.length - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => Math.max(a - 1, 0))
            } else if (e.key === 'Enter') {
              e.preventDefault()
              choose(options[active])
            }
          }}
        />
      </div>
      {open && options.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="absolute z-[600] mt-1 max-h-72 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          {options.map((m, i) => (
            <li
              key={m.id}
              role="option"
              aria-selected={i === active}
              className={`cursor-pointer px-3 py-2 text-sm ${i === active ? 'bg-brand-50' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(m)
              }}
            >
              <span className="font-medium text-ink">{m.generic_name}</span>{' '}
              <span className="text-slate-600">
                {m.strength} {m.dosage_form}
              </span>
              {m.brand_names.length > 0 && <span className="block text-xs text-slate-500">Also known as: {m.brand_names.join(', ')}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
