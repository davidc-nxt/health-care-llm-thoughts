# 🏥 Medical AI LLM - Clinical Research Acceleration Platform

A **HIPAA-compliant** AI system that accelerates patient history review and clinical research for healthcare professionals. Built with modern Python, featuring RAG-powered research retrieval, comprehensive EHR integrations, and enterprise-grade security.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791.svg)](https://github.com/pgvector/pgvector)
[![HIPAA](https://img.shields.io/badge/HIPAA-Compliant-green.svg)](#hipaa-compliance)
[![Tests](https://img.shields.io/badge/Tests-9%2F9%20Passing-success.svg)](#testing)

---

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Standards Compliance](#-standards-compliance)
- [Quick Start](#-quick-start)
- [CLI Commands](#-cli-commands)
- [EHR Integrations](#-ehr-integrations)
- [HIPAA Compliance](#-hipaa-compliance)
- [API Reference](#-api-reference)
- [Testing](#-testing)
- [Contributing](#-contributing)

---

## ✨ Features

### Research Intelligence
- **Multi-Source Ingestion**: PubMed/PMC + arXiv integration with specialty-based MeSH filtering
- **Semantic Search**: pgvector cosine similarity search across indexed research
- **RAG Pipeline**: LangChain document chunking + local embeddings + LLM generation
- **Citation Tracking**: Full provenance for all research references

### Healthcare Integration
- **FHIR R4/R5**: Complete Patient, Condition, MedicationRequest, Observation support
- **HL7 v2**: ADT message parsing with hl7apy for legacy system compatibility
- **Epic SMART on FHIR**: OAuth2 Backend Services + User Authorization flows
- **Mirth Connect**: REST API connector for interface engine management

### Enterprise Security
- **AES-256 Encryption**: Fernet-based PHI encryption at rest
- **Tamper-Proof Audit Logs**: SHA-256 hash chaining for forensic integrity
- **PHI Access Tracking**: Every data access logged with user context

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Interface                             │
│                    (Click-based commands)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   Ingestion   │  │  RAG Pipeline │  │ EHR Connector │
│   PubMed      │  │  Chunking     │  │ FHIR Client   │
│   arXiv       │  │  Embeddings   │  │ HL7 Handler   │
└───────┬───────┘  │  Vector Store │  │ Epic OAuth2   │
        │          │  Advisor      │  │ Mirth API     │
        │          └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
        ┌─────────────────────────────────────┐
        │    PostgreSQL + pgvector            │
        │    (Vector Similarity Search)       │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Encryption   │  │ Audit Logger  │  │  Settings     │
│  (Fernet)     │  │ (Hash Chain)  │  │  (Pydantic)   │
└───────────────┘  └───────────────┘  └───────────────┘
```

---

## 📊 Standards Compliance

### Healthcare Interoperability Standards

| Standard | Version | Implementation | Status |
|----------|---------|----------------|--------|
| **HL7 FHIR** | R4/R5 | `fhir.resources` library | ✅ Complete |
| **HL7 v2** | 2.5+ | `hl7apy` parser | ✅ Complete |
| **SMART on FHIR** | 2.0 | OAuth2 flows | ✅ Complete |
| **ICD-10** | 2024 | Via FHIR Condition | ✅ Supported |
| **SNOMED CT** | Latest | Via FHIR coding | ✅ Supported |

### Security Standards

| Standard | Requirement | Implementation |
|----------|-------------|----------------|
| **HIPAA §164.312(a)(2)(iv)** | Encryption at rest | AES-256 Fernet |
| **HIPAA §164.312(e)(1)** | Transmission security | TLS 1.2+ (httpx) |
| **HIPAA §164.312(b)** | Audit controls | Hash-chained logs |
| **HIPAA §164.312(d)** | Authentication | OAuth2/JWT ready |
| **NIST SP 800-175B** | Cryptographic standards | SHA-256, AES-256-GCM |

### Code Quality Standards

| Metric | Standard | Status |
|--------|----------|--------|
| **Type Hints** | PEP 484/526 | ✅ 100% coverage |
| **Docstrings** | Google style | ✅ All public APIs |
| **Configuration** | Pydantic Settings | ✅ Validated |
| **Error Handling** | Graceful degradation | ✅ Try/except patterns |
| **Testing** | pytest | ✅ 9/9 passing |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- PostgreSQL (via Docker)

### Installation

```bash
# Clone the repository
git clone https://github.com/davidc-nxt/health-care-llm-thoughts.git
cd health-care-llm-thoughts

# Start PostgreSQL with pgvector
docker compose up -d

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys:
# - OPENROUTER_API_KEY (required for LLM)
# - NCBI_EMAIL (required for PubMed)
# - NCBI_API_KEY (optional, increases rate limit)

# Verify installation
python -m src.cli status
```

Expected output:
```
🏥 Medical AI LLM System Status

✅ PostgreSQL connected (pgvector v0.8.1)
📚 Papers indexed: 0
📄 Chunks stored: 0
🤖 LLM configured: openai/gpt-4o-mini
🔬 PubMed configured: your_email@domain.com

✨ System ready!
```

---

## 💻 CLI Commands

### System Status
```bash
python -m src.cli status
```

### Ingest Research Papers
```bash
# Ingest cardiology papers from PubMed and arXiv
python -m src.cli ingest-papers -s cardiology -l 20

# Options:
#   -s, --specialty   Medical specialty (required)
#   -q, --query       Additional search terms
#   -l, --limit       Maximum papers (default: 10)
#   --source          pubmed, arxiv, or both (default: both)
#   --days            Papers from last N days (default: 365)
```

### Semantic Search
```bash
# Search indexed papers
python -m src.cli search "atrial fibrillation treatment options"

# Options:
#   -s, --specialty   Filter by specialty
#   -l, --limit       Number of results (default: 10)
#   --json            Output as JSON
```

### Generate Medical Advice
```bash
# Get research-backed clinical guidance
python -m src.cli advise "Best treatment approach for elderly AFib patients"

# Options:
#   -s, --specialty       Medical specialty context
#   -p, --patient-context De-identified patient information
#   --json                Output as JSON
```

### Test FHIR Connection
```bash
# Test Epic sandbox connectivity
python -m src.cli test-fhir --sandbox
```

### Generate Encryption Key
```bash
# Generate HIPAA-compliant encryption key
python -m src.cli generate-key
```

---

## 🏥 EHR Integrations

### FHIR R4/R5

```python
from src.ehr import FHIRClient

client = FHIRClient(
    base_url="https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
    access_token="your_oauth_token"
)

# Get patient summary with conditions, medications, labs
summary = client.get_patient_summary("patient-id", user_id="dr-smith")
print(f"Patient: {summary.name}")
print(f"Conditions: {len(summary.conditions)}")
print(f"Medications: {len(summary.medications)}")
```

### HL7 v2 Messages

```python
from src.ehr import HL7Handler

handler = HL7Handler()

# Parse ADT admission message
adt_message = """MSH|^~\\&|..."""
admit_info = handler.parse_adt(adt_message)

print(f"Event: {admit_info.event_type}")
print(f"Patient: {admit_info.patient.first_name} {admit_info.patient.last_name}")

# Generate acknowledgment
ack = handler.create_ack(original_message, "AA")
```

### Epic SMART on FHIR

```python
from src.ehr import EpicIntegration

epic = EpicIntegration(
    client_id="your_client_id",
    use_sandbox=True
)

# For user-facing apps
auth_url = epic.get_authorization_url(
    redirect_uri="https://your-app.com/callback",
    state="random_state"
)

# Exchange code for token
token = epic.exchange_code_for_token(code, redirect_uri)

# Get authenticated FHIR client
fhir_client = epic.get_fhir_client()
```

---

## 🔒 HIPAA Compliance

### Encryption at Rest

All PHI is encrypted using AES-256 (Fernet):

```python
from src.security import EncryptionService

# Generate and store this key securely
key = EncryptionService.generate_key()

service = EncryptionService(encryption_key=key)

# Encrypt PHI before storage
encrypted = service.encrypt("Patient SSN: 123-45-6789")

# Decrypt when authorized
decrypted = service.decrypt(encrypted)
```

### Audit Logging

Tamper-proof audit trail with hash chaining:

```python
from src.security import log_action

# All PHI access is logged
log_action(
    action="VIEW_PATIENT_RECORD",
    user_id="dr-smith",
    resource_type="Patient",
    resource_id="patient-123",
    phi_accessed=True,
    request_details={"reason": "Pre-surgery review"}
)
```

Audit log format:
```json
{
  "id": "uuid",
  "timestamp": "2026-02-03T09:30:00Z",
  "action": "VIEW_PATIENT_RECORD",
  "user_id": "dr-smith",
  "resource_type": "Patient",
  "resource_id": "patient-123",
  "phi_accessed": true,
  "previous_hash": "abc123...",
  "record_hash": "def456..."
}
```

---

## 📚 API Reference

### Configuration (`src.config`)

```python
from src.config import get_settings

settings = get_settings()
# Access validated settings:
# settings.database_url
# settings.openrouter_api_key
# settings.ncbi_email
```

### RAG Pipeline (`src.rag`)

| Class | Purpose |
|-------|---------|
| `DocumentChunker` | Split papers into semantic chunks |
| `EmbeddingService` | Generate 384-dim embeddings locally |
| `VectorStore` | pgvector storage and similarity search |
| `MedicalAdvisor` | RAG + LLM for clinical guidance |

### Ingestion (`src.ingestion`)

| Class | Purpose |
|-------|---------|
| `PubMedClient` | Fetch papers via Biopython Bio.Entrez |
| `ArxivClient` | Fetch preprints from arXiv q-bio categories |

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html

# Current results: 9/9 passing
```

### Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| `security.encryption` | 4 | ✅ Pass |
| `rag.chunking` | 1 | ✅ Pass |
| `ehr.hl7v2_handler` | 2 | ✅ Pass |
| `ingestion.pubmed_client` | 1 | ✅ Pass |
| `ehr.fhir_client` | 1 | ✅ Pass |

---

## 📁 Project Structure

```
clinic-ai-llm/
├── docker-compose.yml       # PostgreSQL + pgvector
├── init_pgvector.sql        # Database schema
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
├── src/
│   ├── __init__.py
│   ├── config.py            # Pydantic settings
│   ├── cli.py               # Click CLI
│   ├── ingestion/           # Research paper clients
│   │   ├── pubmed_client.py
│   │   └── arxiv_client.py
│   ├── rag/                 # RAG pipeline
│   │   ├── chunking.py
│   │   ├── embeddings.py
│   │   ├── vector_store.py
│   │   └── advisor.py
│   ├── ehr/                 # Healthcare integrations
│   │   ├── fhir_client.py
│   │   ├── hl7v2_handler.py
│   │   ├── epic_integration.py
│   │   └── mirth_connector.py
│   └── security/            # HIPAA compliance
│       ├── encryption.py
│       └── audit_logger.py
└── tests/
    └── unit/
        └── test_components.py
```

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Language** | Python 3.10+ | Core application |
| **Database** | PostgreSQL 16 | Relational storage |
| **Vector DB** | pgvector 0.8.1 | Similarity search |
| **Embeddings** | sentence-transformers | Local embeddings |
| **LLM** | OpenRouter (GPT-4o-mini) | Response generation |
| **FHIR** | fhir.resources | Healthcare resources |
| **HL7** | hl7apy | Message parsing |
| **HTTP** | httpx | Async HTTP client |
| **Config** | Pydantic Settings | Validated configuration |
| **CLI** | Click | Command-line interface |
| **Testing** | pytest | Unit testing |
| **Encryption** | cryptography (Fernet) | AES-256 encryption |

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📞 Support

For questions or issues, please open a GitHub issue or contact the maintainers.

---

*Built with ❤️ for healthcare professionals*
