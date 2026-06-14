"""
CognitOps AI - RAG Retrieval Service
Provides hybrid vector + keyword search over:
  - manual_index (maintenance manuals, SOPs, safety procedures)
  - maintenance_cases (historical service records)
  - parts_inventory (parts catalog)

Uses Azure AI Search with vector search (text-embedding-3-large) and
semantic ranking for maximum retrieval quality.
"""
import os
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery, QueryType
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

APPINSIGHTS_CONN = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
if APPINSIGHTS_CONN:
    configure_azure_monitor(connection_string=APPINSIGHTS_CONN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognitops.rag")
tracer = trace.get_tracer("cognitops.rag")

# ── Azure Search ──────────────────────────────────────────────────────────────
SEARCH_ENDPOINT  = os.getenv("AZURE_AI_SEARCH_ENDPOINT", "")
SEARCH_API_KEY   = os.getenv("AZURE_AI_SEARCH_API_KEY", "")
OPENAI_ENDPOINT  = os.getenv("AZURE_OPENAI_ENDPOINT", "")
OPENAI_API_KEY   = os.getenv("AZURE_OPENAI_API_KEY", "")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_EMBEDDING", "text-embedding-3-large")

# Index names
MANUALS_INDEX    = "cognitops-manuals"
CASES_INDEX      = "cognitops-cases"
PARTS_INDEX      = "cognitops-parts"

search_credential = AzureKeyCredential(SEARCH_API_KEY) if SEARCH_API_KEY else DefaultAzureCredential()

openai_client = AzureOpenAI(
    azure_endpoint=OPENAI_ENDPOINT,
    api_key=OPENAI_API_KEY,
    api_version="2024-08-01-preview",
)

app = FastAPI(title="CognitOps RAG Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Request / Response models ─────────────────────────────────────────────────

class RetrievalRequest(BaseModel):
    asset_id: str
    query: str
    asset_type: str = "Unknown"
    top_k: int = 4


class RetrievalResponse(BaseModel):
    doc_ids: list[str]
    chunks: list[dict]
    query_used: str


# ── Embedding helper ──────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(input=text, model=EMBED_DEPLOYMENT)
    return response.data[0].embedding


# ── Search helpers ────────────────────────────────────────────────────────────

def search_manuals(query: str, asset_type: str, top_k: int) -> list[dict]:
    """Hybrid search over maintenance manuals index."""
    client = SearchClient(SEARCH_ENDPOINT, MANUALS_INDEX, search_credential)
    vector_query = VectorizableTextQuery(text=query, k_nearest_neighbors=top_k, fields="content_vector")

    filter_expr = f"asset_type eq '{asset_type}'" if asset_type != "Unknown" else None

    results = client.search(
        search_text=query,
        vector_queries=[vector_query],
        filter=filter_expr,
        query_type=QueryType.SEMANTIC,
        semantic_configuration_name="cognitops-semantic",
        select=["doc_id", "section", "summary", "keywords", "source_file", "asset_type"],
        top=top_k,
    )

    chunks = []
    for r in results:
        chunks.append({
            "doc_id":    r.get("doc_id"),
            "section":   r.get("section"),
            "summary":   r.get("summary"),
            "keywords":  r.get("keywords", ""),
            "source":    r.get("source_file"),
            "score":     r.get("@search.score", 0),
            "index":     MANUALS_INDEX,
        })
    return chunks


def search_cases(query: str, asset_id: str, top_k: int) -> list[dict]:
    """Hybrid search over historical maintenance cases."""
    client = SearchClient(SEARCH_ENDPOINT, CASES_INDEX, search_credential)
    vector_query = VectorizableTextQuery(text=query, k_nearest_neighbors=top_k, fields="content_vector")

    filter_expr = f"asset_id eq '{asset_id}'"

    results = client.search(
        search_text=query,
        vector_queries=[vector_query],
        filter=filter_expr,
        select=["case_id", "issue_description", "ai_diagnosis_summary", "recommended_action",
                "safety_warning", "severity_score", "resolution_notes"],
        top=top_k,
    )

    chunks = []
    for r in results:
        chunks.append({
            "doc_id":  r.get("case_id"),
            "section": "Historical Case",
            "summary": f"{r.get('ai_diagnosis_summary')} | Resolution: {r.get('resolution_notes', 'N/A')}",
            "score":   r.get("@search.score", 0),
            "index":   CASES_INDEX,
        })
    return chunks


def search_parts(asset_type: str, top_k: int) -> list[dict]:
    """Keyword search over parts catalog for given asset type."""
    client = SearchClient(SEARCH_ENDPOINT, PARTS_INDEX, search_credential)
    results = client.search(
        search_text=asset_type,
        filter=f"compatible_asset_type eq '{asset_type}'",
        select=["part_id", "part_name", "stock_quantity", "unit_cost_usd", "supplier", "lead_time_days"],
        top=top_k,
    )
    chunks = []
    for r in results:
        stock = r.get("stock_quantity", 0)
        chunks.append({
            "doc_id":  r.get("part_id"),
            "section": "Parts Catalog",
            "summary": f"{r.get('part_name')} - Stock: {stock} - ${r.get('unit_cost_usd')} - Lead: {r.get('lead_time_days')}d",
            "score":   r.get("@search.score", 0),
            "index":   PARTS_INDEX,
        })
    return chunks


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "rag-service"}


@app.post("/retrieve", response_model=RetrievalResponse)
async def retrieve(req: RetrievalRequest):
    """
    Retrieve relevant knowledge chunks using hybrid search.
    Searches manuals, historical cases, and parts catalog in parallel.
    Returns ranked and deduplicated results.
    """
    with tracer.start_as_current_span("rag_retrieve") as span:
        span.set_attribute("asset_id", req.asset_id)
        span.set_attribute("asset_type", req.asset_type)

        all_chunks: list[dict] = []

        # Search manuals
        try:
            manual_chunks = search_manuals(req.query, req.asset_type, req.top_k)
            all_chunks.extend(manual_chunks)
        except Exception as e:
            logger.warning(f"Manual search failed: {e}")

        # Search historical cases
        try:
            case_chunks = search_cases(req.query, req.asset_id, req.top_k // 2)
            all_chunks.extend(case_chunks)
        except Exception as e:
            logger.warning(f"Case search failed: {e}")

        # Fetch parts
        try:
            parts_chunks = search_parts(req.asset_type, 3)
            all_chunks.extend(parts_chunks)
        except Exception as e:
            logger.warning(f"Parts search failed: {e}")

        # Sort by score, deduplicate, cap at top_k * 2
        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        seen = set()
        deduped = []
        for c in all_chunks:
            if c["doc_id"] not in seen:
                seen.add(c["doc_id"])
                deduped.append(c)

        deduped = deduped[: req.top_k * 2]
        doc_ids = [c["doc_id"] for c in deduped]

        logger.info(f"RAG retrieved {len(deduped)} chunks for asset={req.asset_id}")
        return RetrievalResponse(doc_ids=doc_ids, chunks=deduped, query_used=req.query)
