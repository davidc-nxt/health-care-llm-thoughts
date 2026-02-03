# Healthcare Interoperability Standards

This document details the healthcare interoperability standards implemented in the Medical AI LLM system.

---

## HL7 FHIR (Fast Healthcare Interoperability Resources)

### Versions Supported
- **FHIR R4** (4.0.1) - Primary
- **FHIR R5** (5.0.0) - Via fhir.resources library

### Resources Implemented

| Resource | Purpose | Implementation |
|----------|---------|----------------|
| `Patient` | Demographics, identifiers | Full CRUD via FHIRClient |
| `Condition` | Diagnoses, problems | Read with ICD-10/SNOMED |
| `MedicationRequest` | Prescriptions | Active medication retrieval |
| `Observation` | Labs, vitals | Category-filtered queries |
| `Bundle` | Resource collections | Transaction/collection support |

### FHIR Client Usage

```python
from src.ehr import FHIRClient, PatientSummary

client = FHIRClient(
    base_url="https://fhir.epic.com/api/FHIR/R4",
    access_token="bearer_token"
)

# Get complete patient summary
summary: PatientSummary = client.get_patient_summary("patient-id")

# Access individual resources
patient = client.get_patient("patient-id")
conditions = client.get_conditions("patient-id")
medications = client.get_medications("patient-id")
observations = client.get_observations("patient-id", category="laboratory")
```

### Terminology Support

| System | Standard | OID |
|--------|----------|-----|
| Diagnosis Codes | ICD-10-CM | 2.16.840.1.113883.6.90 |
| Clinical Terms | SNOMED CT | 2.16.840.1.113883.6.96 |
| Drug Codes | RxNorm | 2.16.840.1.113883.6.88 |
| Lab Codes | LOINC | 2.16.840.1.113883.6.1 |

---

## HL7 Version 2.x

### Versions Supported
- HL7 v2.3, v2.4, v2.5, v2.5.1
- v2.5 is the default

### Message Types Implemented

| Type | Name | Implementation |
|------|------|----------------|
| ADT | Admission/Discharge/Transfer | Full parsing |
| ORU | Observation Result | Structure ready |
| ORM | Order Message | Structure ready |
| ACK | Acknowledgment | Generation |

### ADT Events Supported

| Event | Description |
|-------|-------------|
| A01 | Admit/Visit Notification |
| A02 | Transfer |
| A03 | Discharge/End Visit |
| A04 | Register a Patient |
| A08 | Update Patient Information |
| A11 | Cancel Admit |
| A13 | Cancel Discharge |

### HL7 Handler Usage

```python
from src.ehr import HL7Handler, HL7AdmitInfo

handler = HL7Handler()

# Parse ADT message
adt_message = """
MSH|^~\\&|SENDING_APP|SENDING_FAC|RECEIVING_APP|RECEIVING_FAC|20240101120000||ADT^A01|MSG00001|P|2.5
PID|1||12345^^^HOSP^MRN||DOE^JOHN^A||19800101|M
PV1|1|I|ICU^101^A||||1234^SMITH^JANE^M^MD
"""

admit_info: HL7AdmitInfo = handler.parse_adt(adt_message)
print(f"Patient: {admit_info.patient.first_name} {admit_info.patient.last_name}")
print(f"Event: {admit_info.event_type}")

# Generate ACK response
ack = handler.create_ack(original_message, "AA")  # AA = Accept
```

### Segment Support

| Segment | Name | Fields Parsed |
|---------|------|---------------|
| MSH | Message Header | Sending/Receiving apps, datetime, message type |
| PID | Patient Identification | ID, name, DOB, gender, address, phone |
| PV1 | Patient Visit | Location, attending physician, admit/discharge dates |
| DG1 | Diagnosis | Diagnosis code and description |

---

## SMART on FHIR (OAuth2)

### Flows Implemented

