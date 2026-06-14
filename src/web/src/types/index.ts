// ── Shared domain types ───────────────────────────────────────────────────────

export type Severity = 'Low' | 'Medium' | 'High' | 'Critical'
export type CaseStatus = 'processing' | 'completed' | 'escalated' | 'failed'

export interface DiagnosisResult {
  diagnosis_summary: string
  recommended_action: string
  safety_warning: string | null
  severity_score: Severity
  confidence_level: number  // 0.0 – 1.0
  escalation_required: boolean
  rag_sources: string[]
}

export interface CaseResponse {
  case_id: string
  status: CaseStatus
  asset_id: string
  created_at: string
  diagnosis?: DiagnosisResult
  adjusted_severity?: Severity
  error?: string
}

// ── Supervisor types ──────────────────────────────────────────────────────────

export interface EscalationItem {
  id: string
  case_id: string
  asset_id: string
  facility_id: string
  severity: Severity
  diagnosis_summary: string
  recommended_action: string
  safety_warning: string | null
  escalation_reason: string
  created_at: string
  status: 'pending' | 'approved' | 'rejected'
}
