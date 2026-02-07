"""Medical AI LLM - MCP (Model Context Protocol) Server

Exposes the platform's research, EHR, and clinical decision support
capabilities as MCP tools and resources. Any MCP-compatible client
(Claude Desktop, Cursor, custom agents) can connect and interact.

Usage:
    python -m src.mcp_server          # stdio transport (default)
    python -m src.mcp_server --sse    # SSE transport for web clients
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.config import get_settings

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

settings = get_settings()

mcp = FastMCP(
    name="Medical AI Research Platform",
    instructions=(
        "A HIPAA-compliant medical AI system providing research paper search, "
        "clinical decision support, EHR integration (FHIR/HL7), and PHI encryption. "
        "All PHI access is audit-logged."
    ),
)

# ---------------------------------------------------------------------------
# Authentication helper
# ---------------------------------------------------------------------------

_MCP_API_KEY = os.getenv("MCP_API_KEY", settings.mcp_api_key)


def _check_auth(api_key: Optional[str] = None) -> None:
    """Validate API key if MCP_API_KEY is configured."""
    if not _MCP_API_KEY:
        return  # No key configured — open access (dev mode)
    if api_key != _MCP_API_KEY:
        raise ValueError(
            "Invalid or missing API key. "
            "Provide 'api_key' matching the server's MCP_API_KEY."
        )


# ═══════════════════════════════════════════════════════════════════════════
# TOOLS
# ═══════════════════════════════════════════════════════════════════════════

# ── 1. System Status ──────────────────────────────────────────────────────


@mcp.tool(
    name="system_status",
    description=(
        "Check system health: database connectivity, pgvector version, "
        "paper/chunk counts, and API configuration status."
    ),
)
def system_status(api_key: Optional[str] = None) -> str:
    """Return system health report."""
    _check_auth(api_key)

    from sqlalchemy import create_engine, text

    report = {"timestamp": datetime.now(tz=__import__('datetime').timezone.utc).isoformat()}

    try:
        engine = create_engine(settings.database_url_sync)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()
            report["database"] = "connected"
            report["pgvector_version"] = row[0] if row else "not installed"
            report["paper_count"] = conn.execute(
                text("SELECT COUNT(*) FROM research_papers")
            ).fetchone()[0]
            report["chunk_count"] = conn.execute(
                text("SELECT COUNT(*) FROM paper_chunks")
            ).fetchone()[0]
    except Exception as e:
        report["database"] = f"error: {e}"

    report["llm_configured"] = bool(settings.openrouter_api_key)
    report["llm_model"] = settings.openrouter_model
    report["pubmed_configured"] = bool(settings.ncbi_email)

    return json.dumps(report, indent=2)


# ── 2. Search Papers ──────────────────────────────────────────────────────


@mcp.tool(
    name="search_papers",
    description=(
        "Semantic search across indexed medical research papers using "
        "pgvector cosine similarity. Returns relevant chunks with "
        "similarity scores, titles, and source URLs."
    ),
)
def search_papers(
    query: str,
    specialty: Optional[str] = None,
    limit: int = 10,
    min_similarity: float = 0.3,
    api_key: Optional[str] = None,
) -> str:
    """Search indexed papers by semantic similarity."""
    _check_auth(api_key)

    from src.rag.vector_store import VectorStore

    vs = VectorStore()
    results = vs.search(
        query=query, specialty=specialty, top_k=limit, min_similarity=min_similarity
    )

    output = []
    for r in results:
        output.append(
            {
                "title": r["title"],
                "similarity": round(r["similarity"], 4),
                "content_preview": r["content"][:300],
                "source_url": r["source_url"],
                "specialty": r["metadata"].get("specialty"),
            }
        )

    return json.dumps(
        {"query": query, "result_count": len(output), "results": output},
        indent=2,
        default=str,
    )


# ── 3. Ingest Papers ─────────────────────────────────────────────────────


@mcp.tool(
    name="ingest_papers",
    description=(
        "Fetch and index research papers from PubMed and/or arXiv by "
        "medical specialty. Papers are chunked, embedded, and stored "
        "in pgvector for semantic search."
    ),
)
def ingest_papers(
    specialty: str,
    query: Optional[str] = None,
    source: str = "both",
    limit: int = 10,
    api_key: Optional[str] = None,
) -> str:
    """Ingest papers from PubMed/arXiv into the vector store."""
    _check_auth(api_key)

    from src.ingestion import ArxivClient, PubMedClient
    from src.rag.chunking import DocumentChunker
    from src.rag.vector_store import VectorStore

    search_query = query or f"{specialty} treatment guidelines recent advances"
    papers = []
    errors = []

    if source in ("pubmed", "both"):
        try:
            client = PubMedClient()
            papers.extend(
                client.search_and_fetch(
                    query=search_query, specialty=specialty, max_results=limit
                )
            )
        except Exception as e:
            errors.append(f"PubMed: {e}")

    if source in ("arxiv", "both"):
        try:
            client = ArxivClient()
            papers.extend(
                client.search(query=search_query, specialty=specialty, max_results=limit)
            )
        except Exception as e:
            errors.append(f"arXiv: {e}")

    if not papers:
        return json.dumps({"status": "no_papers_found", "errors": errors})

    chunker = DocumentChunker()
    vs = VectorStore()
    indexed = 0

    for paper in papers:
        try:
            paper_db_id = vs.store_paper(
                paper_id=paper.paper_id,
                title=paper.title,
                abstract=paper.abstract,
                authors=paper.authors,
                source=paper.source,
                specialty=paper.specialty or specialty,
                publication_date=paper.publication_date,
                source_url=paper.source_url,
            )
            chunks = chunker.chunk_paper(paper)
            vs.store_chunks(chunks, paper_db_id)
            indexed += 1
        except Exception as e:
            errors.append(f"Index {paper.paper_id}: {e}")

    return json.dumps(
        {
            "status": "success",
            "papers_found": len(papers),
            "papers_indexed": indexed,
            "errors": errors,
        },
        indent=2,
        default=str,
    )


# ── 4. Get Medical Advice ────────────────────────────────────────────────


@mcp.tool(
    name="get_medical_advice",
    description=(
        "Generate research-backed clinical guidance using RAG. "
        "Retrieves relevant papers and synthesizes advice with citations. "
        "Requires OPENROUTER_API_KEY to be configured."
    ),
)
def get_medical_advice(
    query: str,
    specialty: Optional[str] = None,
    patient_context: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Generate RAG-powered medical advice."""
    _check_auth(api_key)

    from src.rag.advisor import MedicalAdvisor

    try:
        advisor = MedicalAdvisor()
        result = advisor.advise(
            query=query,
            specialty=specialty,
            patient_context=patient_context,
            user_id="mcp_client",
        )
        return json.dumps(result, indent=2, default=str)
    except ValueError as e:
        return json.dumps({"error": str(e), "hint": "Set OPENROUTER_API_KEY"})


