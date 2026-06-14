import { useEffect, useState, useCallback } from 'react'
import { getQueue, approveItem, rejectItem } from '../api/supervisor'
import type { EscalationItem } from '../types'
import SeverityBadge from '../components/SeverityBadge'

interface RejectModalProps {
  item: EscalationItem
  onConfirm: (reason: string) => void
  onCancel: () => void
}

function RejectModal({ item, onConfirm, onCancel }: RejectModalProps) {
  const [reason, setReason] = useState('')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="card w-full max-w-md shadow-xl">
        <h3 className="text-base font-semibold text-gray-900 mb-1">Reject Escalation</h3>
        <p className="text-sm text-gray-500 mb-4">Asset: <span className="font-mono font-medium">{item.asset_id}</span></p>
        <label className="label">Rejection Reason *</label>
        <textarea
          className="input resize-none h-24"
          placeholder="Explain why this escalation is being rejected…"
          value={reason}
          onChange={e => setReason(e.target.value)}
          autoFocus
        />
        <div className="flex justify-end gap-3 mt-4">
          <button onClick={onCancel} className="btn-secondary">Cancel</button>
          <button
            onClick={() => onConfirm(reason)}
            disabled={!reason.trim()}
            className="btn-danger"
          >Confirm Rejection</button>
        </div>
      </div>
    </div>
  )
}

export default function SupervisorPage() {
  const [items, setItems]               = useState<EscalationItem[]>([])
  const [loading, setLoading]           = useState(true)
  const [refreshing, setRefreshing]     = useState(false)
  const [error, setError]               = useState<string | null>(null)
  const [actionError, setActionError]   = useState<string | null>(null)
  const [rejectTarget, setRejectTarget] = useState<EscalationItem | null>(null)
  const [processing, setProcessing]     = useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = useState<'pending' | 'approved' | 'rejected'>('pending')

  const loadQueue = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const q = await getQueue(statusFilter)
      setItems(q.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load queue')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [statusFilter])

  useEffect(() => { loadQueue() }, [loadQueue])

  const handleApprove = async (item: EscalationItem) => {
    setActionError(null)
    setProcessing(p => new Set(p).add(item.id))
    try {
      await approveItem(item.id)
      setItems(prev => prev.filter(i => i.id !== item.id))
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Approve failed')
    } finally {
      setProcessing(p => { const s = new Set(p); s.delete(item.id); return s })
    }
  }

  const handleRejectConfirm = async (reason: string) => {
    if (!rejectTarget) return
    const target = rejectTarget
    setRejectTarget(null)
    setActionError(null)
    setProcessing(p => new Set(p).add(target.id))
    try {
      await rejectItem(target.id, reason)
      setItems(prev => prev.filter(i => i.id !== target.id))
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Reject failed')
    } finally {
      setProcessing(p => { const s = new Set(p); s.delete(target.id); return s })
    }
  }

  const pendingCount = items.filter(i => i.status === 'pending').length

  return (
    <div className="space-y-6">
      {rejectTarget && (
        <RejectModal
          item={rejectTarget}
          onConfirm={handleRejectConfirm}
          onCancel={() => setRejectTarget(null)}
        />
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Supervisor Portal</h1>
          <p className="mt-1 text-sm text-gray-500">Review and resolve AI-escalated service cases.</p>
        </div>
        <button
          onClick={() => loadQueue(true)}
          disabled={refreshing}
          className="btn-secondary"
        >
          {refreshing ? (
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          ) : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          )}
          Refresh
        </button>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-3 gap-4">
        {(['pending', 'approved', 'rejected'] as const).map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`card text-left transition-all ${statusFilter === s ? 'ring-2 ring-blue-500' : 'hover:shadow-md'}`}
          >
            <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider capitalize">{s}</dt>
            <dd className="mt-1 text-2xl font-bold text-gray-900">
              {loading ? '…' : statusFilter === s ? items.length : '—'}
            </dd>
          </button>
        ))}
      </div>

      {actionError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      {/* Queue table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900 capitalize">{statusFilter} Queue</h2>
          {statusFilter === 'pending' && pendingCount > 0 && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
              {pendingCount} requiring action
            </span>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <svg className="animate-spin h-8 w-8 text-blue-400" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          </div>
        ) : error ? (
          <div className="px-6 py-10 text-center">
            <p className="text-sm text-red-600">{error}</p>
            <button onClick={() => loadQueue()} className="btn-secondary mt-4">Retry</button>
          </div>
        ) : items.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <svg className="mx-auto h-12 w-12 text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="mt-3 text-sm text-gray-400">No {statusFilter} items</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-100 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {['Asset ID', 'Facility', 'Severity', 'Summary', 'Escalation Reason', 'Time', 'Actions'].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {items.map(item => (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono font-medium text-gray-900 whitespace-nowrap">{item.asset_id}</td>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{item.facility_id}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <SeverityBadge severity={item.severity} size="sm" />
                    </td>
                    <td className="px-4 py-3 text-gray-700 max-w-xs">
                      <p className="line-clamp-2">{item.diagnosis_summary}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-500 max-w-xs">
                      <p className="line-clamp-2">{item.escalation_reason}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap text-xs">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {item.status === 'pending' ? (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleApprove(item)}
                            disabled={processing.has(item.id)}
                            className="btn-success"
                          >Approve</button>
                          <button
                            onClick={() => setRejectTarget(item)}
                            disabled={processing.has(item.id)}
                            className="btn-danger"
                          >Reject</button>
                        </div>
                      ) : (
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          item.status === 'approved'
                            ? 'bg-green-50 text-green-700 ring-1 ring-green-200'
                            : 'bg-gray-100 text-gray-500 ring-1 ring-gray-200'
                        }`}>
                          {item.status}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
