import { z } from 'zod'

export const KE_PHONE = /^(?:\+?254|0)?(7|1)\d{8}$/

export const phoneSchema = z
  .string()
  .trim()
  .transform((v) => v.replace(/[\s-]/g, ''))
  .refine((v) => KE_PHONE.test(v), 'Enter a valid Kenyan mobile number, e.g. 0712 345 678')

export const optionalPhone = z
  .string()
  .trim()
  .transform((v) => v.replace(/[\s-]/g, ''))
  .refine((v) => v === '' || KE_PHONE.test(v), 'Enter a valid Kenyan mobile number, e.g. 0712 345 678')
