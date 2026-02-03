"""HIPAA-Compliant Encryption Module"""

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.config import get_settings


class EncryptionService:
    """AES-256 encryption service for PHI data."""

    def __init__(self, encryption_key: Optional[str] = None):
        """Initialize with encryption key from settings or parameter."""
        settings = get_settings()
        key = encryption_key or settings.encryption_key

        if not key:
            raise ValueError(
                "Encryption key is required for HIPAA compliance. "
                "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        # Validate key format
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            raise ValueError(f"Invalid encryption key format: {e}")

    def encrypt(self, data: str) -> bytes:
        """
        Encrypt string data using AES-256 (Fernet).

        Args:
            data: Plaintext string to encrypt

        Returns:
            Encrypted bytes
        """
        if not data:
            return b""
        return self._fernet.encrypt(data.encode("utf-8"))

    def decrypt(self, encrypted_data: bytes) -> str:
        """
        Decrypt data back to plaintext string.

        Args:
            encrypted_data: Encrypted bytes

        Returns:
            Decrypted string

        Raises:
            InvalidToken: If decryption fails (wrong key or corrupted data)
        """
        if not encrypted_data:
            return ""
        try:
            return self._fernet.decrypt(encrypted_data).decode("utf-8")
        except InvalidToken:
            raise ValueError("Decryption failed - invalid key or corrupted data")

    def encrypt_dict(self, data: dict) -> bytes:
        """Encrypt a dictionary as JSON."""
        import json

        return self.encrypt(json.dumps(data))

    def decrypt_dict(self, encrypted_data: bytes) -> dict:
        """Decrypt bytes back to dictionary."""
        import json

        return json.loads(self.decrypt(encrypted_data))

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key."""
        return Fernet.generate_key().decode()

    @staticmethod
    def hash_data(data: str) -> str:
        """
        Create SHA-256 hash of data for integrity verification.

        Args:
            data: String to hash

        Returns:
            Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def derive_key_from_password(password: str, salt: Optional[bytes] = None) -> tuple:
        """
        Derive encryption key from password using PBKDF2.
        Useful for user-specific encryption.

        Args:
            password: User password
            salt: Optional salt bytes (generated if not provided)

        Returns:
            Tuple of (derived_key, salt)
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600000,  # OWASP 2023 recommendation
        )

        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode(), salt


# Singleton instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """Get or create singleton encryption service."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
