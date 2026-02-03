"""Unit tests for security module."""

import pytest
from unittest.mock import patch, MagicMock


class TestEncryptionService:
    """Tests for encryption service."""

    def test_generate_key(self):
        """Test encryption key generation."""
        from src.security.encryption import EncryptionService

        key = EncryptionService.generate_key()
        assert isinstance(key, str)
        assert len(key) == 44  # Fernet key length

    def test_encrypt_decrypt(self):
        """Test encrypt/decrypt roundtrip."""
        from src.security.encryption import EncryptionService

        key = EncryptionService.generate_key()
        service = EncryptionService(encryption_key=key)

        original = "Protected Health Information"
        encrypted = service.encrypt(original)
        decrypted = service.decrypt(encrypted)

        assert decrypted == original
        assert encrypted != original.encode()

    def test_encrypt_dict(self):
        """Test dictionary encryption."""
        from src.security.encryption import EncryptionService

        key = EncryptionService.generate_key()
        service = EncryptionService(encryption_key=key)

        data = {"patient_id": "12345", "diagnosis": "Test condition"}
        encrypted = service.encrypt_dict(data)
        decrypted = service.decrypt_dict(encrypted)

        assert decrypted == data

    def test_hash_data(self):
        """Test data hashing."""
        from src.security.encryption import EncryptionService

        hash1 = EncryptionService.hash_data("test data")
        hash2 = EncryptionService.hash_data("test data")
        hash3 = EncryptionService.hash_data("different data")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA-256 hex length


class TestDocumentChunker:
    """Tests for document chunking."""

    def test_chunk_paper(self):
        """Test paper chunking."""
        from src.rag.chunking import DocumentChunker
        from src.ingestion.pubmed_client import ResearchPaper
        from datetime import datetime

        chunker = DocumentChunker(chunk_size=200, chunk_overlap=20)

        paper = ResearchPaper(
            paper_id="test:123",
            title="Test Paper Title",
            abstract="This is a test abstract. " * 20,
            authors=["Author One", "Author Two"],
            source="pubmed",
            specialty="cardiology",
            publication_date=datetime.now(),
            source_url="https://example.com/paper",
        )

        chunks = chunker.chunk_paper(paper)

        assert len(chunks) > 0
        assert chunks[0].paper_id == "test:123"
        assert "cardiology" in str(chunks[0].metadata)


class TestHL7Handler:
    """Tests for HL7 v2 handler."""

    def test_parse_adt_message(self):
        """Test ADT message parsing."""
        from src.ehr.hl7v2_handler import HL7Handler

        handler = HL7Handler()

        # Sample ADT A01 message
        adt_message = (
            "MSH|^~\\&|SENDING_APP|SENDING_FAC|RECEIVING_APP|RECEIVING_FAC|"
            "20240101120000||ADT^A01|MSG00001|P|2.5\r"
            "PID|1||12345^^^HOSP^MRN||DOE^JOHN^A||19800101|M\r"
            "PV1|1|I|ICU^101^A||||1234^SMITH^JANE^M^MD"
        )

        with patch("src.security.audit_logger.log_action"):
            result = handler.parse_adt(adt_message)

        assert result is not None
        assert result.event_type == "A01"
        assert result.patient.last_name == "DOE"
        assert result.patient.first_name == "JOHN"

    def test_ack_generation(self):
        """Test ACK message generation."""
        from src.ehr.hl7v2_handler import HL7Handler
        from hl7apy.parser import parse_message

        handler = HL7Handler()

        original = parse_message(
            "MSH|^~\\&|APP1|FAC1|APP2|FAC2|20240101||ADT^A01|12345|P|2.5\r"
            "PID|1||99999"
        )

        ack = handler.create_ack(original, "AA")

        assert "ACK" in ack
        assert "AA" in ack
        assert "12345" in ack  # Original message control ID


class TestPubMedClient:
    """Tests for PubMed client."""

    def test_specialty_mesh_terms(self):
        """Test specialty to MeSH term mapping."""
        from src.ingestion.pubmed_client import PubMedClient

        # Just test the mapping exists
        assert "cardiology" in PubMedClient.SPECIALTY_MESH_TERMS
        assert "Heart Diseases" in PubMedClient.SPECIALTY_MESH_TERMS["cardiology"]


class TestFHIRClient:
    """Tests for FHIR client."""

    def test_patient_summary_creation(self):
        """Test patient summary dataclass."""
        from src.ehr.fhir_client import PatientSummary
        from datetime import date

        summary = PatientSummary(
            patient_id="123",
            name="John Doe",
            birth_date=date(1980, 1, 1),
            gender="male",
            conditions=[{"code": "123", "display": "Test Condition"}],
            medications=[{"code": "456", "display": "Test Medication"}],
            observations=[{"code": "789", "display": "Test Observation"}],
            raw_resources={},
        )

        assert summary.patient_id == "123"
        assert len(summary.conditions) == 1
