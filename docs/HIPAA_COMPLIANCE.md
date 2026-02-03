# HIPAA Compliance Documentation

This document details the HIPAA compliance measures implemented in the Medical AI LLM system.

## Regulatory Framework

### HIPAA Security Rule Requirements

| § Reference | Requirement | Implementation |
|-------------|-------------|----------------|
| §164.312(a)(2)(iv) | Encryption and decryption | AES-256 Fernet encryption |
| §164.312(b) | Audit controls | Hash-chained audit logs |
| §164.312(c)(1) | Integrity | SHA-256 data hashing |
| §164.312(d) | Person/entity authentication | OAuth2/JWT ready |
| §164.312(e)(1) | Transmission security | TLS 1.2+ via httpx |
| §164.312(e)(2)(ii) | Encryption (transmission) | HTTPS for all APIs |

---

## Implementation Details

### 1. Encryption at Rest (§164.312(a)(2)(iv))

**Technology**: Fernet (AES-128-CBC with HMAC-SHA256)

**Location**: `src/security/encryption.py`

```python
from cryptography.fernet import Fernet

class EncryptionService:
    def encrypt(self, plaintext: str) -> bytes
    def decrypt(self, ciphertext: bytes) -> str
    def encrypt_dict(self, data: dict) -> bytes
    def decrypt_dict(self, ciphertext: bytes) -> dict
    @staticmethod
    def hash_data(data: str) -> str  # SHA-256
```

**Key Management**:
- Keys stored in environment variables (never in code)
- Key rotation supported via versioned encryption
- Keys should be stored in HSM or secrets manager in production

---

### 2. Audit Controls (§164.312(b))

**Technology**: Tamper-proof logging with SHA-256 hash chaining

**Location**: `src/security/audit_logger.py`

**Log Format**:
```json
{
  "id": "uuid-v4",
  "timestamp": "ISO-8601",
  "action": "VIEW_PATIENT_RECORD",
  "user_id": "authenticated_user",
  "resource_type": "Patient",
  "resource_id": "patient-id",
  "phi_accessed": true,
  "request_details": {},
  "previous_hash": "sha256-of-previous-record",
  "record_hash": "sha256-of-this-record"
}
```

**Tamper Detection**:
- Each log entry includes hash of previous entry
- Chain broken = tampering detected
- Verification via `AuditLogger.verify_chain()`

**Retention**: 
- Database configured for 6-year retention
- Configurable via `AUDIT_RETENTION_YEARS` environment variable

---

### 3. Integrity (§164.312(c)(1))

**Implementation**:
- All PHI hashed before logging (for verification, not storage)
- Database constraints prevent unauthorized modification
- Hash chain in audit logs detects tampering

---

### 4. Access Control Foundations (§164.312(d))

**Current Implementation**:
- User ID tracked on all operations
- Audit logging captures who accessed what
- OAuth2 integration ready (Epic SMART on FHIR)

**Production Enhancements Needed**:
- Role-Based Access Control (RBAC)
- Multi-factor authentication
- Session timeout enforcement

---

### 5. Transmission Security (§164.312(e))

**Implementation**:
- All external APIs use HTTPS via `httpx` client
- TLS 1.2+ enforced by default
- Certificate verification enabled

**APIs Protected**:
- OpenRouter (LLM)
- PubMed/NCBI
- arXiv
- Epic FHIR
- Mirth Connect

---

## Database Security

### PostgreSQL Configuration

```sql
-- All PHI tables include:
CREATE TABLE research_papers (
    -- ... fields ...
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log table with hash chain
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    action VARCHAR(100) NOT NULL,
    user_id VARCHAR(100),
    resource_type VARCHAR(100),
    resource_id VARCHAR(200),
    phi_accessed BOOLEAN DEFAULT FALSE,
    request_details JSONB,
    previous_hash VARCHAR(64),
    record_hash VARCHAR(64) NOT NULL
);

-- Index for efficient auditing
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_phi ON audit_logs(phi_accessed) WHERE phi_accessed = TRUE;
```

---

## Operational Requirements

### Environment Variables (Required for Compliance)

```bash
# Encryption
ENCRYPTION_KEY=your-fernet-key-here  # Generate with: python -m src.cli generate-key

# Audit
AUDIT_RETENTION_YEARS=6  # HIPAA minimum

# Database
DATABASE_URL=postgresql://...  # Use SSL in production
```

### Production Checklist

- [ ] Store encryption keys in HSM or secrets manager
- [ ] Enable SSL for PostgreSQL connections
- [ ] Configure database backup with encryption
- [ ] Implement log shipping to immutable storage
- [ ] Set up intrusion detection
- [ ] Enable MFA for all administrative access
- [ ] Document data flow for each PHI touchpoint
- [ ] Conduct annual risk assessment
- [ ] Train staff on HIPAA procedures

---

## Breach Notification Readiness

In case of a security incident, the audit system provides:

1. **What was accessed**: `resource_type`, `resource_id`
2. **When**: `timestamp`
3. **By whom**: `user_id`
4. **Chain of custody**: `previous_hash`, `record_hash`

Query for incident analysis:
```sql
SELECT * FROM audit_logs 
WHERE phi_accessed = TRUE 
AND timestamp BETWEEN '2026-01-01' AND '2026-01-31'
ORDER BY timestamp;
```

---

## Disclaimer

This implementation provides the technical foundation for HIPAA compliance. 
Full compliance requires:
- Administrative safeguards (policies, training)
- Physical safeguards (facility access)
- Organizational requirements (BAAs, policies)
- Regular risk assessments

Consult a HIPAA compliance officer for complete regulatory guidance.
