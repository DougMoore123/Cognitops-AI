"""
CognitOps AI - Diagnostic Engine
Core GPT-4o multimodal reasoning service.
Receives: asset context, issue description, optional image URL, RAG chunks.
Produces: diagnosis summary, recommended action, safety warning, severity, confidence.

Prompt engineering informed by actual maintenance_cases.csv patterns.
"""
import os
import json
import logging
import base64
import time
import httpx
import mlflow

from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

APPINSIGHTS_CONN = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
if APPINSIGHTS_CONN:
    configure_azure_monitor(connection_string=APPINSIGHTS_CONN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognitops.diagnostic")
tracer = trace.get_tracer("cognitops.diagnostic")

OPENAI_ENDPOINT     = os.getenv("AZURE_OPENAI_ENDPOINT", "")
OPENAI_API_KEY      = os.getenv("AZURE_OPENAI_API_KEY", "")
GPT4O_DEPLOYMENT    = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPT4O", "gpt-4o")
MLFLOW_TRACKING_URI = os.getenv("AZURE_MLFLOW_TRACKING_URI", "")

if MLFLOW_TRACKING_URI:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("cognitops-diagnostics")
    logger.info(f"MLflow tracking enabled: {MLFLOW_TRACKING_URI}")
else:
    logger.warning("AZURE_MLFLOW_TRACKING_URI not set — MLflow tracking disabled")

openai_client = AzureOpenAI(
    azure_endpoint=OPENAI_ENDPOINT,
    api_key=OPENAI_API_KEY,
    api_version="2024-08-01-preview",
)

app = FastAPI(title="CognitOps Diagnostic Engine", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Request / Response ────────────────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    case_id: str
    asset_id: str
    asset_type: str = "Unknown"
    technician_id: str
    issue_description: str
    image_url: str | None = None
    rag_doc_ids: list[str] = []
    rag_chunks: list[dict] = []
    work_order_id: str | None = None
    sensor_snapshot: dict | None = None


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are CognitOps AI, an expert field service diagnostic assistant for industrial equipment.

You analyze equipment issues reported by field technicians and provide:
1. A clear, concise diagnosis of the likely root cause
2. Specific recommended repair/inspection actions 
3. Critical safety warnings the technician must follow
4. A severity score: Low, Medium, High, or Critical
5. A confidence level: Low, Medium, or High
6. Whether immediate supervisor escalation is required

SEVERITY GUIDELINES (based on historical cases):
- Critical: Equipment failure imminent, safety risk, production stopped (e.g. hydraulic pressure loss, electrical faults)
- High: Significant degradation, escalating damage risk (e.g. bearing wear, overheating >85°C)
- Medium: Performance degradation, scheduled repair needed (e.g. moderate vibration, pressure variance)
- Low: Cosmetic or minor issues, monitor and log

ESCALATION RULES - Set escalation_required=true when:
- severity_score is Critical or High AND confidence_level is Low or Medium
- Safety hazard is identified
- Repair requires specialized tooling or permits
- Historical cases show pattern of recurring failure

CONFIDENCE GUIDELINES:
- High: Clear visual evidence + matching RAG documentation + consistent sensor data
- Medium: Partial evidence or ambiguous symptoms
- Low: Insufficient data, unusual failure mode, or contradictory signals

Always cite the relevant manual section or historical case if available in context.
Respond ONLY with a valid JSON object - no markdown, no commentary."""


def build_user_message(req: DiagnoseRequest) -> list[dict]:
    """Build multimodal user message with text + optional image."""
    parts: list[dict] = []

    # Build text context
    rag_context = ""
    if req.rag_chunks:
        rag_context = "\n\nRELEVANT KNOWLEDGE BASE:\n"
        for chunk in req.rag_chunks[:6]:
            rag_context += f"- [{chunk.get('doc_id', 'N/A')}] {chunk.get('section', '')}: {chunk.get('summary', '')}\n"

    sensor_context = ""
    if req.sensor_snapshot:
        s = req.sensor_snapshot
        sensor_context = (
            f"\n\nLATEST SENSOR READING:\n"
            f"  Temperature: {s.get('temperature_c')}°C | "
            f"Vibration: {s.get('vibration_mm_s')} mm/s | "
            f"Pressure: {s.get('pressure_psi')} PSI | "
            f"Current: {s.get('current_amp')} A | "
            f"Anomaly: {s.get('anomaly_flag')}"
        )

    text_content = f"""CASE ID: {req.case_id}
ASSET: {req.asset_id} ({req.asset_type})
TECHNICIAN: {req.technician_id}
ISSUE REPORTED: {req.issue_description}
{sensor_context}
{rag_context}

Analyze this equipment issue and respond with a JSON object with EXACTLY these fields:
{{
  "diagnosis_summary": "...",
  "recommended_action": "...",
  "safety_warning": "...",
  "severity_score": "Low|Medium|High|Critical",
  "confidence_level": "Low|Medium|High",
  "escalation_required": true|false,
  "rag_sources": ["doc_id_1", "doc_id_2"]
}}"""

    parts.append({"type": "text", "text": text_content})

    # Add image if provided
    if req.image_url:
        try:
            # Fetch image and encode as base64 for GPT-4o vision
            resp = httpx.get(req.image_url, timeout=10.0)
            if resp.status_code == 200:
                b64 = base64.b64encode(resp.content).decode("utf-8")
                content_type = resp.headers.get("content-type", "image/jpeg")
                parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{content_type};base64,{b64}",
                        "detail": "high",
                    },
                })
                logger.info(f"[{req.case_id}] Image attached for vision analysis")
        except Exception as e:
            logger.warning(f"[{req.case_id}] Could not attach image: {e}")
            # Fall back to URL hint in text
            parts[0]["text"] += f"\n\nEQUIPMENT IMAGE URL (analyze if possible): {req.image_url}"

    return parts


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "diagnostic-engine"}


@app.post("/diagnose")
async def diagnose(req: DiagnoseRequest):
    """
    Core diagnostic reasoning endpoint.
    Calls GPT-4o with multimodal context (image + text + RAG).
    """
    with tracer.start_as_current_span("diagnose") as span:
        span.set_attribute("case_id", req.case_id)
        span.set_attribute("asset_id", req.asset_id)
        span.set_attribute("has_image", req.image_url is not None)
        span.set_attribute("rag_chunks", len(req.rag_chunks))

        user_parts = build_user_message(req)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_parts},
        ]

        t0 = time.monotonic()

        try:
            response = openai_client.chat.completions.create(
                model=GPT4O_DEPLOYMENT,
                messages=messages,
                max_tokens=1024,
                temperature=0.1,           # Low temp for consistent diagnostic output
                response_format={"type": "json_object"},
            )
        except Exception as e:
            logger.error(f"[{req.case_id}] OpenAI call failed: {e}")
            raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")

        elapsed_ms = (time.monotonic() - t0) * 1000
        raw = response.choices[0].message.content
        total_tokens = response.usage.total_tokens
        logger.info(f"[{req.case_id}] LLM tokens used: {total_tokens} in {elapsed_ms:.0f} ms")

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"[{req.case_id}] JSON parse error: {e}\nRaw: {raw}")
            raise HTTPException(status_code=500, detail="Diagnostic engine returned malformed JSON")

        # Inject metadata
        result["case_id"]      = req.case_id
        result["asset_id"]     = req.asset_id
        result["created_at"]   = datetime.utcnow().isoformat()

        # Ensure rag_sources exists
        if "rag_sources" not in result:
            result["rag_sources"] = req.rag_doc_ids

        # ── MLflow tracking ───────────────────────────────────────────────────
        if MLFLOW_TRACKING_URI:
            try:
                with mlflow.start_run(run_name=f"case-{req.case_id[:8]}"):
                    mlflow.log_params({
                        "case_id":           req.case_id,
                        "asset_id":          req.asset_id,
                        "asset_type":        req.asset_type,
                        "has_image":         req.image_url is not None,
                        "rag_chunk_count":   len(req.rag_chunks),
                        "gpt4o_deployment":  GPT4O_DEPLOYMENT,
                    })
                    mlflow.log_metrics({
                        "total_tokens":      total_tokens,
                        "prompt_tokens":     response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "latency_ms":        elapsed_ms,
                    })
                    # Encode severity + confidence as numeric for trend charts
                    severity_map = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
                    confidence_map = {"Low": 1, "Medium": 2, "High": 3}
                    mlflow.log_metrics({
                        "severity_numeric":   severity_map.get(result.get("severity_score", "Low"), 1),
                        "confidence_numeric": confidence_map.get(result.get("confidence_level", "Low"), 1),
                        "escalation_flag":    int(result.get("escalation_required", False)),
                    })
                    mlflow.set_tags({
                        "severity":   result.get("severity_score"),
                        "confidence": result.get("confidence_level"),
                        "escalated":  str(result.get("escalation_required")),
                    })
            except Exception as mlflow_err:
                # Never let MLflow failure break the diagnostic response
                logger.warning(f"[{req.case_id}] MLflow logging failed (non-fatal): {mlflow_err}")

        logger.info(
            f"[{req.case_id}] Diagnosis: {result.get('severity_score')} / "
            f"{result.get('confidence_level')} / Escalate: {result.get('escalation_required')}"
        )
        return result
