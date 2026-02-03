"""Epic FHIR Integration with OAuth2 SMART on FHIR"""

import base64
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt

from src.config import get_settings
from src.ehr.fhir_client import FHIRClient
from src.security.audit_logger import log_action


@dataclass
class EpicTokenResponse:
    """OAuth2 token response from Epic."""

    access_token: str
    token_type: str
    expires_in: int
    scope: str
    patient: Optional[str] = None  # Patient context if applicable


class EpicIntegration:
    """
    Epic EHR integration using SMART on FHIR.

    Supports:
    - Backend Services (system-to-system) authentication
    - Patient-facing app authentication
    - Sandbox and production endpoints
    """

    # Epic sandbox endpoints
    SANDBOX_BASE_URL = "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"
    SANDBOX_TOKEN_URL = "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token"

    # Default scopes for backend services
    BACKEND_SCOPES = [
        "system/Patient.read",
        "system/Condition.read",
        "system/MedicationRequest.read",
        "system/Observation.read",
    ]

    def __init__(
        self,
        client_id: Optional[str] = None,
        private_key: Optional[str] = None,
        base_url: Optional[str] = None,
        token_url: Optional[str] = None,
        use_sandbox: bool = True,
    ):
        """
        Initialize Epic integration.

        Args:
            client_id: Epic OAuth2 Client ID
            private_key: RSA private key for JWT signing (backend services)
            base_url: FHIR API base URL
            token_url: OAuth2 token endpoint
            use_sandbox: Use Epic sandbox endpoints
        """
        settings = get_settings()

        self._client_id = client_id or settings.epic_client_id
        self._private_key = private_key
        
        if use_sandbox:
            self._base_url = self.SANDBOX_BASE_URL
            self._token_url = self.SANDBOX_TOKEN_URL
        else:
            self._base_url = base_url or settings.epic_fhir_base_url
            self._token_url = token_url or settings.epic_token_url

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._fhir_client: Optional[FHIRClient] = None

    def authenticate_backend_service(self) -> EpicTokenResponse:
        """
        Authenticate using Backend Services flow (JWT assertion).

        This is for system-to-system communication without user interaction.
        Requires a registered RSA public key with Epic.

        Returns:
            EpicTokenResponse with access token
        """
        if not self._private_key:
            raise ValueError(
                "Private key is required for backend service authentication. "
                "Generate an RSA key pair and register the public key with Epic."
            )

        log_action(
            action="EPIC_BACKEND_AUTH",
            resource_type="OAuth2",
            request_details={"client_id": self._client_id},
        )

        # Create JWT assertion
        now = int(time.time())
        claims = {
            "iss": self._client_id,
            "sub": self._client_id,
            "aud": self._token_url,
            "jti": f"jwt-{now}",
            "exp": now + 300,  # 5 minutes
        }

        assertion = jwt.encode(claims, self._private_key, algorithm="RS384")

        # Request token
        with httpx.Client() as client:
            response = client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                    "client_assertion": assertion,
                    "scope": " ".join(self.BACKEND_SCOPES),
                },
            )
            response.raise_for_status()
            data = response.json()

        token_response = EpicTokenResponse(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in", 3600),
            scope=data.get("scope", ""),
        )

        self._access_token = token_response.access_token
        self._token_expires_at = time.time() + token_response.expires_in - 60

        return token_response

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[list[str]] = None,
        aud: Optional[str] = None,
    ) -> str:
        """
        Generate OAuth2 authorization URL for user-facing apps.

        Args:
            redirect_uri: Callback URL after authorization
            state: State parameter for CSRF protection
            scopes: Requested scopes (default: patient read access)
            aud: FHIR server URL (audience)

        Returns:
            Authorization URL to redirect user to
        """
        if scopes is None:
            scopes = ["patient/Patient.read", "patient/Condition.read", "launch/patient"]

        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "aud": aud or self._base_url,
        }

        # Epic uses .well-known/smart-configuration for auth URL
        auth_url = self._token_url.replace("/oauth2/token", "/oauth2/authorize")
        return f"{auth_url}?{urlencode(params)}"

    def exchange_code_for_token(
        self, code: str, redirect_uri: str
    ) -> EpicTokenResponse:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from callback
            redirect_uri: Same redirect URI used in authorization

        Returns:
            EpicTokenResponse with access token
        """
        log_action(
            action="EPIC_CODE_EXCHANGE",
            resource_type="OAuth2",
            request_details={"client_id": self._client_id},
        )

        with httpx.Client() as client:
            response = client.post(
                self._token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self._client_id,
                },
            )
            response.raise_for_status()
            data = response.json()

        token_response = EpicTokenResponse(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in", 3600),
            scope=data.get("scope", ""),
            patient=data.get("patient"),  # Patient ID from launch context
        )

        self._access_token = token_response.access_token
        self._token_expires_at = time.time() + token_response.expires_in - 60

        return token_response

    def get_fhir_client(self) -> FHIRClient:
        """
        Get authenticated FHIR client.

        Returns:
            FHIRClient configured with current access token
        """
        if self._fhir_client is None:
            self._fhir_client = FHIRClient(
                base_url=self._base_url, access_token=self._access_token
            )
        elif self._access_token:
            self._fhir_client.set_access_token(self._access_token)

        return self._fhir_client

    def is_token_valid(self) -> bool:
        """Check if current token is valid and not expired."""
        return self._access_token is not None and time.time() < self._token_expires_at

    def test_connection(self) -> dict:
        """
        Test connection to Epic FHIR server.

        Returns:
            Server metadata or error information
        """
        try:
            with httpx.Client() as client:
                response = client.get(f"{self._base_url}/metadata")
                response.raise_for_status()
                metadata = response.json()
                return {
                    "status": "connected",
                    "fhir_version": metadata.get("fhirVersion"),
                    "software": metadata.get("software", {}).get("name"),
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
