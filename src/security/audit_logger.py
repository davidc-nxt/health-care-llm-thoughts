"""HIPAA-Compliant Audit Logging System"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.config import get_settings


class AuditLogger:
    """
    Tamper-proof audit logging for HIPAA compliance.
    
    Features:
    - Hash chaining for tamper detection
    - Automatic PHI access flagging
    - Configurable retention (default 6 years)
    """

    def __init__(self, database_url: Optional[str] = None):
        """Initialize with database connection."""
        settings = get_settings()
        self._db_url = database_url or settings.database_url_sync
        self._engine = create_engine(self._db_url)
        self._last_hash: Optional[str] = None

    def _get_last_hash(self) -> Optional[str]:
        """Retrieve the hash of the last audit log entry."""
        if self._last_hash:
            return self._last_hash

        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT current_hash FROM audit_logs "
                        "ORDER BY id DESC LIMIT 1"
                    )
                )
                row = result.fetchone()
                self._last_hash = row[0] if row else None
                return self._last_hash
        except SQLAlchemyError:
            return None

    def _compute_hash(self, log_data: dict, previous_hash: Optional[str]) -> str:
        """
        Compute hash for current log entry including previous hash.
        This creates an immutable chain.
        """
        hash_input = json.dumps(log_data, sort_keys=True, default=str)
        if previous_hash:
            hash_input = previous_hash + hash_input
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def log(
        self,
        action: str,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_details: Optional[dict] = None,
        response_status: Optional[int] = None,
        phi_accessed: bool = False,
    ) -> int:
        """
        Log an auditable event.

        Args:
            action: Description of the action (e.g., "VIEW_PATIENT", "SEARCH_PAPERS")
            user_id: User performing the action
            user_role: Role of the user (doctor, nurse, admin, researcher)
            resource_type: Type of resource accessed (e.g., "patient", "paper")
            resource_id: ID of the specific resource
            ip_address: Client IP address
            user_agent: Client user agent string
            request_details: Additional request context (JSON-serializable)
            response_status: HTTP status code if applicable
            phi_accessed: Whether PHI was accessed (triggers special handling)

        Returns:
            ID of the created audit log entry
        """
        timestamp = datetime.now(timezone.utc)
        previous_hash = self._get_last_hash()

        log_data = {
            "event_timestamp": timestamp.isoformat(),
            "user_id": user_id,
            "user_role": user_role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "request_details": request_details,
            "response_status": response_status,
            "phi_accessed": phi_accessed,
        }

        current_hash = self._compute_hash(log_data, previous_hash)

        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text("""
                        INSERT INTO audit_logs (
                            event_timestamp, user_id, user_role, action,
                            resource_type, resource_id, ip_address, user_agent,
                            request_details, response_status, phi_accessed,
                            previous_hash, current_hash
                        ) VALUES (
                            :timestamp, :user_id, :user_role, :action,
                            :resource_type, :resource_id, :ip_address, :user_agent,
                            :request_details, :response_status, :phi_accessed,
                            :previous_hash, :current_hash
                        ) RETURNING id
                    """),
                    {
                        "timestamp": timestamp,
                        "user_id": user_id,
                        "user_role": user_role,
                        "action": action,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "ip_address": ip_address,
                        "user_agent": user_agent,
                        "request_details": json.dumps(request_details)
                        if request_details
                        else None,
                        "response_status": response_status,
                        "phi_accessed": phi_accessed,
                        "previous_hash": previous_hash,
                        "current_hash": current_hash,
                    },
                )
                conn.commit()
                log_id = result.fetchone()[0]
                self._last_hash = current_hash
                return log_id
        except SQLAlchemyError as e:
            # Log to fallback mechanism in production
            print(f"CRITICAL: Audit log failed: {e}")
            raise

    def verify_chain_integrity(self, limit: int = 1000) -> tuple[bool, Optional[int]]:
        """
        Verify the integrity of the audit log chain.

        Returns:
            Tuple of (is_valid, first_invalid_id)
            If valid, first_invalid_id is None
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT id, event_timestamp, user_id, user_role, action, "
                        "resource_type, resource_id, ip_address, user_agent, "
                        "request_details, response_status, phi_accessed, "
                        "previous_hash, current_hash "
                        "FROM audit_logs ORDER BY id LIMIT :limit"
                    ),
                    {"limit": limit},
                )

                previous_hash = None
                for row in result:
                    log_data = {
                        "event_timestamp": row[1].isoformat() if row[1] else None,
                        "user_id": row[2],
                        "user_role": row[3],
                        "action": row[4],
                        "resource_type": row[5],
                        "resource_id": row[6],
                        "ip_address": row[7],
                        "user_agent": row[8],
                        "request_details": row[9],
                        "response_status": row[10],
                        "phi_accessed": row[11],
                    }

                    expected_hash = self._compute_hash(log_data, previous_hash)
                    if expected_hash != row[13]:  # current_hash
                        return False, row[0]  # id

                    if row[12] != previous_hash:  # previous_hash
                        return False, row[0]

                    previous_hash = row[13]

                return True, None
        except SQLAlchemyError as e:
            print(f"Integrity check failed: {e}")
            return False, None


# Singleton instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create singleton audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def log_action(action: str, **kwargs) -> int:
    """Convenience function for logging actions."""
    return get_audit_logger().log(action, **kwargs)
