import type { NotifyResult } from '../api/types'

export type NotificationRow = {
  channel: string
  status: string
  message: string
  at: string
}

const RETRY_PATTERNS: RegExp[] = [
  /\bretry(?:ing|ied)?\b/i,
  /\battempt\s*\d+\s*(?:\/|of)\s*\d+\b/i,
  /\[retry\]/i,
]

export function isRetryMessage(message: string): boolean {
  const value = message.trim()
  if (!value) return false
  return RETRY_PATTERNS.some((pattern) => pattern.test(value))
}

export function classifyFailureReason(message: string): string {
  const m = message.toLowerCase()
  if (/\b(auth|unauthorized|forbidden|credential|invalid api key)\b/.test(m)) return 'Auth Failure'
  if (/\b(timeout|timed out|deadline exceeded|socket hang up)\b/.test(m)) return 'Timeout'
  if (/\b(recipient|mailbox|invalid email|email address|rcpt)\b/.test(m)) return 'Invalid Recipient'
  if (/\b(webhook)\b/.test(m) && /\b(invalid|not found|malformed|404|410)\b/.test(m)) return 'Invalid Webhook'
  return 'Other Delivery Errors'
}

export function flattenNotificationRows(history: NotifyResult[]): NotificationRow[] {
  return history.flatMap((entry) =>
    (entry.results ?? []).map((res) => ({
      channel: String(res.channel ?? '').toLowerCase(),
      status: String(res.status ?? '').toLowerCase(),
      message: (res.message ?? '').trim(),
      at: res.sent_at ?? entry.generated_at,
    }))
  )
}
