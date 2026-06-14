"""
CognitOps AI - Data Ingestion Pipeline
Seeds all 6 CSV datasets into their respective Azure services:

  equipment_assets.csv    → Cosmos DB (equipment-profiles container)
  maintenance_cases.csv   → Cosmos DB (service-tickets) + AI Search index (cognitops-cases)
  sensor_readings.csv     → Cosmos DB (service-tickets as time-series sub-docs)
  manual_index.csv        → AI Search index (cognitops-manuals) — primary RAG source
  parts_inventory.csv     → Cosmos DB (equipment-profiles) + AI Search (cognitops-parts)
  technician_feedback.csv → Cosmos DB (service-tickets as feedback docs)

Also creates AI Search indexes with vector fields for hybrid retrieval.
"""
import os
import csv
import json
import logging
import argparse
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, PartitionKey
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType,
    SimpleField, SearchableField, VectorSearch,
    HnswAlgorithmConfiguration, VectorSearchProfile,
    SemanticConfiguration, SemanticSearch, SemanticPrioritizedFields,
    SemanticField,
)
from azure.search.documents.models import IndexDocumentsBatch
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("cognitops.ingest")

# ── Environment ───────────────────────────────────────────────────────────────
COSMOS_ENDPOINT  = os.getenv("AZURE_COSMOS_ENDPOINT", "")
SEARCH_ENDPOINT  = os.getenv("AZURE_AI_SEARCH_ENDPOINT", "")
SEARCH_API_KEY   = os.getenv("AZURE_AI_SEARCH_API_KEY", "")
OPENAI_ENDPOINT  = os.getenv("AZURE_OPENAI_ENDPOINT", "")
OPENAI_API_KEY   = os.getenv("AZURE_OPENAI_API_KEY", "")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_EMBEDDING", "text-embedding-3-large")

DATA_DIR = Path(__file__).parent / "data"

# Index names
MANUALS_INDEX = "cognitops-manuals"
CASES_INDEX   = "cognitops-cases"
PARTS_INDEX   = "cognitops-parts"

# ── Clients ───────────────────────────────────────────────────────────────────
credential   = DefaultAzureCredential()
cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=credential)
db            = cosmos_client.get_database_client("cognitops")

search_credential = AzureKeyCredential(SEARCH_API_KEY) if SEARCH_API_KEY else credential
index_client  = SearchIndexClient(SEARCH_ENDPOINT, search_credential)

openai_client = AzureOpenAI(
    azure_endpoint=OPENAI_ENDPOINT,
    api_key=OPENAI_API_KEY,
    api_version="2024-08-01-preview",
)


# ── Embedding helper ──────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Generate text embedding using Azure OpenAI text-embedding-3-large."""
    response = openai_client.embeddings.create(input=text[:8000], model=EMBED_DEPLOYMENT)
    return response.data[0].embedding


# ── AI Search index definitions ───────────────────────────────────────────────

VECTOR_DIM = 3072  # text-embedding-3-large output dimension


def build_manuals_index() -> SearchIndex:
    """
    Index for manual_index.csv entries.
    Supports hybrid search (keyword + vector) + semantic ranking.
    Fields match: doc_id, asset_type, document_title, section, summary, keywords, source_file
    """
    fields = [
        SimpleField("id",             SearchFieldDataType.String, key=True),
        SimpleField("doc_id",         SearchFieldDataType.String, filterable=True),
        SimpleField("asset_type",     SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField("document_title", SearchFieldDataType.String),
        SearchableField("section",    SearchFieldDataType.String),
        SearchableField("summary",    SearchFieldDataType.String, analyzer_name="en.microsoft"),
        SearchableField("keywords",   SearchFieldDataType.String),
        SimpleField("source_file",    SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIM,
            vector_search_profile_name="hnsw-profile",
        ),
    ]
    return SearchIndex(
        name=MANUALS_INDEX,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration("hnsw-algo")],
            profiles=[VectorSearchProfile("hnsw-profile", algorithm_configuration_name="hnsw-algo")],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="cognitops-semantic",
            configurations=[
                SemanticConfiguration(
                    name="cognitops-semantic",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="document_title"),
                        content_fields=[SemanticField(field_name="summary"), SemanticField(field_name="section")],
                        keywords_fields=[SemanticField(field_name="keywords")],
                    ),
                )
            ],
        ),
    )


