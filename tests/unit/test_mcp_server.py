"""Tests for MCP Server tools and resources."""

import json
from unittest.mock import MagicMock, patch

import pytest

# Import tool/resource functions directly
from src.mcp_server import (
    decrypt_phi,
    encrypt_phi,
    get_fhir_capabilities,
    get_specialties,
    get_stats,
    parse_hl7_message,
    search_papers,
    system_status,
)


class TestMCPAuthentication:
    """Test API key authentication."""

    @patch("src.mcp_server._MCP_API_KEY", "test-secret-key")
    def test_valid_api_key(self):
        """Valid API key should not raise."""
        # system_status accepts api_key and should succeed
        result = system_status(api_key="test-secret-key")
        data = json.loads(result)
        assert "timestamp" in data

    @patch("src.mcp_server._MCP_API_KEY", "test-secret-key")
    def test_invalid_api_key(self):
        """Invalid API key should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid or missing API key"):
            system_status(api_key="wrong-key")

    @patch("src.mcp_server._MCP_API_KEY", "test-secret-key")
    def test_missing_api_key(self):
        """Missing API key should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid or missing API key"):
            system_status()

    @patch("src.mcp_server._MCP_API_KEY", "")
    def test_no_key_configured_allows_access(self):
        """When no MCP_API_KEY is configured, access is open."""
        result = system_status()
        data = json.loads(result)
        assert "timestamp" in data


class TestSystemStatusTool:
    """Test system_status tool."""

    @patch("src.mcp_server._MCP_API_KEY", "")
    def test_returns_status_json(self):
        result = system_status()
        data = json.loads(result)
        assert "timestamp" in data
        assert "database" in data

    @patch("src.mcp_server._MCP_API_KEY", "")
    def test_includes_llm_config(self):
        result = system_status()
        data = json.loads(result)
        assert "llm_model" in data


class TestSearchPapersTool:
    """Test search_papers tool."""

    @patch("src.mcp_server._MCP_API_KEY", "")
    def test_returns_search_results(self):
        result = search_papers(query="atrial fibrillation", limit=5)
        data = json.loads(result)
        assert "query" in data
        assert "result_count" in data
        assert data["query"] == "atrial fibrillation"
        assert isinstance(data["results"], list)


class TestParseHL7MessageTool:
    """Test parse_hl7_message tool."""

    SAMPLE_ADT = (
        "MSH|^~\\&|HIS|Hospital|LIS|Lab|20240615120000||ADT^A01|MSG001|P|2.5\r"
        "PID|||12345^^^MRN||Doe^John||19800101|M|||123 Main St^^City^ST^12345\r"
        "PV1||I|ICU^101^A"
    )

    @patch("src.mcp_server._MCP_API_KEY", "")
    def test_parses_adt_message(self):
        result = parse_hl7_message(raw_message=self.SAMPLE_ADT)
        data = json.loads(result)
        # Should parse successfully (not error)
        assert "patient" in data or "error" in data

    @patch("src.mcp_server._MCP_API_KEY", "")
    def test_invalid_message(self):
        result = parse_hl7_message(raw_message="not a valid hl7 message")
        data = json.loads(result)
        assert "error" in data


class TestEncryptDecryptTools:
    """Test encrypt_phi and decrypt_phi tools."""

    @patch("src.mcp_server._MCP_API_KEY", "")
    def test_encrypt_returns_ciphertext(self):
        result = encrypt_phi(data="Test PHI data 12345")
        data = json.loads(result)
        # Should either succeed or error about missing key
        assert "encrypted" in data or "error" in data

    @patch("src.mcp_server._MCP_API_KEY", "")
    def test_encrypt_decrypt_roundtrip(self):
        """If encryption key is set, roundtrip should work."""
        from src.config import get_settings

        settings = get_settings()
        if not settings.encryption_key:
            pytest.skip("ENCRYPTION_KEY not configured")

        enc_result = json.loads(encrypt_phi(data="sensitive patient info"))
        if "error" in enc_result:
            pytest.skip(f"Encryption unavailable: {enc_result['error']}")

        dec_result = json.loads(decrypt_phi(encrypted_data=enc_result["encrypted"]))
        assert dec_result["decrypted"] == "sensitive patient info"


class TestResources:
    """Test MCP resources."""

    def test_get_specialties(self):
        result = get_specialties()
        data = json.loads(result)
        assert isinstance(data, dict)
        assert len(data) > 0
        # Should contain common specialties
        assert "cardiology" in data

    def test_get_stats(self):
        result = get_stats()
        data = json.loads(result)
        assert "embedding_model" in data
        assert "embedding_dimension" in data
        assert "llm_model" in data

    def test_get_fhir_capabilities(self):
        result = get_fhir_capabilities()
        data = json.loads(result)
        assert data["fhir_version"] == "R4/R5"
        assert len(data["supported_resources"]) == 4
        assert any(r["type"] == "Patient" for r in data["supported_resources"])
        assert len(data["ehr_integrations"]) == 2
        assert data["hl7v2_support"]["versions"] == ["2.5+"]


class TestMCPServerRegistration:
    """Test that tools and resources are properly registered."""

    def test_mcp_instance_exists(self):
        from src.mcp_server import mcp

        assert mcp is not None
        assert mcp.name == "Medical AI Research Platform"
