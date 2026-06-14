"""
CognitOps AI - Report Generator
Generates structured service reports from diagnostic results and stores them in:
  - Cosmos DB (service-tickets container)
  - Azure Blob Storage (service-reports container as JSON)
  - Subscribes to diagnostic-results Service Bus topic for async generation
"""
import os
import json
import uuid
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from azure.cosmos import CosmosClient
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor

APPINSIGHTS_CONN = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
if APPINSIGHTS_CONN:
    configure_azure_monitor(connection_string=APPINSIGHTS_CONN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognitops.report")

COSMOS_ENDPOINT   = os.getenv("AZURE_COSMOS_ENDPOINT", "")
STORAGE_ACCOUNT   = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "")

credential    = DefaultAzureCredential()
cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=credential)
db            = cosmos_client.get_database_client("cognitops")
tickets_cont  = db.get_container_client("service-tickets")

blob_svc = BlobServiceClient(
    account_url=f"https://{STORAGE_ACCOUNT}.blob.core.windows.net",
    credential=credential,
)

app = FastAPI(title="CognitOps Report Generator", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class GenerateRequest(BaseModel):
    case_id: str
    diagnostic_result: dict
    supervisor_review: Optional[dict] = None


class ReportResponse(BaseModel):
    report_id: str
    case_id: str
    blob_url: str
    cosmos_id: str
    generated_at: str


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "report-generator"}


@app.post("/generate", response_model=ReportResponse)
async def generate_report(req: GenerateRequest):
    """
    Generate a service report from a completed diagnostic case.
    Persists to Cosmos DB and Blob Storage.
    """
    report_id    = f"RPT-{uuid.uuid4().hex[:8].upper()}"
    generated_at = datetime.utcnow().isoformat()

    # Build the report document
    report = {
        "id":               report_id,
        "report_id":        report_id,
        "case_id":          req.case_id,
        "asset_id":         req.diagnostic_result.get("asset_id"),
        "diagnosis_summary":     req.diagnostic_result.get("diagnosis_summary"),
        "recommended_action":    req.diagnostic_result.get("recommended_action"),
        "safety_warning":        req.diagnostic_result.get("safety_warning"),
        "severity_score":        req.diagnostic_result.get("severity_score"),
        "confidence_level":      req.diagnostic_result.get("confidence_level"),
        "escalation_required":   req.diagnostic_result.get("escalation_required"),
        "rag_sources":           req.diagnostic_result.get("rag_sources", []),
        "supervisor_review":     req.supervisor_review,
        "case_status":           "Resolved" if not req.diagnostic_result.get("escalation_required")
                                 else ("Resolved" if req.supervisor_review else "Escalated"),
        "generated_at":      generated_at,
    }

    # 1. Store in Cosmos DB
    cosmos_id = None
    try:
        cosmos_doc = {**report, "partitionKey": report["asset_id"] or "unknown"}
        result     = tickets_cont.upsert_item(cosmos_doc)
        cosmos_id  = result["id"]
        logger.info(f"[{req.case_id}] Report saved to Cosmos: {cosmos_id}")
    except Exception as e:
        logger.error(f"[{req.case_id}] Cosmos upsert failed: {e}")
        cosmos_id = "error"

    # 2. Store in Blob Storage as JSON
    blob_url = ""
    try:
        blob_name = f"{req.case_id}/{report_id}.json"
        blob      = blob_svc.get_blob_client(container="service-reports", blob=blob_name)
        blob.upload_blob(json.dumps(report, indent=2), overwrite=True, content_settings={"content_type": "application/json"})
        blob_url  = blob.url
        logger.info(f"[{req.case_id}] Report blob: {blob_url}")
    except Exception as e:
        logger.error(f"[{req.case_id}] Blob upload failed: {e}")
        blob_url = "error"

    return ReportResponse(
        report_id=report_id,
        case_id=req.case_id,
        blob_url=blob_url,
        cosmos_id=cosmos_id or "",
        generated_at=generated_at,
    )


@app.get("/reports/{case_id}")
async def get_report(case_id: str):
    """Fetch all reports for a case from Cosmos DB."""
    try:
        results = list(tickets_cont.query_items(
            query=f"SELECT * FROM c WHERE c.case_id = '{case_id}'",
            enable_cross_partition_query=True,
        ))
        if not results:
            raise HTTPException(status_code=404, detail=f"No reports found for case {case_id}")
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
