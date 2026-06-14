import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getCase } from '../api/cases'
import type { CaseResponse } from '../types'
import SeverityBadge from '../components/SeverityBadge'

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const [caseData, setCaseData] = useState<CaseResponse | null>(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)

  useEffect(() => {
    if (!caseId) return
    getCase(caseId)
      .then(setCaseData)
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load case'))
      .finally(() => setLoading(false))
  }, [caseId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <svg className="animate-spin h-8 w-8 text-blue-500" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      </div>
    )
  }

  if (error || !caseData) {
    return (
      <div className="card bg-red-50 border-red-200 text-red-700">
        <p className="font-medium">Error loading case</p>
        <p className="text-sm mt-1">{error ?? 'Case not found'}</p>
        <button onClick={() => navigate('/operator')} className="btn-secondary mt-4">← Back</button>
      </div>
    )
  }

  const { diagnosis, adjusted_severity } = caseData

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/operator')} className="btn-secondary">← Back</button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Case Detail</h1>
          <p className="text-sm text-gray-400 font-mono">{caseData.case_id}</p>
        </div>
        {adjusted_severity && <div className="ml-auto"><SeverityBadge severity={adjusted_severity} size="lg" /></div>}
      </div>

      {/* Meta */}
      <div className="card">
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Asset ID',    value: caseData.asset_id },
            { label: 'Status',      value: caseData.status },
            { label: 'Submitted',   value: new Date(caseData.created_at).toLocaleString() },
            { label: 'Confidence',  value: diagnosis ? `${(diagnosis.confidence_level * 100).toFixed(0)}%` : '—' },
          ].map(({ label, value }) => (
            <div key={label}>
              <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</dt>
              <dd className="mt-1 text-sm font-semibold text-gray-900">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      {caseData.status === 'processing' && (
        <div className="card bg-blue-50 border-blue-100 flex items-center gap-3 text-blue-700">
          <svg className="animate-spin h-5 w-5 shrink-0" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span className="text-sm font-medium">Diagnosis in progress…</span>
        </div>
      )}

      {caseData.status === 'failed' && (
        <div className="card bg-red-50 border-red-100 text-red-700">
          <p className="font-medium">Diagnosis failed</p>
          <p className="text-sm mt-1">{caseData.error ?? 'An unexpected error occurred.'}</p>
        </div>
      )}

      {diagnosis && (
        <>
          {/* Safety warning */}
          {diagnosis.safety_warning && (
            <div className="card bg-orange-50 border-orange-200">
              <div className="flex items-start gap-3">
                <svg className="h-5 w-5 text-orange-500 shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <div>
                  <p className="text-sm font-semibold text-orange-800">Safety Warning</p>
                  <p className="text-sm text-orange-700 mt-1">{diagnosis.safety_warning}</p>
                </div>
              </div>
            </div>
          )}

          {/* Diagnosis */}
          <div className="card">
            <h2 className="text-base font-semibold text-gray-900 mb-3">Diagnosis Summary</h2>
            <p className="text-sm text-gray-700 leading-relaxed">{diagnosis.diagnosis_summary}</p>
          </div>

          {/* Recommended action */}
          <div className="card">
            <h2 className="text-base font-semibold text-gray-900 mb-3">Recommended Action</h2>
            <p className="text-sm text-gray-700 leading-relaxed">{diagnosis.recommended_action}</p>
          </div>

          {/* RAG sources */}
          {diagnosis.rag_sources.length > 0 && (
            <div className="card">
              <h2 className="text-base font-semibold text-gray-900 mb-3">Knowledge Sources</h2>
              <ul className="space-y-1">
                {diagnosis.rag_sources.map((src, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm text-gray-600">
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-400 shrink-0" />
                    {src}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Escalation indicator */}
          {diagnosis.escalation_required && (
            <div className="card bg-red-50 border-red-200 flex items-center gap-3">
              <svg className="h-5 w-5 text-red-500 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2.003 5.884L10 9.882l7.997-3.998A2 2 0 0016 4H4a2 2 0 00-1.997 1.884z" />
                <path d="M18 8.118l-8 4-8-4V14a2 2 0 002 2h12a2 2 0 002-2V8.118z" />
              </svg>
              <div>
                <p className="text-sm font-semibold text-red-800">Escalation Required</p>
                <p className="text-xs text-red-600">This case has been routed to the supervisor queue for review.</p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
