"""Tests for WebSocket compression support in ParadexWebsocketClient."""

from unittest.mock import AsyncMock, patch

import pytest
from websockets import State

from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import TESTNET
from paradex_py.paradex import Paradex

MOCK_L1_PRIVATE_KEY = "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
MOCK_L1_ADDRESS = "0xabcdef0123456789abcdef0123456789abcdef01"


class TestWebSocketCompression:
    """Test suite for WebSocket compression configuration."""

    def test_compression_enabled_by_default(self):
        """Test that compression is enabled by default."""
        ws_client = ParadexWebsocketClient(env=TESTNET)

        # Should have enable_compression=True by default
        assert ws_client.enable_compression is True

    def test_compression_explicitly_enabled(self):
        """Test that compression can be explicitly enabled."""
        ws_client = ParadexWebsocketClient(env=TESTNET, enable_compression=True)

        # Should have enable_compression=True
        assert ws_client.enable_compression is True

    def test_compression_disabled(self):
        """Test that compression can be disabled."""
        ws_client = ParadexWebsocketClient(env=TESTNET, enable_compression=False)

        # Should have enable_compression=False
        assert ws_client.enable_compression is False

    @pytest.mark.asyncio
    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_compression_enabled_connect_kwargs(self, mock_connect: AsyncMock):
        """Test that compression enabled does not add compression=None to kwargs."""
        mock_ws_connection = AsyncMock()
        mock_ws_connection.state = State.OPEN
        mock_connect.return_value = mock_ws_connection

        ws_client = ParadexWebsocketClient(env=TESTNET, enable_compression=True)
        await ws_client.connect()

        # Verify compression is not in kwargs (letting websockets use its default)
        call_args = mock_connect.call_args
        assert "compression" not in call_args.kwargs

    @pytest.mark.asyncio
    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_compression_disabled_connect_kwargs(self, mock_connect: AsyncMock):
        """Test that compression disabled adds compression=None to kwargs."""
        mock_ws_connection = AsyncMock()
        mock_ws_connection.state = State.OPEN
        mock_connect.return_value = mock_ws_connection

        ws_client = ParadexWebsocketClient(env=TESTNET, enable_compression=False)
        await ws_client.connect()

        # Verify compression=None is passed to disable compression
        call_args = mock_connect.call_args
        assert call_args.kwargs["compression"] is None

    @pytest.mark.asyncio
    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_compression_with_custom_connector(self, mock_connect: AsyncMock):
        """Test that custom connector is unaffected by compression setting."""
        mock_ws_connection = AsyncMock()
        mock_ws_connection.state = State.OPEN

        # Custom connector function
        async def custom_connector(url: str, headers: dict) -> AsyncMock:
            return mock_ws_connection

        ws_client = ParadexWebsocketClient(env=TESTNET, connector=custom_connector, enable_compression=False)
        await ws_client.connect()

        # Custom connector should be used, not websockets.connect
        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_compression_persists_after_reconnect(self, mock_connect: AsyncMock):
        """Test that compression setting persists after reconnection."""
        mock_ws_connection = AsyncMock()
        mock_ws_connection.state = State.OPEN
        mock_connect.return_value = mock_ws_connection

        ws_client = ParadexWebsocketClient(env=TESTNET, enable_compression=False)

        # First connection
        await ws_client.connect()
        first_call_args = mock_connect.call_args
        assert first_call_args.kwargs["compression"] is None

        # Simulate reconnection
        mock_connect.reset_mock()
        mock_ws_connection.state = State.OPEN
        mock_connect.return_value = mock_ws_connection

        with patch.object(ws_client, "_send_auth_id", new_callable=AsyncMock):
            await ws_client._reconnect()

        # Verify compression setting persists after reconnect
        if mock_connect.called:
            second_call_args = mock_connect.call_args
            assert second_call_args.kwargs["compression"] is None

    def test_compression_disabled_via_paradex_constructor(self):
        """Test that compression can be disabled via Paradex constructor."""
        paradex = Paradex(env=TESTNET, enable_ws_compression=False)

        # Should have created a WebSocket client with compression disabled
        assert paradex.ws_client.enable_compression is False

    def test_compression_enabled_via_paradex_constructor(self):
        """Test that compression is enabled via Paradex constructor."""
        paradex = Paradex(env=TESTNET, enable_ws_compression=True)

        # Should have created a WebSocket client with compression enabled
        assert paradex.ws_client.enable_compression is True

    def test_compression_default_via_paradex_constructor(self):
        """Test that compression is enabled by default via Paradex constructor."""
        paradex = Paradex(env=TESTNET)

        # Should use default compression behavior (enabled)
        assert paradex.ws_client.enable_compression is True

    def test_compression_with_other_ws_options(self):
        """Test that compression works alongside other WebSocket options."""
        ws_client = ParadexWebsocketClient(
            env=TESTNET, enable_compression=False, ws_timeout=30, ping_interval=20.0, disable_reconnect=True
        )

        # Should have all options set correctly
        assert ws_client.enable_compression is False
        assert ws_client.ws_timeout == 30
        assert ws_client.ping_interval == 20.0
        assert ws_client.disable_reconnect is True

    @pytest.mark.asyncio
    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_compression_with_ping_interval(self, mock_connect: AsyncMock):
        """Test that compression works alongside ping_interval configuration."""
        mock_ws_connection = AsyncMock()
        mock_ws_connection.state = State.OPEN
        mock_connect.return_value = mock_ws_connection

        ws_client = ParadexWebsocketClient(env=TESTNET, enable_compression=False, ping_interval=15.0)
        await ws_client.connect()

        # Verify both compression and ping_interval are passed
        call_args = mock_connect.call_args
        assert call_args.kwargs["compression"] is None
        assert call_args.kwargs["ping_interval"] == 15
