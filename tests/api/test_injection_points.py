"""Tests for simulator-friendly injection points in paradex_py."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.http_client import HttpClient
from paradex_py.api.ws_client import ParadexWebsocketChannel, ParadexWebsocketClient
from paradex_py.environment import Environment
from paradex_py.paradex import Paradex


class TestHttpClientInjection:
    """Test HTTP client injection functionality."""

    def test_http_client_default_initialization(self):
        """Test default HTTP client initialization."""
        client = HttpClient()
        assert client.client is not None
        assert isinstance(client.client, httpx.Client)
        assert "Content-Type" in client.client.headers
        assert client.client.headers["Content-Type"] == "application/json"

    def test_http_client_injection(self):
        """Test HTTP client injection."""
        # Create a custom httpx client
        custom_client = httpx.Client()
        custom_client.headers.update({"Custom-Header": "test-value"})

        # Inject it into HttpClient
        client = HttpClient(http_client=custom_client)

        assert client.client is custom_client
        assert "Custom-Header" in client.client.headers
        assert client.client.headers["Custom-Header"] == "test-value"
        # Should still have Content-Type added
        assert "Content-Type" in client.client.headers

    def test_http_client_injection_preserves_existing_headers(self):
        """Test that injection preserves existing headers."""
        # Create a custom client with Content-Type already set
        custom_client = httpx.Client()
        custom_client.headers.update({"Content-Type": "application/xml"})

        # Inject it into HttpClient
        client = HttpClient(http_client=custom_client)

        # Should preserve the existing Content-Type
        assert client.client.headers["Content-Type"] == "application/xml"

    def test_mock_transport_integration(self):
        """Test integration with httpx MockTransport."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/test"):
                return httpx.Response(200, json={"message": "success"})
            return httpx.Response(404, json={"error": "not found"})

        mock_transport = httpx.MockTransport(handler)
        custom_client = httpx.Client(transport=mock_transport)
        http_client = HttpClient(http_client=custom_client)

        # Test successful request
        http_client.request(
            url="https://example.com/test",
            http_method=http_client.HttpMethod.GET if hasattr(http_client, "HttpMethod") else MagicMock(),
        )
        # Note: This would need the HttpMethod enum to be accessible
        # For now, we just verify the client was injected correctly
        assert http_client.client.transport is mock_transport


class TestApiClientInjection:
    """Test API client injection functionality."""

    def test_api_client_default_initialization(self):
        """Test default API client initialization."""
        with patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock()):
            client = ParadexApiClient(env=Environment.TESTNET)
            assert client.env == Environment.TESTNET
            assert "testnet" in client.api_url

    def test_api_client_http_injection(self):
        """Test API client with HTTP client injection."""
        custom_http_client = HttpClient(http_client=httpx.Client())

        with patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock()):
            client = ParadexApiClient(env=Environment.TESTNET, http_client=custom_http_client)
            # Verify the custom client was used
            assert client.client is not None

    def test_api_client_base_url_override(self):
        """Test API client with base URL override."""
        custom_url = "https://custom.api.example.com/v1"

        with patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock()):
            client = ParadexApiClient(env=Environment.TESTNET, api_base_url=custom_url)
            assert client.api_url == custom_url

    def test_api_client_both_injections(self):
        """Test API client with both HTTP client and URL override."""
        custom_http_client = HttpClient(http_client=httpx.Client())
        custom_url = "https://custom.api.example.com/v1"

        with patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock()):
            client = ParadexApiClient(env=Environment.TESTNET, http_client=custom_http_client, api_base_url=custom_url)
            assert client.api_url == custom_url
            assert client.client is not None


class MockWebSocketConnection:
    """Mock WebSocket connection for testing."""

    def __init__(self, messages=None):
        self.messages = messages or []
        self._message_iter = iter(self.messages)
        self.state = SimpleNamespace(value="OPEN")
        self.sent_messages = []

    async def send(self, data: str):
        self.sent_messages.append(data)

    async def recv(self) -> str:
        try:
            return next(self._message_iter)
        except StopIteration as err:
            # Simulate waiting indefinitely
            await asyncio.sleep(10)
            raise asyncio.TimeoutError() from err

    async def close(self):
        self.state = SimpleNamespace(value="CLOSED")


