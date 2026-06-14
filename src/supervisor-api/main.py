"""
CognitOps AI - Supervisor Review API
Human-in-the-loop governance for escalated cases.
- Reads from Service Bus supervisor-review-queue
- Stores pending reviews in Cosmos DB (escalations container)
- Provides approve/reject endpoints for supervisors
- Publishes resolution to diagnostic-results topic
"""
import os
import json
import uuid
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional
from azure.cosmos import CosmosClient, exceptions as cosmos_exc
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

APPINSIGHTS_CONN = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
if APPINSIGHTS_CONN:
    configure_azure_monitor(connection_string=APPINSIGHTS_CONN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognitops.supervisor")
tracer = trace.get_tracer("cognitops.supervisor")

COSMOS_CONN     = os.getenv("AZURE_COSMOS_CONNECTION_STRING", "")
COSMOS_ENDPOINT = os.getenv("AZURE_COSMOS_ENDPOINT", "")
SB_CONN_STRING  = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "")
DB_NAME         = "cognitops"

credential   = DefaultAzureCredential()
cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=credential)
db           = cosmos_client.get_database_client(DB_NAME)
escalations  = db.get_container_client("escalations")
cases_cont   = db.get_container_client("service-tickets")

app = FastAPI(title="CognitOps Supervisor API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ReviewDecision(BaseModel):
    supervisor_id: str
    decision: Literal["Approved", "Rejected", "Modified"]
    override_notes: Optional[str] = None
    modified_action: Optional[str] = None  # if Modified, new recommended action


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "supervisor-api"}


@app.get("/queue")
async def get_queue():
    """Get all pending escalated cases awaiting supervisor review."""
    try:
        items = list(escalations.query_items(
            query="SELECT * FROM c WHERE c.review_decision = null ORDER BY c.queued_at ASC",
            enable_cross_partition_query=True,
        ))
        return {"pending_count": len(items), "items": items}
    except Exception as e:
        logger.error(f"Failed to fetch escalation queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/queue/{case_id}")
async def get_case(case_id: str):
    """Retrieve a specific escalated case."""
    try:
        results = list(escalations.query_items(
            query=f"SELECT * FROM c WHERE c.case_id = '{case_id}'",
            enable_cross_partition_query=True,
        ))
        if not results:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not in escalation queue")
        return results[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/queue/{case_id}/approve")
async def approve_case(case_id: str, body: ReviewDecision):
    """
    Supervisor approves AI recommendation.
    Updates Cosmos DB and publishes to diagnostic-results topic.
    """
    with tracer.start_as_current_span("supervisor_approve") as span:
        span.set_attribute("case_id", case_id)
        span.set_attribute("supervisor_id", body.supervisor_id)

        result = await _update_escalation(
            case_id,
            decision="Approved",
            supervisor_id=body.supervisor_id,
            override_notes=body.override_notes,
        )
        await _publish_resolution(case_id, "Approved", body.supervisor_id)
        logger.info(f"[{case_id}] Approved by {body.supervisor_id}")
        return result


@app.post("/queue/{case_id}/reject")
async def reject_case(case_id: str, body: ReviewDecision):
    """
    Supervisor rejects AI recommendation with override notes.
    Case is returned for rework or manual resolution.
    """
    with tracer.start_as_current_span("supervisor_reject") as span:
        span.set_attribute("case_id", case_id)
        if not body.override_notes:
            raise HTTPException(status_code=400, detail="override_notes required when rejecting")

        result = await _update_escalation(
            case_id,
            decision="Rejected",
            supervisor_id=body.supervisor_id,
            override_notes=body.override_notes,
            modified_action=body.modified_action,
        )
        await _publish_resolution(case_id, "Rejected", body.supervisor_id)
        logger.info(f"[{case_id}] Rejected by {body.supervisor_id}: {body.override_notes}")
        return result


@app.get("/stats")
async def queue_stats():
    """Supervisor dashboard stats."""
    try:
        total   = list(escalations.query_items("SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True))[0]
        pending = list(escalations.query_items(
            "SELECT VALUE COUNT(1) FROM c WHERE c.review_decision = null",
            enable_cross_partition_query=True,
        ))[0]
        approved = list(escalations.query_items(
            "SELECT VALUE COUNT(1) FROM c WHERE c.review_decision = 'Approved'",
            enable_cross_partition_query=True,
        ))[0]
        return {"total": total, "pending": pending, "approved": approved, "rejected": total - approved - pending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _update_escalation(
    case_id: str,
    decision: str,
    supervisor_id: str,
    override_notes: str | None,
    modified_action: str | None = None,
) -> dict:
    results = list(escalations.query_items(
        query=f"SELECT * FROM c WHERE c.case_id = '{case_id}'",
        enable_cross_partition_query=True,
    ))
    if not results:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found in escalation queue")

    item = results[0]
    item["review_decision"] = decision
    item["reviewed_by"]     = supervisor_id
    item["reviewed_at"]     = datetime.utcnow().isoformat()
    item["override_notes"]  = override_notes
    if modified_action:
        item["modified_action"] = modified_action

    escalations.upsert_item(item)
    return item


async def _publish_resolution(case_id: str, decision: str, supervisor_id: str) -> None:
    """Publish resolution event to Service Bus diagnostic-results topic."""
    try:
        msg_body = json.dumps({
            "case_id":        case_id,
            "decision":       decision,
            "reviewed_by":    supervisor_id,
            "reviewed_at":    datetime.utcnow().isoformat(),
        })
        with ServiceBusClient.from_connection_string(SB_CONN_STRING) as sb:
            sender = sb.get_topic_sender("diagnostic-results")
            with sender:
                sender.send_messages(ServiceBusMessage(msg_body, content_type="application/json"))
    except Exception as e:
        logger.warning(f"[{case_id}] Failed to publish resolution event: {e}")
