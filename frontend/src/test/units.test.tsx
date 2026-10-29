import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DeliveryStatusPill, StatusBadge } from '../components/StatusBadge'
import { qs } from '../lib/api'
import { timeAgo } from '../lib/format'
import { phoneSchema } from '../lib/validation'

describe('StatusBadge', () => {
  it('labels every availability category with text, not just colour', () => {
    const labels = {
      available: 'Reported available',
      low: 'Reported low stock',
      out_of_stock: 'Reported out of stock',
      stale: 'Stale: needs confirmation',
      unknown: 'Unknown: no recent report',
    }
    for (const [status, label] of Object.entries(labels)) {
      render(<StatusBadge status={status} />)
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('falls back to unknown for unexpected values', () => {
    render(<StatusBadge status="weird" />)
    expect(screen.getByText(/Unknown/)).toBeInTheDocument()
  })
})

describe('DeliveryStatusPill', () => {
  it('never presents simulated or accepted messages as delivered', () => {
    render(
      <>
        <DeliveryStatusPill status="simulated" />
        <DeliveryStatusPill status="accepted" />
      </>,
    )
    expect(screen.getByText('Simulated (not sent)')).toBeInTheDocument()
    expect(screen.getByText('Accepted by provider')).toBeInTheDocument()
    expect(screen.queryByText('Delivered')).toBeNull()
  })
})

describe('helpers', () => {
  it('builds query strings without empty values', () => {
    expect(qs({ a: 1, b: '', c: null, d: undefined, e: 'x y' })).toBe('?a=1&e=x+y')
    expect(qs({})).toBe('')
  })

  it('formats relative times', () => {
    const now = new Date('2026-10-29T12:00:00Z')
    expect(timeAgo('2026-10-29T11:59:30Z', now)).toBe('just now')
    expect(timeAgo('2026-10-29T09:00:00Z', now)).toBe('3 h ago')
    expect(timeAgo('2026-10-27T12:00:00Z', now)).toBe('2 days ago')
    expect(timeAgo(null, now)).toBe('never')
  })

  it('validates Kenyan mobile numbers', () => {
    expect(phoneSchema.safeParse('0712 345 678').success).toBe(true)
    expect(phoneSchema.safeParse('+254112345678').success).toBe(true)
    expect(phoneSchema.safeParse('12345').success).toBe(false)
    expect(phoneSchema.safeParse('+1 555 123 4567').success).toBe(false)
  })
})