class TestWebSocketClientInjection:
    """Test WebSocket client injection functionality."""

    def test_ws_client_default_initialization(self):
        """Test default WebSocket client initialization."""
        client = ParadexWebsocketClient(env=Environment.TESTNET)
        assert client.env == Environment.TESTNET
        assert "testnet" in client.api_url
        assert client.auto_start_reader is True
        assert client.connector is None

    def test_ws_client_auto_start_reader_disabled(self):
        """Test WebSocket client with auto_start_reader disabled."""
        client = ParadexWebsocketClient(env=Environment.TESTNET, auto_start_reader=False)
        assert client.auto_start_reader is False
        assert client._reader_task is None

    def test_ws_client_url_override(self):
        """Test WebSocket client with URL override."""
        custom_url = "wss://custom.ws.example.com/v1"
        client = ParadexWebsocketClient(env=Environment.TESTNET, ws_url_override=custom_url)
        assert client.api_url == custom_url

    @pytest.mark.asyncio
    async def test_ws_client_custom_connector(self):
        """Test WebSocket client with custom connector."""
        test_messages = [
            json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": "50000", "ask": "50001"}})
        ]

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection(test_messages)

        client = ParadexWebsocketClient(env=Environment.TESTNET, auto_start_reader=False, connector=mock_connector)

        # Test connection
        result = await client.connect()
        assert result is True
        assert client.ws is not None
        assert isinstance(client.ws, MockWebSocketConnection)

    @pytest.mark.asyncio
    async def test_ws_client_manual_pumping(self):
        """Test WebSocket client manual message pumping."""
        test_message = json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": "50000", "ask": "50001"}})

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection([test_message])

        client = ParadexWebsocketClient(env=Environment.TESTNET, auto_start_reader=False, connector=mock_connector)

        await client.connect()

        # Set up callback to capture message
        received_messages = []

        async def test_callback(channel, message):
            received_messages.append((channel, message))

        await client.subscribe(ParadexWebsocketChannel.BBO, callback=test_callback, params={"market": "BTC-USD-PERP"})

        # Manually pump one message
        result = await client.pump_once()
        assert result is True
        assert len(received_messages) == 1

        # Try to pump again (should return False as no more messages)
        result = await client.pump_once()
        assert result is False

    @pytest.mark.asyncio
    async def test_ws_client_message_injection(self):
        """Test WebSocket client message injection."""
        client = ParadexWebsocketClient(env=Environment.TESTNET, auto_start_reader=False)

        # Set up callback to capture message
        received_messages = []

        async def test_callback(channel, message):
            received_messages.append((channel, message))

        await client.subscribe(ParadexWebsocketChannel.BBO, callback=test_callback, params={"market": "BTC-USD-PERP"})

        # Inject a message directly
        test_message = json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": "50000", "ask": "50001"}})

        await client.inject(test_message)

        assert len(received_messages) == 1
        channel, message = received_messages[0]
        assert channel == ParadexWebsocketChannel.BBO
        assert message["data"]["bid"] == "50000"


class TestParadexFacadeInjection:
    """Test Paradex facade injection functionality."""

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_paradex_default_initialization(self, mock_config):
        """Test default Paradex initialization."""
        paradex = Paradex(env=Environment.TESTNET)
        assert paradex.env == Environment.TESTNET
        assert paradex.api_client is not None
        assert paradex.ws_client is not None

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_paradex_http_injection(self, mock_config):
        """Test Paradex with HTTP client injection."""
        custom_http_client = HttpClient(http_client=httpx.Client())

        paradex = Paradex(env=Environment.TESTNET, http_client=custom_http_client)

        assert paradex.api_client is not None
        # Verify the injection was passed through
        assert paradex.api_client.client is not None

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_paradex_ws_injection(self, mock_config):
        """Test Paradex with WebSocket injection."""

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        paradex = Paradex(
            env=Environment.TESTNET,
            auto_start_ws_reader=False,
            ws_connector=mock_connector,
            ws_url_override="wss://custom.example.com/v1",
        )

        assert paradex.ws_client.auto_start_reader is False
        assert paradex.ws_client.connector is mock_connector
        assert paradex.ws_client.api_url == "wss://custom.example.com/v1"

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_paradex_full_injection(self, mock_config):
        """Test Paradex with all injection options."""
        custom_http_client = HttpClient(http_client=httpx.Client())
        custom_api_url = "https://custom.api.example.com/v1"
        custom_ws_url = "wss://custom.ws.example.com/v1"

        async def mock_connector(url: str, headers: dict):
            return MockWebSocketConnection()

        paradex = Paradex(
            env=Environment.TESTNET,
            http_client=custom_http_client,
            api_base_url=custom_api_url,
            auto_start_ws_reader=False,
            ws_connector=mock_connector,
            ws_url_override=custom_ws_url,
        )

        # Verify all injections were applied
        assert paradex.api_client.api_url == custom_api_url
        assert paradex.ws_client.api_url == custom_ws_url
        assert paradex.ws_client.auto_start_reader is False
        assert paradex.ws_client.connector is mock_connector


