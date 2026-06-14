"""
CognitOps AI - Orchestrator Service
Entry point for all technician requests. Coordinates:
  1. Image upload to Blob Storage
  2. RAG context retrieval
  3. Diagnostic Engine call
  4. Severity scoring
  5. Escalation routing (Service Bus) or direct response
  6. Report generation trigger
"""
import os
import uuid
import time
import httpx
import logging

from datetime import datetime
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

from models import DiagnosticRequest, DiagnosticResult, MaintenanceCase

# ── Telemetry ─────────────────────────────────────────────────────────────────
APPINSIGHTS_CONN = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
if APPINSIGHTS_CONN:
    configure_azure_monitor(connection_string=APPINSIGHTS_CONN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognitops.orchestrator")
tracer = trace.get_tracer("cognitops.orchestrator")

# ── Service URLs (internal Container Apps) ────────────────────────────────────
RAG_SERVICE_URL        = os.getenv("RAG_SERVICE_URL", "http://ca-rag-service")
DIAGNOSTIC_ENGINE_URL  = os.getenv("DIAGNOSTIC_ENGINE_URL", "http://ca-diagnostic-engine")
SEVERITY_SCORER_URL    = os.getenv("SEVERITY_SCORER_URL", "http://ca-severity-scorer")
REPORT_GENERATOR_URL   = os.getenv("REPORT_GENERATOR_URL", "http://ca-report-generator")

# ── Azure clients ─────────────────────────────────────────────────────────────
credential = DefaultAzureCredential()
STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "")
blob_client = BlobServiceClient(
    account_url=f"https://{STORAGE_ACCOUNT}.blob.core.windows.net",
    credential=credential,
)
SB_NAMESPACE    = os.getenv("AZURE_SERVICE_BUS_NAMESPACE", "")
SB_CONN_STRING  = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "")

app = FastAPI(
    title="CognitOps Orchestrator",
    description="Multimodal field service AI - main entry point",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def upload_image(image: UploadFile, case_id: str) -> str:
    """Upload equipment image to Azure Blob Storage and return the blob URL."""
    container = "equipment-images"
    blob_name  = f"{case_id}/{image.filename}"
    blob       = blob_client.get_blob_client(container=container, blob=blob_name)
    data       = await image.read()
    blob.upload_blob(data, overwrite=True)
    return blob.url


async def get_rag_context(asset_id: str, issue_description: str, asset_type: str) -> list[str]:
    """Call RAG service to retrieve relevant manual sections."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{RAG_SERVICE_URL}/retrieve",
            json={"asset_id": asset_id, "query": issue_description, "asset_type": asset_type, "top_k": 4},
        )
        resp.raise_for_status()
        return resp.json().get("doc_ids", [])


async def call_diagnostic_engine(payload: dict) -> dict:
    """Call the diagnostic engine microservice."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{DIAGNOSTIC_ENGINE_URL}/diagnose", json=payload)
        resp.raise_for_status()
        return resp.json()


async def enqueue_escalation(case_id: str, result: dict) -> None:
    """Push escalated case to Service Bus supervisor-review-queue."""
    message_body = {
        "case_id": case_id,
        "severity_score": result.get("severity_score"),
        "confidence_level": result.get("confidence_level"),
        "queued_at": datetime.utcnow().isoformat(),
    }
    import json
    async with ServiceBusClient.from_connection_string(SB_CONN_STRING) as sb:
        sender = sb.get_queue_sender("supervisor-review-queue")
        async with sender:
            await sender.send_messages(
                ServiceBusMessage(json.dumps(message_body), content_type="application/json")
            )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "orchestrator", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/cases", response_model=DiagnosticResult, status_code=200)
async def submit_case(
    asset_id:          str        = Form(...),
    technician_id:     str        = Form(...),
    issue_description: str        = Form(...),
    asset_type:        str        = Form("Unknown"),
    work_order_id:     str | None = Form(None),
    image:             UploadFile = File(None),
):
    """
    Main entry point for field technicians.
    Accepts multipart form data with optional equipment image.
    Returns AI diagnosis, recommendations, severity, and escalation flag.
    """
    with tracer.start_as_current_span("orchestrate_case") as span:
        case_id   = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        start_ms  = time.time()

        span.set_attribute("case_id", case_id)
        span.set_attribute("asset_id", asset_id)
        span.set_attribute("technician_id", technician_id)

        # 1. Upload image
        image_url = None
        if image and image.filename:
            try:
                image_url = await upload_image(image, case_id)
                logger.info(f"[{case_id}] Image uploaded: {image_url}")
            except Exception as e:
                logger.warning(f"[{case_id}] Image upload failed (non-fatal): {e}")

        # 2. Retrieve RAG context
        rag_doc_ids: list[str] = []
        try:
            rag_doc_ids = await get_rag_context(asset_id, issue_description, asset_type)
            logger.info(f"[{case_id}] RAG retrieved {len(rag_doc_ids)} docs")
        except Exception as e:
            logger.warning(f"[{case_id}] RAG retrieval failed (non-fatal): {e}")

        # 3. Call diagnostic engine
        diag_payload = {
            "case_id":           case_id,
            "asset_id":          asset_id,
            "asset_type":        asset_type,
            "technician_id":     technician_id,
            "issue_description": issue_description,
            "image_url":         image_url,
            "rag_doc_ids":       rag_doc_ids,
            "work_order_id":     work_order_id,
        }
        try:
            diag_result = await call_diagnostic_engine(diag_payload)
        except httpx.HTTPError as e:
            logger.error(f"[{case_id}] Diagnostic engine error: {e}")
            raise HTTPException(status_code=502, detail="Diagnostic engine unavailable")

        elapsed_ms = int((time.time() - start_ms) * 1000)
        diag_result["processing_time_ms"] = elapsed_ms

        # 4. Escalate if required
        if diag_result.get("escalation_required"):
            try:
                await enqueue_escalation(case_id, diag_result)
                logger.info(f"[{case_id}] Escalated to supervisor queue")
                diag_result["case_status"] = "Escalated"
            except Exception as e:
                logger.warning(f"[{case_id}] Escalation enqueue failed: {e}")

        # 5. Trigger report generation (fire-and-forget)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{REPORT_GENERATOR_URL}/generate",
                    json={"case_id": case_id, "diagnostic_result": diag_result},
                )
        except Exception:
            pass  # Report generation is async; don't fail the response

        logger.info(f"[{case_id}] Completed in {elapsed_ms}ms - Severity: {diag_result.get('severity_score')}")
        return DiagnosticResult(**diag_result)


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str):
    """Retrieve a previously processed diagnostic case."""
    # In production, fetch from Cosmos DB
    raise HTTPException(status_code=404, detail=f"Case {case_id} not found in cache; query Cosmos DB directly.")
