"""Mirth Connect Interface Engine Connector"""

import base64
from typing import Optional

import httpx

from src.config import get_settings
from src.security.audit_logger import log_action


class MirthConnector:
    """
    Connector for Mirth Connect integration engine.

    Provides:
    - Channel status monitoring
    - Message sending via HTTP
    - Channel deployment management
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = True,
    ):
        """
        Initialize Mirth Connect connector.

        Args:
            host: Mirth Connect server host
            port: Mirth Connect API port (default: 8443)
            username: Admin username
            password: Admin password
            use_ssl: Use HTTPS (default: True)
        """
        settings = get_settings()

        self._host = host or settings.mirth_host
        self._port = port or settings.mirth_port
        self._username = username or settings.mirth_username
        self._password = password or settings.mirth_password

        protocol = "https" if use_ssl else "http"
        self._base_url = f"{protocol}://{self._host}:{self._port}/api"

        self._session_token: Optional[str] = None

    def _get_auth_header(self) -> dict:
        """Get authentication header."""
        if self._session_token:
            return {"Cookie": f"JSESSIONID={self._session_token}"}
        
        # Basic auth fallback
        credentials = base64.b64encode(
            f"{self._username}:{self._password}".encode()
        ).decode()
        return {"Authorization": f"Basic {credentials}"}

    def login(self) -> bool:
        """
        Authenticate with Mirth Connect.

        Returns:
            True if authentication successful
        """
        try:
            with httpx.Client(verify=False) as client:  # Mirth often uses self-signed certs
                response = client.post(
                    f"{self._base_url}/users/_login",
                    data={
                        "username": self._username,
                        "password": self._password,
                    },
                )
                
                if response.status_code == 200:
                    # Extract session token from cookies
                    cookies = response.cookies
                    self._session_token = cookies.get("JSESSIONID")
                    return True
                    
            return False
        except Exception as e:
            print(f"Mirth login error: {e}")
            return False

    def get_server_status(self) -> dict:
        """
        Get Mirth Connect server status.

        Returns:
            Server status information
        """
        try:
            with httpx.Client(verify=False) as client:
                response = client.get(
                    f"{self._base_url}/server/status",
                    headers=self._get_auth_header(),
                )
                
                if response.status_code == 200:
                    return {"status": "connected", "data": response.json()}
                else:
                    return {"status": "error", "code": response.status_code}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_channels(self) -> list[dict]:
        """
        List all channels.

        Returns:
            List of channel information
        """
        log_action(
            action="MIRTH_LIST_CHANNELS",
            resource_type="MirthChannel",
        )

        try:
            with httpx.Client(verify=False) as client:
                response = client.get(
                    f"{self._base_url}/channels",
                    headers={
                        **self._get_auth_header(),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                
                data = response.json()
                channels = data.get("list", {}).get("channel", [])
                
                if isinstance(channels, dict):
                    channels = [channels]
                    
                return [
                    {
                        "id": ch.get("id"),
                        "name": ch.get("name"),
                        "enabled": ch.get("enabled"),
                        "description": ch.get("description"),
                    }
                    for ch in channels
                ]
        except Exception as e:
            print(f"Error listing channels: {e}")
            return []

    def get_channel_status(self, channel_id: str) -> dict:
        """
        Get status of a specific channel.

        Args:
            channel_id: Channel ID

        Returns:
            Channel status
        """
        try:
            with httpx.Client(verify=False) as client:
                response = client.get(
                    f"{self._base_url}/channels/{channel_id}/status",
                    headers={
                        **self._get_auth_header(),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}

    def send_message(
        self,
        channel_id: str,
        message: str,
        user_id: Optional[str] = None,
    ) -> dict:
        """
        Send a message to a channel.

        Args:
            channel_id: Target channel ID
            message: Message content (typically HL7)
            user_id: User ID for audit logging

        Returns:
            Send result
        """
        log_action(
            action="MIRTH_SEND_MESSAGE",
            user_id=user_id,
            resource_type="MirthMessage",
            resource_id=channel_id,
            phi_accessed=True,  # HL7 messages typically contain PHI
        )

        try:
            with httpx.Client(verify=False) as client:
                response = client.post(
                    f"{self._base_url}/channels/{channel_id}/messages",
                    headers={
                        **self._get_auth_header(),
                        "Content-Type": "text/plain",
                    },
                    content=message,
                )
                response.raise_for_status()
                return {"status": "sent", "response": response.text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def start_channel(self, channel_id: str) -> bool:
        """
        Start a channel.

        Args:
            channel_id: Channel ID to start

        Returns:
            True if successful
        """
        log_action(
            action="MIRTH_START_CHANNEL",
            resource_type="MirthChannel",
            resource_id=channel_id,
        )

        try:
            with httpx.Client(verify=False) as client:
                response = client.post(
                    f"{self._base_url}/channels/{channel_id}/_start",
                    headers=self._get_auth_header(),
                )
                return response.status_code == 204
        except Exception:
            return False

    def stop_channel(self, channel_id: str) -> bool:
        """
        Stop a channel.

        Args:
            channel_id: Channel ID to stop

        Returns:
            True if successful
        """
        log_action(
            action="MIRTH_STOP_CHANNEL",
            resource_type="MirthChannel",
            resource_id=channel_id,
        )

        try:
            with httpx.Client(verify=False) as client:
                response = client.post(
                    f"{self._base_url}/channels/{channel_id}/_stop",
                    headers=self._get_auth_header(),
                )
                return response.status_code == 204
        except Exception:
            return False

    def get_channel_statistics(self, channel_id: str) -> dict:
        """
        Get channel message statistics.

        Args:
            channel_id: Channel ID

        Returns:
            Statistics (received, sent, errored counts)
        """
        try:
            with httpx.Client(verify=False) as client:
                response = client.get(
                    f"{self._base_url}/channels/{channel_id}/statistics",
                    headers={
                        **self._get_auth_header(),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}
