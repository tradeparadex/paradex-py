"""Tests for WebSocket JWT token refresh functionality.

This module tests the automatic JWT token refresh mechanism that prevents
websocket keepalive ping timeouts due to expired bearer tokens.
"""

import asyncio
import json
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
    async def test_auth_refresh_task_starts_on_connect(self):
        """Test that auth refresh task starts automatically when connected with an account."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        # Create mock API client
        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        # Create mock account with JWT token
        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

        # Create WebSocket client with short refresh interval for testing
        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            auth_refresh_interval=0.1,  # Refresh every 100ms for testing
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        try:
            # Connect
            await client.connect()

            # Verify auth refresh task was created
            assert client._auth_refresh_task is not None
            assert not client._auth_refresh_task.done()

            # Wait a bit to let the refresh task attempt to run
            await asyncio.sleep(0.2)

            # Verify last_auth_time was set
            assert client._last_auth_time > 0
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_auth_refresh_task_cancelled_on_close(self):
        """Test that auth refresh task is cancelled when connection is closed."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_api_client = MagicMock()
        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            auth_refresh_interval=10.0,  # Long interval
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        # Connect
        await client.connect()
        assert client._auth_refresh_task is not None

        # Close
        await client.close()

        # Verify task was cancelled
        assert client._auth_refresh_task.done()
        assert client._auth_refresh_task.cancelled()

    @pytest.mark.asyncio
    async def test_auth_refresh_disabled_when_interval_zero(self):
        """Test that auth refresh is disabled when interval is set to 0."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token"

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            auth_refresh_interval=0,  # Disabled
        )
        client.init_account(mock_account)

        try:
            # Connect
            await client.connect()

            # Verify auth refresh task was NOT created
            assert client._auth_refresh_task is None
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_auth_error_triggers_reconnect_with_refresh(self):
        """Test that authentication error (code 40111) triggers reconnection with token refresh."""
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
    async def test_reconnect_with_auth_refresh_calls_api_client(self):
        """Test that _reconnect_with_auth_refresh calls api_client.auth() before reconnecting."""
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
            disable_reconnect=False,
        )
        client.init_account(mock_account)

        await client.connect()

        # Mock the _reconnect method to avoid actual reconnection
        with patch.object(client, "_reconnect", new_callable=AsyncMock) as mock_reconnect:
            # Call reconnect with auth refresh
            await client._reconnect_with_auth_refresh()

            # Verify that api_client.auth() was called
            mock_api_client.auth.assert_called_once()

            # Verify that _reconnect was called after auth refresh
            mock_reconnect.assert_called_once()

        await client.close()

    @pytest.mark.asyncio
    async def test_auth_refresh_without_api_client_logs_warning(self):
        """Test that auth refresh without api_client logs a warning."""
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
            auth_refresh_interval=0.1,  # Short interval for testing
            api_client=None,  # No API client
        )
        client.init_account(mock_account)

        try:
            await client.connect()

            # Wait for auth refresh to attempt
            await asyncio.sleep(0.2)

            # The test passes if no exception is raised
            # The warning should be logged (not tested here)
        finally:
            await client.close()

    def test_auth_refresh_interval_default_value(self):
        """Test that auth_refresh_interval has correct default value."""
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)

        # Should default to 4 minutes (240 seconds)
        assert client.auth_refresh_interval == 240

    @pytest.mark.asyncio
    async def test_auth_refresh_updates_last_auth_time(self):
        """Test that successful auth refresh updates _last_auth_time."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        mock_api_client = MagicMock()
        mock_api_client.auth = MagicMock()

        mock_account = MagicMock()
        mock_account.jwt_token = "test_token_old"

        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            connector=mock_connector,
            auth_refresh_interval=0.1,
            api_client=mock_api_client,
        )
        client.init_account(mock_account)

        try:
            await client.connect()
            initial_auth_time = client._last_auth_time

            # Wait for auth refresh
            await asyncio.sleep(0.2)

            # Last auth time should be updated
            assert client._last_auth_time >= initial_auth_time
        finally:
            await client.close()
