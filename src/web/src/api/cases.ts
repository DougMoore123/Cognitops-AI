import { get, post } from './client'
import type { CaseResponse } from '../types'

export interface SubmitCasePayload {
  asset_id: string
  location: string
  symptom_description: string
  image?: File | null
}

export async function submitCase(payload: SubmitCasePayload): Promise<CaseResponse> {
  const form = new FormData()
  form.append('asset_id', payload.asset_id)
  form.append('location', payload.location)
  form.append('symptom_description', payload.symptom_description)
  if (payload.image) {
    form.append('image', payload.image, payload.image.name)
  }
  return post<CaseResponse>('/api/cases', form)
}

export async function getCase(caseId: string): Promise<CaseResponse> {
  return get<CaseResponse>(`/api/cases/${encodeURIComponent(caseId)}`)
}

/** Poll until status is no longer 'processing', with a 60 s timeout. */
export async function pollCase(
  caseId: string,
  onUpdate: (c: CaseResponse) => void,
  intervalMs = 2000,
  timeoutMs = 60000,
): Promise<CaseResponse> {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const c = await getCase(caseId)
        onUpdate(c)
        if (c.status !== 'processing') {
          resolve(c)
          return
        }
        if (Date.now() >= deadline) {
          reject(new Error('Timed out waiting for diagnosis'))
          return
        }
        setTimeout(tick, intervalMs)
      } catch (err) {
        reject(err)
      }
    }
    setTimeout(tick, intervalMs)
  })
}