def build_cases_index() -> SearchIndex:
    """
    Index for maintenance_cases.csv.
    Fields: case_id, asset_id, issue_description, ai_diagnosis_summary, recommended_action,
            safety_warning, severity_score, confidence_level, resolution_notes
    """
    fields = [
        SimpleField("id",               SearchFieldDataType.String, key=True),
        SimpleField("case_id",          SearchFieldDataType.String, filterable=True),
        SimpleField("asset_id",         SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField("severity_score",   SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField("confidence_level", SearchFieldDataType.String, filterable=True),
        SearchableField("issue_description",   SearchFieldDataType.String, analyzer_name="en.microsoft"),
        SearchableField("ai_diagnosis_summary",SearchFieldDataType.String, analyzer_name="en.microsoft"),
        SearchableField("recommended_action",  SearchFieldDataType.String),
        SearchableField("safety_warning",      SearchFieldDataType.String),
        SearchableField("resolution_notes",    SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIM,
            vector_search_profile_name="hnsw-profile",
        ),
    ]
    return SearchIndex(
        name=CASES_INDEX,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration("hnsw-algo")],
            profiles=[VectorSearchProfile("hnsw-profile", algorithm_configuration_name="hnsw-algo")],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="cognitops-semantic",
            configurations=[
                SemanticConfiguration(
                    name="cognitops-semantic",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[
                            SemanticField(field_name="ai_diagnosis_summary"),
                            SemanticField(field_name="issue_description"),
                        ],
                        keywords_fields=[SemanticField(field_name="safety_warning")],
                    ),
                )
            ],
        ),
    )


