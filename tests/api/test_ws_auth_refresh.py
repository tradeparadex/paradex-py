"""Tests for WebSocket JWT token refresh functionality.

This module tests the automatic JWT token refresh mechanism that prevents
websocket keepalive ping timeouts due to expired bearer tokens.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets import State

from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import TESTNET


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

        # Create mock API client with recent auth timestamp
        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()
        mock_api_client.auth_timestamp = time.time()  # Fresh token

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

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
        """Test that _is_token_expired returns True for old tokens."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        # Create mock API client with old auth timestamp (24 hours ago)
        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()
        mock_api_client.auth_timestamp = time.time() - (24 * 3600)  # 24 hours old

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

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
        """Test that token expiry uses 23-hour threshold for safety margin."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        try:
            await client.connect()

            # Test 22 hours old - should NOT be expired
            mock_api_client.auth_timestamp = time.time() - (22 * 3600)
            assert not client._is_token_expired()

            # Test 23 hours old - should be expired (at threshold)
            mock_api_client.auth_timestamp = time.time() - (23 * 3600)
            assert client._is_token_expired()

            # Test 24 hours old - should be expired
            mock_api_client.auth_timestamp = time.time() - (24 * 3600)
            assert client._is_token_expired()
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_reconnect_refreshes_expired_token(self):
        """Test that reconnect refreshes token if it has expired."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        # Create mock API client with expired token
        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()
        mock_api_client.auth_timestamp = time.time() - (24 * 3600)  # Expired

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

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
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        # Create mock API client with fresh token
        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()
        mock_api_client.auth_timestamp = time.time()  # Fresh token

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

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
        mock_account.jwt_token = "test_token"

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
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        # Create mock API client with fresh token
        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()
        mock_api_client.auth_timestamp = time.time()  # Fresh token

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

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
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

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
        mock_account.jwt_token = "test_token"

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
    async def test_is_token_expired_with_zero_timestamp(self):
        """Test that _is_token_expired returns False when auth_timestamp is 0."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()
        mock_api_client.auth_timestamp = 0  # No token fetched yet

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        try:
            await client.connect()

            # Should return False (no token has been fetched)
            assert not client._is_token_expired()
        finally:
            await client.close()