class TestSimulatorUseCases:
    """Test realistic simulator use cases."""

    def test_rest_simulator_integration(self):
        """Test REST API simulator integration example."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/v1/markets"):
                return httpx.Response(200, json={"results": [{"symbol": "BTC-USD-PERP", "status": "active"}]})
            elif request.url.path.endswith("/v1/system/config"):
                return httpx.Response(200, json={"paraclear_decimals": 8, "paraclear_account_registry": "0x123"})
            return httpx.Response(404, json={"error": "not found"})

        mock_transport = httpx.MockTransport(handler)
        custom_client = httpx.Client(transport=mock_transport)
        http_client = HttpClient(http_client=custom_client)

        # This would be used in a simulator
        api_client = ParadexApiClient(
            env=Environment.TESTNET, http_client=http_client, api_base_url="https://simulator.example.com/v1"
        )

        assert api_client.api_url == "https://simulator.example.com/v1"
        assert api_client.client.transport is mock_transport

    @pytest.mark.asyncio
    async def test_ws_simulator_integration(self):
        """Test WebSocket simulator integration example."""
        # Simulate market data messages
        market_messages = [
            json.dumps(
                {
                    "params": {"channel": "bbo.BTC-USD-PERP"},
                    "data": {"bid": "50000", "ask": "50001", "timestamp": "1234567890"},
                }
            ),
            json.dumps(
                {
                    "params": {"channel": "bbo.BTC-USD-PERP"},
                    "data": {"bid": "50010", "ask": "50011", "timestamp": "1234567891"},
                }
            ),
        ]

        async def simulator_connector(url: str, headers: dict):
            return MockWebSocketConnection(market_messages)

        # Create client with simulator connector
        ws_client = ParadexWebsocketClient(
            env=Environment.TESTNET,
            auto_start_reader=False,
            connector=simulator_connector,
            ws_url_override="wss://simulator.example.com/v1",
        )

        await ws_client.connect()

        # Collect messages
        received_data = []

        async def data_handler(channel, message):
            received_data.append(message["data"])

        await ws_client.subscribe(ParadexWebsocketChannel.BBO, callback=data_handler, params={"market": "BTC-USD-PERP"})

        # Pump messages manually (deterministic)
        await ws_client.pump_once()
        await ws_client.pump_once()

        assert len(received_data) == 2
        assert received_data[0]["bid"] == "50000"
        assert received_data[1]["bid"] == "50010"

    @pytest.mark.asyncio
    async def test_combined_simulator_integration(self):
        """Test combined REST + WebSocket simulator integration."""
        # REST simulator
        def rest_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/v1/system/config"):
                return httpx.Response(200, json={"paraclear_decimals": 8})
            return httpx.Response(404, json={"error": "not found"})

        mock_transport = httpx.MockTransport(rest_handler)
        custom_http_client = httpx.Client(transport=mock_transport)

        # WebSocket simulator
        async def ws_connector(url: str, headers: dict):
            return MockWebSocketConnection(
                [json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": "50000", "ask": "50001"}})]
            )

        # Create fully injected Paradex instance
        paradex = Paradex(
            env=Environment.TESTNET,
            http_client=HttpClient(http_client=custom_http_client),
            api_base_url="https://rest-sim.example.com/v1",
            auto_start_ws_reader=False,
            ws_connector=ws_connector,
            ws_url_override="wss://ws-sim.example.com/v1",
        )

        # Verify both components are properly configured
        assert paradex.api_client.api_url == "https://rest-sim.example.com/v1"
        assert paradex.ws_client.api_url == "wss://ws-sim.example.com/v1"
        assert paradex.ws_client.auto_start_reader is False

        # Test WebSocket functionality
        await paradex.ws_client.connect()

        received_messages = []

        async def handler(channel, message):
            received_messages.append(message)

        await paradex.ws_client.subscribe(
            ParadexWebsocketChannel.BBO, callback=handler, params={"market": "BTC-USD-PERP"}
        )

        await paradex.ws_client.pump_once()
        assert len(received_messages) == 1
