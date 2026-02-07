"""Medical AI LLM System - Configuration"""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql://clinic_user:changeme_in_production@localhost:5433/clinic_ai",
        description="PostgreSQL connection string",
    )

    # LLM Configuration
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini", description="LLM model to use"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", description="OpenRouter API base URL"
    )

    # Research APIs
    ncbi_email: str = Field(default="", description="Email for NCBI/PubMed API")
    ncbi_api_key: Optional[str] = Field(
        default=None, description="Optional NCBI API key for higher rate limits"
    )

    # Epic FHIR
    epic_client_id: str = Field(default="", description="Epic OAuth2 Client ID")
    epic_fhir_base_url: str = Field(
        default="https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
        description="Epic FHIR API base URL",
    )
    epic_token_url: str = Field(
        default="https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token",
        description="Epic OAuth2 token URL",
    )

    # Cerner FHIR (optional)
    cerner_client_id: Optional[str] = Field(default=None)
    cerner_fhir_base_url: Optional[str] = Field(default=None)

    # Mirth Connect (optional)
    mirth_host: str = Field(default="localhost")
    mirth_port: int = Field(default=8443)
    mirth_username: str = Field(default="admin")
    mirth_password: str = Field(default="admin")

    # Security
    encryption_key: str = Field(
        default="", description="Fernet encryption key for PHI"
    )
    jwt_secret_key: str = Field(default="", description="JWT signing secret")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiry_hours: int = Field(default=24)

    # HIPAA Compliance
    audit_log_retention_years: int = Field(default=6)
    phi_encryption_enabled: bool = Field(default=True)

    # Embedding Configuration
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384)

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        """Warn if encryption key is not set."""
        if not v:
            import warnings

            warnings.warn(
                "ENCRYPTION_KEY not set. PHI encryption will fail. "
                "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        return v

    @property
    def database_url_sync(self) -> str:
        """Return synchronous database URL string."""
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
