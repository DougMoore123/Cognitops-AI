import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { submitCase, pollCase } from '../api/cases'
import type { CaseResponse } from '../types'
import SeverityBadge from '../components/SeverityBadge'

interface CaseEntry {
  case_id: string
  asset_id: string
  status: CaseResponse['status']
  adjusted_severity?: CaseResponse['adjusted_severity']
  created_at: string
}

export default function OperatorPage() {
  const navigate = useNavigate()

  // Form state
  const [assetId, setAssetId]             = useState('')
  const [location, setLocation]           = useState('')
  const [description, setDescription]     = useState('')
  const [imageFile, setImageFile]         = useState<File | null>(null)
  const [imagePreview, setImagePreview]   = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // Submission state
  const [submitting, setSubmitting]       = useState(false)
  const [statusMsg, setStatusMsg]         = useState('')
  const [error, setError]                 = useState<string | null>(null)

  // Recent cases (session only — page refresh clears this)
  const [cases, setCases] = useState<CaseEntry[]>([])

  const handleImage = (file: File | null) => {
    setImageFile(file)
    if (file) {
      const reader = new FileReader()
      reader.onload = (e) => setImagePreview(e.target?.result as string)
      reader.readAsDataURL(file)
    } else {
      setImagePreview(null)
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('image/')) handleImage(file)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!assetId.trim() || !description.trim()) return
    setError(null)
    setSubmitting(true)
    setStatusMsg('Submitting case...')

    try {
      const created = await submitCase({
        asset_id: assetId.trim(),
        location: location.trim(),
        symptom_description: description.trim(),
        image: imageFile,
      })

      setStatusMsg('Case submitted — running diagnosis...')
      setCases(prev => [{
        case_id: created.case_id,
        asset_id: created.asset_id,
        status: created.status,
        created_at: created.created_at,
      }, ...prev])

      const final = await pollCase(
        created.case_id,
        (update) => {
          setCases(prev => prev.map(c =>
            c.case_id === update.case_id
              ? { ...c, status: update.status, adjusted_severity: update.adjusted_severity }
              : c
          ))
        }
      )

      setCases(prev => prev.map(c =>
        c.case_id === final.case_id
          ? { ...c, status: final.status, adjusted_severity: final.adjusted_severity }
          : c
      ))
      setStatusMsg('')
      // Reset form
      setAssetId(''); setLocation(''); setDescription('')
      setImageFile(null); setImagePreview(null)

      // Navigate to the case detail
      navigate(`/operator/cases/${final.case_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setStatusMsg('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Operator Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">Submit a field service case for AI-powered diagnosis.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        {/* ── Submission form ── */}
        <div className="lg:col-span-3">
          <div className="card">
            <h2 className="text-base font-semibold text-gray-900 mb-5">New Case</h2>
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Asset ID *</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="e.g. ASSET-001"
                    value={assetId}
                    onChange={e => setAssetId(e.target.value)}
                    required
                    disabled={submitting}
                  />
                </div>
                <div>
                  <label className="label">Location / Zone</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="e.g. Plant A – Bay 3"
                    value={location}
                    onChange={e => setLocation(e.target.value)}
                    disabled={submitting}
                  />
                </div>
              </div>

              <div>
                <label className="label">Symptom Description *</label>
                <textarea
                  className="input resize-none h-28"
                  placeholder="Describe what the technician observed…"
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  required
                  disabled={submitting}
                />
              </div>

              {/* Image drop zone */}
              <div>
                <label className="label">Equipment Photo (optional)</label>
                <div
                  onDrop={handleDrop}
                  onDragOver={e => e.preventDefault()}
                  onClick={() => fileRef.current?.click()}
                  className={`relative border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors duration-150
                    ${imagePreview ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}`}
                >
                  {imagePreview ? (
                    <div className="flex items-center gap-4">
                      <img src={imagePreview} alt="preview" className="h-20 w-20 object-cover rounded-lg border border-gray-200" />
                      <div className="text-left">
                        <p className="text-sm font-medium text-gray-700">{imageFile?.name}</p>
                        <p className="text-xs text-gray-400">{imageFile ? (imageFile.size / 1024).toFixed(1) + ' KB' : ''}</p>
                        <button
                          type="button"
                          className="mt-1 text-xs text-red-500 hover:text-red-700"
                          onClick={e => { e.stopPropagation(); handleImage(null) }}
                        >Remove</button>
                      </div>
                    </div>
                  ) : (
                    <div className="py-4">
                      <svg className="mx-auto h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      <p className="mt-2 text-sm text-gray-500">Drag & drop or <span className="text-blue-600 underline">browse</span></p>
                      <p className="text-xs text-gray-400">PNG, JPG, WEBP up to 10 MB</p>
                    </div>
                  )}
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={e => handleImage(e.target.files?.[0] ?? null)}
                  />
                </div>
              </div>

              {error && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <button type="submit" disabled={submitting || !assetId.trim() || !description.trim()} className="btn-primary w-full justify-center">
                {submitting ? (
                  <>
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    {statusMsg || 'Processing…'}
                  </>
                ) : 'Submit Case'}
              </button>
            </form>
          </div>
        </div>

        {/* ── Recent cases sidebar ── */}
        <div className="lg:col-span-2">
          <div className="card h-full">
            <h2 className="text-base font-semibold text-gray-900 mb-4">Recent Cases</h2>
            {cases.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-8">No cases submitted this session.</p>
            ) : (
              <ul className="divide-y divide-gray-100 space-y-0">
                {cases.map(c => (
                  <li key={c.case_id} className="py-3 flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 truncate">{c.asset_id}</p>
                      <p className="text-xs text-gray-400 font-mono">{c.case_id.slice(0, 8)}…</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {c.adjusted_severity ? (
                        <SeverityBadge severity={c.adjusted_severity} size="sm" />
                      ) : (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          c.status === 'processing' ? 'bg-blue-50 text-blue-600 ring-1 ring-blue-200'
                          : c.status === 'failed'   ? 'bg-red-50 text-red-600 ring-1 ring-red-200'
                          : 'bg-gray-50 text-gray-600 ring-1 ring-gray-200'
                        }`}>
                          {c.status}
                        </span>
                      )}
                      <button
                        onClick={() => navigate(`/operator/cases/${c.case_id}`)}
                        className="text-xs text-blue-600 hover:underline"
                      >View</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