def build_parts_index() -> SearchIndex:
    """
    Index for parts_inventory.csv.
    Fields: part_id, part_name, compatible_asset_type, stock_quantity, unit_cost_usd, supplier
    """
    fields = [
        SimpleField("id",                   SearchFieldDataType.String, key=True),
        SimpleField("part_id",              SearchFieldDataType.String, filterable=True),
        SimpleField("compatible_asset_type",SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField("stock_quantity",       SearchFieldDataType.Int32,  filterable=True),
        SimpleField("unit_cost_usd",        SearchFieldDataType.Double, filterable=True, sortable=True),
        SimpleField("lead_time_days",       SearchFieldDataType.Int32,  filterable=True),
        SimpleField("reorder_level",        SearchFieldDataType.Int32),
        SimpleField("supplier",             SearchFieldDataType.String, filterable=True),
        SearchableField("part_name",        SearchFieldDataType.String, analyzer_name="en.microsoft"),
    ]
    return SearchIndex(name=PARTS_INDEX, fields=fields)


# ── Index creation ────────────────────────────────────────────────────────────

def create_indexes():
    logger.info("Creating AI Search indexes...")
    for idx in [build_manuals_index(), build_cases_index(), build_parts_index()]:
        try:
            index_client.create_or_update_index(idx)
            logger.info(f"  ✓ Index '{idx.name}' created/updated")
        except Exception as e:
            logger.error(f"  ✗ Index '{idx.name}' failed: {e}")


# ── CSV → Cosmos DB ───────────────────────────────────────────────────────────

def ingest_equipment_assets(csv_path: Path):
    """equipment_assets.csv → Cosmos DB equipment-profiles container."""
    container = db.get_container_client("equipment-profiles")
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            doc = {
                "id":               row["asset_id"],
                "asset_id":         row["asset_id"],
                "asset_name":       row["asset_name"],
                "asset_type":       row["asset_type"],
                "manufacturer":     row["manufacturer"],
                "model":            row["model"],
                "location":         row["location"],
                "install_date":     row["install_date"],
                "criticality":      row["criticality"],
                "last_service_date":row["last_service_date"],
                "status":           row["status"],
                "facilityId":       row["location"].split(" - ")[0] if " - " in row["location"] else row["location"],
            }
            container.upsert_item(doc)
            count += 1
    logger.info(f"  ✓ equipment_assets: {count} assets → Cosmos equipment-profiles")


def ingest_maintenance_cases(csv_path: Path):
    """maintenance_cases.csv → Cosmos DB service-tickets container."""
    container = db.get_container_client("service-tickets")
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            doc = {
                "id":                    row["case_id"],
                "case_id":               row["case_id"],
                "asset_id":              row["asset_id"],
                "equipmentId":           row["asset_id"],  # partition key
                "case_date":             row["case_date"],
                "technician_id":         row["technician_id"],
                "issue_description":     row["issue_description"],
                "uploaded_image_file":   row.get("uploaded_image_file", ""),
                "ai_diagnosis_summary":  row.get("ai_diagnosis_summary", ""),
                "recommended_action":    row.get("recommended_action", ""),
                "safety_warning":        row.get("safety_warning", ""),
                "severity_score":        row.get("severity_score", ""),
                "confidence_level":      row.get("confidence_level", ""),
                "escalation_required":   row.get("escalation_required", "No").strip() == "Yes",
                "case_status":           row.get("case_status", "Open"),
                "resolution_notes":      row.get("resolution_notes", ""),
                "doc_type":              "maintenance_case",
            }
            container.upsert_item(doc)
            count += 1
    logger.info(f"  ✓ maintenance_cases: {count} cases → Cosmos service-tickets")


def ingest_sensor_readings(csv_path: Path):
    """sensor_readings.csv → Cosmos DB service-tickets container as time-series docs."""
    container = db.get_container_client("service-tickets")
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            doc = {
                "id":            row["reading_id"],
                "reading_id":    row["reading_id"],
                "asset_id":      row["asset_id"],
                "equipmentId":   row["asset_id"],
                "timestamp":     row["timestamp"],
                "temperature_c": float(row["temperature_c"]),
                "vibration_mm_s":float(row["vibration_mm_s"]),
                "pressure_psi":  float(row["pressure_psi"]),
                "current_amp":   float(row["current_amp"]),
                "runtime_hours": float(row["runtime_hours"]),
                "anomaly_flag":  row["anomaly_flag"],
                "doc_type":      "sensor_reading",
            }
            container.upsert_item(doc)
            count += 1
    logger.info(f"  ✓ sensor_readings: {count} readings → Cosmos service-tickets")


def ingest_parts_inventory(csv_path: Path):
    """parts_inventory.csv → Cosmos DB equipment-profiles + AI Search."""
    container = db.get_container_client("equipment-profiles")
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            doc = {
                "id":                    row["part_id"],
                "part_id":               row["part_id"],
                "part_name":             row["part_name"],
                "compatible_asset_type": row["compatible_asset_type"],
                "stock_quantity":        int(row["stock_quantity"]),
                "unit_cost_usd":         float(row["unit_cost_usd"]),
                "supplier":              row["supplier"],
                "lead_time_days":        int(row["lead_time_days"]),
                "reorder_level":         int(row["reorder_level"]),
                "facilityId":            "global",
                "doc_type":              "part",
            }
            container.upsert_item(doc)
            count += 1
    logger.info(f"  ✓ parts_inventory: {count} parts → Cosmos equipment-profiles")


def ingest_technician_feedback(csv_path: Path):
    """technician_feedback.csv → Cosmos DB service-tickets (RLHF loop)."""
    container = db.get_container_client("service-tickets")
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            doc = {
                "id":                      row["feedback_id"],
                "feedback_id":             row["feedback_id"],
                "case_id":                 row["case_id"],
                "equipmentId":             f"feedback-{row['case_id']}",
                "technician_id":           row["technician_id"],
                "recommendation_helpful":  row["recommendation_helpful"] == "Yes",
                "accuracy_rating":         int(row["accuracy_rating_1_5"]),
                "feedback_text":           row["feedback_text"],
                "followup_required":       row["followup_required"] == "Yes",
                "doc_type":                "technician_feedback",
            }
            container.upsert_item(doc)
            count += 1
    logger.info(f"  ✓ technician_feedback: {count} records → Cosmos service-tickets")


# ── CSV → AI Search ───────────────────────────────────────────────────────────

def ingest_manuals_to_search(csv_path: Path):
    """manual_index.csv → AI Search cognitops-manuals with vector embeddings."""
    client = SearchClient(SEARCH_ENDPOINT, MANUALS_INDEX, search_credential)
    docs   = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # Build rich text for embedding
            text = f"{row['document_title']} {row['section']} {row['summary']} {row['keywords']}"
            vector = embed(text)

            docs.append({
                "id":             row["doc_id"],
                "doc_id":         row["doc_id"],
                "asset_type":     row["asset_type"],
                "document_title": row["document_title"],
                "section":        row["section"],
                "summary":        row["summary"],
                "keywords":       row["keywords"],
                "source_file":    row["source_file"],
                "content_vector": vector,
            })

    batch = IndexDocumentsBatch()
    batch.add_upload_actions(docs)
    result = client.index_documents(batch)
    failed = [r for r in result if not r.succeeded]
    logger.info(f"  ✓ manual_index: {len(docs) - len(failed)}/{len(docs)} docs → AI Search {MANUALS_INDEX}")
    if failed:
        logger.warning(f"  ✗ {len(failed)} manual docs failed: {[r.key for r in failed]}")


def ingest_cases_to_search(csv_path: Path):
    """maintenance_cases.csv → AI Search cognitops-cases with vector embeddings."""
    client = SearchClient(SEARCH_ENDPOINT, CASES_INDEX, search_credential)
    docs   = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            text = (
                f"{row['issue_description']} "
                f"{row.get('ai_diagnosis_summary','')} "
                f"{row.get('recommended_action','')} "
                f"{row.get('safety_warning','')} "
                f"{row.get('resolution_notes','')}"
            )
            vector = embed(text)
            docs.append({
                "id":                   row["case_id"],
                "case_id":              row["case_id"],
                "asset_id":             row["asset_id"],
                "severity_score":       row.get("severity_score", ""),
                "confidence_level":     row.get("confidence_level", ""),
                "issue_description":    row["issue_description"],
                "ai_diagnosis_summary": row.get("ai_diagnosis_summary", ""),
                "recommended_action":   row.get("recommended_action", ""),
                "safety_warning":       row.get("safety_warning", ""),
                "resolution_notes":     row.get("resolution_notes", ""),
                "content_vector":       vector,
            })

    batch = IndexDocumentsBatch()
    batch.add_upload_actions(docs)
    result = client.index_documents(batch)
    failed = [r for r in result if not r.succeeded]
    logger.info(f"  ✓ maintenance_cases: {len(docs) - len(failed)}/{len(docs)} cases → AI Search {CASES_INDEX}")


def ingest_parts_to_search(csv_path: Path):
    """parts_inventory.csv → AI Search cognitops-parts."""
    client = SearchClient(SEARCH_ENDPOINT, PARTS_INDEX, search_credential)
    docs   = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            docs.append({
                "id":                    row["part_id"],
                "part_id":               row["part_id"],
                "part_name":             row["part_name"],
                "compatible_asset_type": row["compatible_asset_type"],
                "stock_quantity":        int(row["stock_quantity"]),
                "unit_cost_usd":         float(row["unit_cost_usd"]),
                "supplier":              row["supplier"],
                "lead_time_days":        int(row["lead_time_days"]),
                "reorder_level":         int(row["reorder_level"]),
            })

    batch = IndexDocumentsBatch()
    batch.add_upload_actions(docs)
    result = client.index_documents(batch)
    logger.info(f"  ✓ parts_inventory: {len(docs)} parts → AI Search {PARTS_INDEX}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CognitOps AI Data Ingestion Pipeline")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Directory containing the 6 CSV datasets")
    parser.add_argument("--skip-embeddings", action="store_true",
                        help="Skip vector embedding generation (faster, no RAG)")
    parser.add_argument("--cosmos-only",  action="store_true", help="Only ingest to Cosmos DB")
    parser.add_argument("--search-only",  action="store_true", help="Only ingest to AI Search")
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    logger.info(f"CognitOps AI Data Ingestion Pipeline")
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Cosmos endpoint: {COSMOS_ENDPOINT[:40]}..." if COSMOS_ENDPOINT else "No COSMOS_ENDPOINT set")

    # ── Step 1: Create AI Search indexes ─────────────────────────────────────
    if not args.cosmos_only:
        logger.info("\n[1/3] Creating AI Search indexes...")
        create_indexes()

    # ── Step 2: Ingest to Cosmos DB ───────────────────────────────────────────
    if not args.search_only:
        logger.info("\n[2/3] Ingesting datasets to Cosmos DB...")
        ingest_equipment_assets(data_dir / "equipment_assets.csv")
        ingest_maintenance_cases(data_dir / "maintenance_cases.csv")
        ingest_sensor_readings(data_dir / "sensor_readings.csv")
        ingest_parts_inventory(data_dir / "parts_inventory.csv")
        ingest_technician_feedback(data_dir / "technician_feedback.csv")

    # ── Step 3: Ingest to AI Search with embeddings ───────────────────────────
    if not args.cosmos_only:
        logger.info("\n[3/3] Ingesting datasets to AI Search (with vector embeddings)...")
        if not args.skip_embeddings:
            ingest_manuals_to_search(data_dir / "manual_index.csv")
            ingest_cases_to_search(data_dir / "maintenance_cases.csv")
        ingest_parts_to_search(data_dir / "parts_inventory.csv")

    logger.info("\n✓ CognitOps AI data ingestion complete!")
    logger.info("  → Cosmos DB: equipment_assets, maintenance_cases, sensor_readings, parts, feedback")
    logger.info("  → AI Search: cognitops-manuals, cognitops-cases, cognitops-parts (with vectors)")


if __name__ == "__main__":
    main()