#### 1. Backend Services (System-to-System)
```python
from src.ehr import EpicIntegration

epic = EpicIntegration(
    client_id="your_client_id",
    private_key=private_key_pem,  # RSA for JWT signing
    use_sandbox=True
)

# Authenticate without user interaction
token = epic.authenticate_backend_service()
fhir_client = epic.get_fhir_client()
```

#### 2. Authorization Code (User-Facing)
```python
# Step 1: Get authorization URL
auth_url = epic.get_authorization_url(
    redirect_uri="https://your-app.com/callback",
    state="random_csrf_token",
    scopes=["patient/Patient.read", "patient/Condition.read"]
)
# Redirect user to auth_url

# Step 2: Exchange code for token (in callback)
token = epic.exchange_code_for_token(code, redirect_uri)
```

### Scopes Supported

| Scope | Permission |
|-------|------------|
| `system/Patient.read` | Read any patient (backend) |
| `system/Condition.read` | Read any diagnosis (backend) |
| `patient/Patient.read` | Read authorized patient |
| `patient/Condition.read` | Read patient's diagnoses |
| `launch/patient` | Get patient context from launch |

---

## Mirth Connect Integration

### API Version
- Mirth Connect REST API (3.x, 4.x compatible)

### Operations Supported

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List Channels | GET | `/api/channels` |
| Channel Status | GET | `/api/channels/{id}/status` |
| Send Message | POST | `/api/channels/{id}/messages` |
| Start Channel | POST | `/api/channels/{id}/_start` |
| Stop Channel | POST | `/api/channels/{id}/_stop` |
| Statistics | GET | `/api/channels/{id}/statistics` |

### Connector Usage

```python
from src.ehr import MirthConnector

mirth = MirthConnector(
    host="mirth.hospital.local",
    port=8443,
    username="admin",
    password="secure_password"
)

# Login and check status
mirth.login()
status = mirth.get_server_status()

# List all channels
channels = mirth.list_channels()

# Send HL7 message to a channel
result = mirth.send_message(
    channel_id="channel-uuid",
    message=hl7_message,
    user_id="system"
)
```

---

## Data Flow Architecture

```
┌─────────────────┐     FHIR R4      ┌─────────────────┐
│   Epic EHR      │ ◄──────────────► │  FHIR Client    │
│   Cerner EHR    │                  │  (fhir.resources)│
└─────────────────┘                  └────────┬────────┘
                                              │
┌─────────────────┐                           │
│  Legacy Systems │    HL7 v2                 │
│  (Lab, Radiology)│ ◄──────────┐             │
└─────────────────┘             │             │
                                ▼             │
┌─────────────────┐     ┌─────────────────┐   │
│  Mirth Connect  │ ◄──►│  HL7 Handler    │   │
│  (Interface     │     │  (hl7apy)       │   │
│   Engine)       │     └─────────────────┘   │
└─────────────────┘                           │
                                              ▼
                                 ┌─────────────────────┐
                                 │  Medical AI LLM     │
                                 │  (This System)      │
                                 └─────────────────────┘
```

---

## Conformance Testing

### FHIR Validation
- Resources validated via `fhir.resources` Pydantic models
- Supports `model_validate()` for strict parsing

### HL7 v2 Testing
- Parser tested with ADT A01 messages
- ACK generation verified

### Epic Sandbox
```bash
# Test Epic FHIR connectivity
python -m src.cli test-fhir --sandbox

# Expected output:
# ✅ Connected to Epic FHIR
#    FHIR Version: 4.0.1
#    Software: Epic
```

---

## References

- [HL7 FHIR R4 Specification](https://hl7.org/fhir/R4/)
- [HL7 v2 Specification](https://www.hl7.org/implement/standards/product_brief.cfm?product_id=185)
- [SMART on FHIR](https://docs.smarthealthit.org/)
- [Epic on FHIR](https://fhir.epic.com/)
- [Mirth Connect User Guide](https://docs.nextgen.com/bundle/Mirth_User_Guide)
