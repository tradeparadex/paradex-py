"""Tests for WebSocket JWT token refresh functionality.

This module tests the automatic JWT token refresh mechanism that prevents
websocket keepalive ping timeouts due to expired bearer tokens.
"""

import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets import State

from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import TESTNET


def create_jwt_token(exp_timestamp: float) -> str:
    """Create a mock JWT token with specified expiration timestamp.

    Args:
        exp_timestamp: Unix timestamp when token expires

    Returns:
        JWT token string (not cryptographically valid, but decodable)
    """
    # Create header
    header = {"alg": "HS256", "typ": "JWT"}
    header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")

    # Create payload with expiration
    payload = {"exp": int(exp_timestamp), "sub": "test_user"}
    payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    # Create dummy signature (not validated in our code)
    signature = "dummy_signature"

    return f"{header_encoded}.{payload_encoded}.{signature}"


class MockWebSocketConnection:
    """Mock WebSocket connection for testing."""

    def __init__(self):
        self.state = State.OPEN
        self.sent_messages = []

    async def send(self, data: str):
        self.sent_messages.append(data)

    async def recv(self) -> str:
        # Block forever to simulate waiting for messages
        await asyncio.sleep(100)
        return "{}"

    async def close(self):
        self.state = State.CLOSED


class TestWebSocketAuthRefresh:
    """Test WebSocket JWT token refresh functionality."""

    @pytest.mark.asyncio
    async def test_token_not_expired_check(self):
        """Test that _is_token_expired returns False for fresh tokens."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        # Create token that expires in 1 hour
        exp_time = time.time() + 3600
        fresh_token = create_jwt_token(exp_time)

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = fresh_token

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        try:
            await client.connect()

            # Token should not be expired
            assert not client._is_token_expired()
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_token_expired_check(self):
        """Test that _is_token_expired returns True for expired tokens."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        # Create token that expired 1 hour ago
        exp_time = time.time() - 3600
        expired_token = create_jwt_token(exp_time)

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = expired_token

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        try:
            await client.connect()

            # Token should be expired
            assert client._is_token_expired()
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_token_expiry_threshold(self):
        """Test that token expiry uses 60-second safety margin."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
        )

        try:
            # Test token expiring in 120 seconds - should NOT be expired
            exp_time = time.time() + 120
            token_120s = create_jwt_token(exp_time)
            mock_account = MagicMock()
            mock_account.jwt_token = token_120s
            client.init_account(mock_account)
            await client.connect()
            assert not client._is_token_expired()

            # Test token expiring in 30 seconds - should be expired (within 60s safety margin)
            exp_time = time.time() + 30
            token_30s = create_jwt_token(exp_time)
            mock_account.jwt_token = token_30s
            assert client._is_token_expired()

            # Test token expiring in exactly 60 seconds - should be expired (at threshold)
            exp_time = time.time() + 60
            token_60s = create_jwt_token(exp_time)
            mock_account.jwt_token = token_60s
            assert client._is_token_expired()
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_reconnect_refreshes_expired_token(self):
        """Test that reconnect refreshes token if it has expired."""
        MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        # Create expired token
        exp_time = time.time() - 3600
        expired_token = create_jwt_token(exp_time)

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = expired_token

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
            disable_reconnect=False,
        )
        client.init_account(mock_account)

        await client.connect()

        # Call reconnect
        await client._reconnect()

        # Verify that api_client.auth() was called to refresh token
        mock_api_client.auth.assert_called()

        await client.close()

    @pytest.mark.asyncio
    async def test_reconnect_skips_refresh_for_fresh_token(self):
        """Test that reconnect skips token refresh if token is still fresh."""
        MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        # Create fresh token that expires in 1 hour
        exp_time = time.time() + 3600
        fresh_token = create_jwt_token(exp_time)

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = fresh_token

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
            disable_reconnect=False,
        )
        client.init_account(mock_account)

        await client.connect()

        # Reset call count
        mock_api_client.auth.reset_mock()

        # Call reconnect
        await client._reconnect()

        # Verify that api_client.auth() was NOT called (token still fresh)
        mock_api_client.auth.assert_not_called()

        await client.close()

    @pytest.mark.asyncio
    async def test_auth_error_triggers_reconnect_with_refresh(self):
        """Test that authentication error (code 40111) triggers reconnection with token refresh."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()
        mock_api_client.auth_timestamp = time.time()

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"  # noqa: S105

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
            disable_reconnect=False,
        )
        client.init_account(mock_account)

        await client.connect()

        # Mock the reconnect with auth refresh method
        with patch.object(client, "_reconnect_with_auth_refresh", new_callable=AsyncMock) as mock_reconnect:
            # Simulate an auth error message
            error_message = {
                "id": 123,
                "error": {"code": 40111, "message": "invalid bearer token"},
            }

            # Process the error message
            client._check_subscribed_channel(error_message)

            # Wait a bit for the async task to be created
            await asyncio.sleep(0.1)

            # Verify that reconnect with auth refresh was triggered
            mock_reconnect.assert_called_once()

        await client.close()

    @pytest.mark.asyncio
    async def test_reconnect_with_auth_refresh_forces_refresh(self):
        """Test that _reconnect_with_auth_refresh always forces token refresh."""
        MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        # Create fresh token that expires in 1 hour
        exp_time = time.time() + 3600
        fresh_token = create_jwt_token(exp_time)

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = fresh_token

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
            disable_reconnect=False,
        )
        client.init_account(mock_account)

        await client.connect()

        # Reset call count
        mock_api_client.auth.reset_mock()

        # Call reconnect with auth refresh (this should force refresh even if token is fresh)
        await client._reconnect_with_auth_refresh()

        # Verify that api_client.auth() was called to force refresh
        mock_api_client.auth.assert_called()

        await client.close()

    @pytest.mark.asyncio
    async def test_reconnect_without_api_client(self):
        """Test that reconnect works without api_client (no token refresh)."""
        MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"  # noqa: S105

        # Create client WITHOUT api_client
        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=None,
            disable_reconnect=False,
        )
        client.init_account(mock_account)

        await client.connect()

        # Call reconnect - should not raise exception
        await client._reconnect()

        # Test passes if no exception is raised
        await client.close()

    @pytest.mark.asyncio
    async def test_is_token_expired_without_api_client(self):
        """Test that _is_token_expired returns False when no api_client is available."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"  # noqa: S105

        # Create client WITHOUT api_client
        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=None,
        )
        client.init_account(mock_account)

        try:
            await client.connect()

            # Should return False (can't determine expiration)
            assert not client._is_token_expired()
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_is_token_expired_with_invalid_token(self):
        """Test that _is_token_expired returns False for invalid/malformed tokens."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = "invalid_token_format"  # noqa: S105

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        try:
            await client.connect()

            # Should return False (can't decode token)
            assert not client._is_token_expired()
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_decode_jwt_payload(self):
        """Test JWT token payload decoding."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
        )

        # Test valid token
        exp_time = time.time() + 3600
        valid_token = create_jwt_token(exp_time)
        payload = client._decode_jwt_payload(valid_token)
        assert payload is not None
        assert "exp" in payload
        assert payload["exp"] == int(exp_time)

        # Test invalid token
        invalid_payload = client._decode_jwt_payload("not.a.valid.token")
        assert invalid_payload is None

        # Test token with only 2 parts
        invalid_payload = client._decode_jwt_payload("header.payload")
        assert invalid_payload is None

        await client.close()

    @pytest.mark.asyncio
    async def test_token_without_exp_claim(self):
        """Test that tokens without exp claim are treated as not expired."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        # Create token without exp claim
        header = {"alg": "HS256", "typ": "JWT"}
        header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload = {"sub": "test_user"}  # No exp claim
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        token_no_exp = f"{header_encoded}.{payload_encoded}.dummy_signature"

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = token_no_exp

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        try:
            await client.connect()

            # Should return False (can't determine expiration)
            assert not client._is_token_expired()
        finally:
            await client.close()
