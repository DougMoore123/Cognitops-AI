"""
CognitOps AI - Shared data models used across all microservices.
Derived from the actual dataset schemas:
  - equipment_assets.csv
  - maintenance_cases.csv
  - sensor_readings.csv
  - manual_index.csv
  - parts_inventory.csv
  - technician_feedback.csv
"""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Equipment ─────────────────────────────────────────────────────────────────

class EquipmentAsset(BaseModel):
    asset_id: str                                        # e.g. "EQ-1001"
    asset_name: str
    asset_type: str                                      # Motor, Hydraulic Press, …
    manufacturer: str
    model: str
    location: str
    install_date: str
    criticality: Literal["Low", "Medium", "High", "Critical"]
    last_service_date: str
    status: Literal["Active", "Inactive", "Under Maintenance"]


# ── Sensor readings ───────────────────────────────────────────────────────────

class SensorReading(BaseModel):
    reading_id: str                                      # e.g. "READ-00001"
    asset_id: str
    timestamp: datetime
    temperature_c: float
    vibration_mm_s: float
    pressure_psi: float
    current_amp: float
    runtime_hours: float
    anomaly_flag: Literal["Yes", "No"]


# ── Maintenance / Diagnostic ──────────────────────────────────────────────────

SeverityLevel = Literal["Low", "Medium", "High", "Critical"]
ConfidenceLevel = Literal["Low", "Medium", "High"]
CaseStatus = Literal["Open", "Resolved", "Escalated", "In Review"]

class MaintenanceCase(BaseModel):
    case_id: str                                         # e.g. "CASE-0001"
    asset_id: str
    case_date: str
    technician_id: str
    issue_description: str
    uploaded_image_file: Optional[str] = None
    ai_diagnosis_summary: Optional[str] = None
    recommended_action: Optional[str] = None
    safety_warning: Optional[str] = None
    severity_score: Optional[SeverityLevel] = None
    confidence_level: Optional[ConfidenceLevel] = None
    escalation_required: Optional[bool] = None
    case_status: CaseStatus = "Open"
    resolution_notes: Optional[str] = None


class DiagnosticRequest(BaseModel):
    """Inbound payload from the field technician web app."""
    asset_id: str
    technician_id: str
    issue_description: str
    image_url: Optional[str] = None          # blob URL of uploaded image
    work_order_id: Optional[str] = None
    sensor_snapshot: Optional[SensorReading] = None


class DiagnosticResult(BaseModel):
    """Output of the AI Diagnostic Engine."""
    case_id: str
    asset_id: str
    diagnosis_summary: str
    recommended_action: str
    safety_warning: str
    severity_score: SeverityLevel
    confidence_level: ConfidenceLevel
    escalation_required: bool
    rag_sources: list[str] = Field(default_factory=list)   # doc_ids retrieved
    processing_time_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── RAG / Manual index ────────────────────────────────────────────────────────

class ManualEntry(BaseModel):
    doc_id: str                                          # e.g. "DOC-3001"
    asset_type: str
    document_title: str
    section: str
    summary: str
    keywords: list[str]
    source_file: str


class RAGChunk(BaseModel):
    doc_id: str
    chunk_id: str
    content: str
    asset_type: str
    section: str
    score: Optional[float] = None


# ── Parts inventory ──────────────────────────────────────────────────────────

class PartInventory(BaseModel):
    part_id: str                                         # e.g. "PART-2001"
    part_name: str
    compatible_asset_type: str
    stock_quantity: int
    unit_cost_usd: float
    supplier: str
    lead_time_days: int
    reorder_level: int

    @property
    def needs_reorder(self) -> bool:
        return self.stock_quantity <= self.reorder_level


# ── Supervisor / Escalation ──────────────────────────────────────────────────

class EscalationItem(BaseModel):
    case_id: str
    diagnostic_result: DiagnosticResult
    asset: Optional[EquipmentAsset] = None
    queued_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: Optional[str] = None
    review_decision: Optional[Literal["Approved", "Rejected", "Modified"]] = None
    override_notes: Optional[str] = None


# ── Technician feedback (RLHF) ────────────────────────────────────────────────

class TechnicianFeedback(BaseModel):
    feedback_id: str                                     # e.g. "FB-0001"
    case_id: str
    technician_id: str
    recommendation_helpful: bool
    accuracy_rating: int = Field(ge=1, le=5)             # 1-5 scale
    feedback_text: str
    followup_required: bool


# ── Service report ────────────────────────────────────────────────────────────

class ServiceReport(BaseModel):
    report_id: str
    case_id: str
    asset_id: str
    technician_id: str
    diagnostic_result: DiagnosticResult
    supervisor_review: Optional[EscalationItem] = None
    parts_recommended: list[PartInventory] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    report_blob_url: Optional[str] = None
