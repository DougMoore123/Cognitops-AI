import { get, post } from './client'
import type { EscalationItem } from '../types'

export interface QueueResponse {
  items: EscalationItem[]
  total: number
}

export async function getQueue(status = 'pending'): Promise<QueueResponse> {
  return get<QueueResponse>(`/supervisor/queue?status=${encodeURIComponent(status)}`)
}

export async function approveItem(id: string, notes?: string): Promise<EscalationItem> {
  return post<EscalationItem>(`/supervisor/queue/${encodeURIComponent(id)}/approve`, { notes })
}

export async function rejectItem(id: string, reason: string): Promise<EscalationItem> {
  return post<EscalationItem>(`/supervisor/queue/${encodeURIComponent(id)}/reject`, { reason })
}