# ── 5. Get Patient Summary (FHIR) ────────────────────────────────────────


@mcp.tool(
    name="get_patient_summary",
    description=(
        "Retrieve a comprehensive FHIR patient summary including "
        "demographics, active conditions, medications, and recent "
        "observations (labs/vitals). Requires FHIR server access."
    ),
)
def get_patient_summary(
    patient_id: str,
    fhir_base_url: Optional[str] = None,
    access_token: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Fetch FHIR patient summary."""
    _check_auth(api_key)

    from src.ehr.fhir_client import FHIRClient

    client = FHIRClient(base_url=fhir_base_url, access_token=access_token)
    summary = client.get_patient_summary(patient_id, user_id="mcp_client")

    if not summary:
        return json.dumps({"error": f"Patient {patient_id} not found"})

    return json.dumps(
        {
            "patient_id": summary.patient_id,
            "name": summary.name,
            "birth_date": str(summary.birth_date) if summary.birth_date else None,
            "gender": summary.gender,
            "conditions": summary.conditions,
            "medications": summary.medications,
            "observations": summary.observations[:10],
        },
        indent=2,
        default=str,
    )


# ── 6. Parse HL7 Message ─────────────────────────────────────────────────


@mcp.tool(
    name="parse_hl7_message",
    description=(
        "Parse an HL7 v2 ADT (Admission/Discharge/Transfer) message. "
        "Extracts patient demographics, event type, attending doctor, "
        "location, and diagnosis information."
    ),
)
def parse_hl7_message(
    raw_message: str,
    api_key: Optional[str] = None,
) -> str:
    """Parse HL7 v2 ADT message."""
    _check_auth(api_key)

    from src.ehr.hl7v2_handler import HL7Handler

    handler = HL7Handler()
    admit = handler.parse_adt(raw_message, user_id="mcp_client")

    if not admit:
        return json.dumps({"error": "Failed to parse HL7 message"})

    return json.dumps(
        {
            "event_type": admit.event_type,
            "event_description": HL7Handler.get_event_description(admit.event_type),
            "patient": {
                "id": admit.patient.patient_id,
                "first_name": admit.patient.first_name,
                "last_name": admit.patient.last_name,
                "gender": admit.patient.gender,
                "mrn": admit.patient.mrn,
            },
            "admit_datetime": str(admit.admit_datetime) if admit.admit_datetime else None,
            "attending_doctor": admit.attending_doctor,
            "location": admit.location,
            "diagnosis": admit.diagnosis,
        },
        indent=2,
        default=str,
    )


# ── 7. Encrypt PHI ───────────────────────────────────────────────────────


@mcp.tool(
    name="encrypt_phi",
    description=(
        "Encrypt sensitive patient data (PHI) using AES-256 Fernet encryption "
        "for HIPAA-compliant storage. Requires ENCRYPTION_KEY to be configured."
    ),
)
def encrypt_phi(
    data: str,
    api_key: Optional[str] = None,
) -> str:
    """Encrypt data using Fernet AES-256."""
    _check_auth(api_key)

    from src.security.encryption import EncryptionService

    try:
        svc = EncryptionService()
        encrypted = svc.encrypt(data)
        return json.dumps(
            {"encrypted": encrypted.decode("utf-8"), "algorithm": "AES-256-Fernet"}
        )
    except ValueError as e:
        return json.dumps({"error": str(e), "hint": "Set ENCRYPTION_KEY in .env"})


# ── 8. Decrypt PHI ───────────────────────────────────────────────────────


@mcp.tool(
    name="decrypt_phi",
    description=(
        "Decrypt previously encrypted PHI data. Requires the same "
        "ENCRYPTION_KEY used during encryption."
    ),
)
def decrypt_phi(
    encrypted_data: str,
    api_key: Optional[str] = None,
) -> str:
    """Decrypt Fernet-encrypted data."""
    _check_auth(api_key)

    from src.security.encryption import EncryptionService

    try:
        svc = EncryptionService()
        decrypted = svc.decrypt(encrypted_data.encode("utf-8"))
        return json.dumps({"decrypted": decrypted})
    except ValueError as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# RESOURCES
# ═══════════════════════════════════════════════════════════════════════════


@mcp.resource(
    uri="medical://specialties",
    name="Medical Specialties",
    description="List of supported medical specialties with MeSH/arXiv mappings.",
)
def get_specialties() -> str:
    """Return supported specialties."""
    from src.ingestion.pubmed_client import PubMedClient

    specialties = {}
    for name, terms in PubMedClient.SPECIALTY_MESH_TERMS.items():
        specialties[name] = {"mesh_terms": terms}

    return json.dumps(specialties, indent=2)


@mcp.resource(
    uri="medical://stats",
    name="Platform Statistics",
    description="Current paper/chunk counts, index type, and embedding model info.",
)
def get_stats() -> str:
    """Return platform statistics."""
    from sqlalchemy import create_engine, text

    stats = {
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "llm_model": settings.openrouter_model,
    }

    try:
        engine = create_engine(settings.database_url_sync)
        with engine.connect() as conn:
            stats["paper_count"] = conn.execute(
                text("SELECT COUNT(*) FROM research_papers")
            ).fetchone()[0]
            stats["chunk_count"] = conn.execute(
                text("SELECT COUNT(*) FROM paper_chunks")
            ).fetchone()[0]
            stats["specialty_distribution"] = {}
            rows = conn.execute(
                text(
                    "SELECT specialty, COUNT(*) FROM research_papers "
                    "WHERE specialty IS NOT NULL GROUP BY specialty"
                )
            )
            for row in rows:
                stats["specialty_distribution"][row[0]] = row[1]
    except Exception as e:
        stats["database_error"] = str(e)

    return json.dumps(stats, indent=2)


@mcp.resource(
    uri="medical://fhir/capabilities",
    name="FHIR Capabilities",
    description="Supported FHIR resource types and EHR integration endpoints.",
)
def get_fhir_capabilities() -> str:
    """Return FHIR capabilities."""
    return json.dumps(
        {
            "fhir_version": "R4/R5",
            "supported_resources": [
                {
                    "type": "Patient",
                    "operations": ["read", "search"],
                    "description": "Demographics, identifiers",
                },
                {
                    "type": "Condition",
                    "operations": ["search"],
                    "description": "Active diagnoses (ICD-10, SNOMED CT)",
                },
                {
                    "type": "MedicationRequest",
                    "operations": ["search"],
                    "description": "Active prescriptions",
                },
                {
                    "type": "Observation",
                    "operations": ["search"],
                    "description": "Lab results, vital signs",
                },
            ],
            "ehr_integrations": [
                {
                    "system": "Epic",
                    "auth": "SMART on FHIR OAuth2",
                    "modes": ["Backend Services (JWT)", "User Authorization"],
                },
                {
                    "system": "Mirth Connect",
                    "protocol": "REST API",
                    "capabilities": ["Channel management", "Message routing"],
                },
            ],
            "hl7v2_support": {
                "versions": ["2.5+"],
                "message_types": ["ADT", "ORU", "ORM", "SIU", "MDM"],
                "parser": "hl7apy",
            },
            "default_fhir_url": settings.epic_fhir_base_url,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = "stdio"
    if "--sse" in sys.argv:
        transport = "sse"
    mcp.run(transport=transport)
