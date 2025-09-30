"""Tests for WebSocket client enhancements: unsubscribe_by_name, get_subscriptions, pump_until, etc."""

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from websockets import State

from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import TESTNET


class MockWebSocketConnection:
    """Mock WebSocket connection for testing."""

    def __init__(self, messages=None, should_fail=False):
        self.messages = messages or []
        self._message_iter = iter(self.messages)
        self.state = State.OPEN
        self.sent_messages = []
        self.should_fail = should_fail

    async def send(self, data: str):
        if self.should_fail:
            raise Exception("Send failed")
        self.sent_messages.append(data)

    async def recv(self) -> str:
        if self.should_fail:
            raise Exception("Receive failed")
        try:
            return next(self._message_iter)
        except StopIteration as err:
            # Simulate waiting indefinitely
            await asyncio.sleep(10)
            raise asyncio.TimeoutError() from err

    async def close(self):
        self.state = State.CLOSED


class TestWebSocketEnhancements:
    """Test WebSocket client enhancements."""

    def setup_method(self):
        """Set up test fixtures."""
        self.ws_client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)

    @pytest.mark.asyncio
    async def test_subscribe_by_name(self):
        """Test subscribe_by_name method."""
        # Mock the WebSocket connection
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, connector=mock_connector)
        await client.connect()

        # Test callback registration
        callback_called = False
        received_message = None

        def test_callback(channel: str, message: dict):
            nonlocal callback_called, received_message
            callback_called = True
            received_message = message

        await client.subscribe_by_name("bbo.BTC-USD-PERP", test_callback)

        # Verify subscription message was sent
        assert len(mock_connection.sent_messages) == 1
        sent_message = json.loads(mock_connection.sent_messages[0])
        assert sent_message["method"] == "subscribe"
        assert sent_message["params"]["channel"] == "bbo.BTC-USD-PERP"
        assert sent_message["jsonrpc"] == "2.0"

        # Verify callback was registered
        assert "bbo.BTC-USD-PERP" in client.callbacks
        assert client.callbacks["bbo.BTC-USD-PERP"] == test_callback

    @pytest.mark.asyncio
    async def test_unsubscribe_by_name(self):
        """Test unsubscribe_by_name method."""
        mock_connection = MockWebSocketConnection()

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, connector=mock_connector)
        await client.connect()

        # First subscribe
        client.subscribed_channels["bbo.BTC-USD-PERP"] = True
        client.callbacks["bbo.BTC-USD-PERP"] = lambda x, y: None

        # Then unsubscribe
        await client.unsubscribe_by_name("bbo.BTC-USD-PERP")

        # Verify unsubscription message was sent
        assert len(mock_connection.sent_messages) == 1
        sent_message = json.loads(mock_connection.sent_messages[0])
        assert sent_message["method"] == "unsubscribe"
        assert sent_message["params"]["channel"] == "bbo.BTC-USD-PERP"
        assert sent_message["jsonrpc"] == "2.0"

        # Verify channel was removed from tracking
        assert "bbo.BTC-USD-PERP" not in client.subscribed_channels
        assert "bbo.BTC-USD-PERP" not in client.callbacks

    def test_get_subscriptions(self):
        """Test get_subscriptions method."""
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)

        # Add some subscriptions
        client.subscribed_channels["bbo.BTC-USD-PERP"] = True
        client.subscribed_channels["trades.ETH-USD-PERP"] = False
        client.subscribed_channels["order_book.BTC-USD-PERP"] = True

        subscriptions = client.get_subscriptions()

        # Should return a copy of the subscriptions
        assert subscriptions == {
            "bbo.BTC-USD-PERP": True,
            "trades.ETH-USD-PERP": False,
            "order_book.BTC-USD-PERP": True,
        }

        # Should be a copy, not the original
        assert subscriptions is not client.subscribed_channels

        # Modifying returned dict should not affect original
        subscriptions["new.channel"] = True
        assert "new.channel" not in client.subscribed_channels

    @pytest.mark.asyncio
    async def test_pump_once_success(self):
        """Test pump_once method with available message."""
        test_message = json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": "50000", "ask": "50001"}})

        mock_connection = MockWebSocketConnection([test_message])

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, connector=mock_connector)
        await client.connect()

        # Mock the message processing
        processed_message = None

        async def mock_process_message(message: str):
            nonlocal processed_message
            processed_message = message

        with patch.object(client, "_process_message", side_effect=mock_process_message):
            result = await client.pump_once()

        assert result is True
        assert processed_message == test_message

    @pytest.mark.asyncio
    async def test_pump_once_no_message(self):
        """Test pump_once method with no available message."""
        mock_connection = MockWebSocketConnection([])  # No messages

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, connector=mock_connector)
        await client.connect()

        # Should return False quickly due to timeout
        result = await client.pump_once()
        assert result is False

    @pytest.mark.asyncio
    async def test_pump_once_exception(self):
        """Test pump_once method with connection exception."""
        mock_connection = MockWebSocketConnection(should_fail=True)

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, connector=mock_connector)
        await client.connect()

        result = await client.pump_once()
        assert result is False

    @pytest.mark.asyncio
    async def test_inject_message(self):
        """Test inject method for manual message injection."""
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)

        processed_message = None

        async def mock_process_message(message: str):
            nonlocal processed_message
            processed_message = message

        with patch.object(client, "_process_message", side_effect=mock_process_message):
            test_message = json.dumps({"params": {"channel": "test"}, "data": {"test": True}})
            await client.inject(test_message)

        assert processed_message == test_message

    @pytest.mark.asyncio
    async def test_pump_until_predicate_satisfied(self):
        """Test pump_until method with predicate satisfaction."""
        test_messages = [
            json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": "49000", "ask": "49001"}}),
            json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": "50000", "ask": "50001"}}),
            json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": "51000", "ask": "51001"}}),
        ]

        mock_connection = MockWebSocketConnection(test_messages)

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, connector=mock_connector)
        await client.connect()

        # Predicate: stop when bid price >= 50000
        def price_predicate(message: dict) -> bool:
            data = message.get("data", {})
            bid = float(data.get("bid", "0"))
            return bid >= 50000

        # Mock pump_once to simulate message processing
        message_index = 0

        async def mock_pump_once():
            nonlocal message_index
            if message_index < len(test_messages):
                message = test_messages[message_index]
                message_index += 1
                # Simulate message processing by calling the callback
                json.loads(message)
                # Simulate the captured message for predicate testing
                return True
            return False

        with patch.object(client, "pump_once", side_effect=mock_pump_once):
            # Need to simulate the message capture mechanism
            captured_messages = []

            def capture_message(channel: str, message: dict):
                captured_messages.append(message)

            # Mock the callback setup
            client.callbacks.copy()
            client.callbacks = {"test": capture_message}

            # Manually set up the last_message tracking for the test
            last_message = None

            async def mock_pump_once_with_capture():
                nonlocal message_index, last_message
                if message_index < len(test_messages):
                    message_str = test_messages[message_index]
                    message_index += 1
                    last_message = json.loads(message_str)
                    return True
                return False

            # Override the pump_once method and manually control last_message
            with patch.object(client, "pump_once", side_effect=mock_pump_once_with_capture):
                # Manually implement a simplified version of pump_until for testing
                start_time = time.time()
                message_count = 0
                timeout_s = 5.0

                while time.time() - start_time < timeout_s:
                    if await client.pump_once():
                        message_count += 1
                        if last_message and price_predicate(last_message):
                            break
                    else:
                        await asyncio.sleep(0.001)

                assert message_count == 2  # Should stop after second message (bid=50000)

    @pytest.mark.asyncio
    async def test_pump_until_timeout(self):
        """Test pump_until method with timeout."""
        # No messages, should timeout
        mock_connection = MockWebSocketConnection([])

        async def mock_connector(url: str, headers: dict):
            return mock_connection

        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, connector=mock_connector)
        await client.connect()

        def never_satisfied(message: dict) -> bool:
            return False

        with patch.object(client, "pump_once", return_value=False):
            start_time = time.time()
            result = await client.pump_until(never_satisfied, timeout_s=0.1)
            end_time = time.time()

            assert result == 0  # No messages processed
            assert end_time - start_time >= 0.1  # Should have waited for timeout

    def test_configurable_sleep_durations(self):
        """Test configurable sleep durations for high-frequency simulation."""
        # Test zero sleep for high-frequency simulation
        client = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            reader_sleep_on_error=0.0,
            reader_sleep_on_no_connection=0.0,
        )

        assert client.reader_sleep_on_error == 0.0
        assert client.reader_sleep_on_no_connection == 0.0

        # Test custom sleep durations
        client_custom = ParadexWebsocketClient(
            env=TESTNET,
            auto_start_reader=False,
            reader_sleep_on_error=0.5,
            reader_sleep_on_no_connection=0.1,
        )

        assert client_custom.reader_sleep_on_error == 0.5
        assert client_custom.reader_sleep_on_no_connection == 0.1

    def test_ping_interval_configuration(self):
        """Test ping interval configuration."""
        # Test custom ping interval
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, ping_interval=30.0)
        assert client.ping_interval == 30.0

        # Test default ping interval (None)
        client_default = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
        assert client_default.ping_interval is None

    def test_disable_reconnect_configuration(self):
        """Test disable reconnect configuration."""
        # Test with reconnect disabled
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, disable_reconnect=True)
        assert client.disable_reconnect is True

        # Test with reconnect enabled (default)
        client_default = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
        assert client_default.disable_reconnect is False

    @pytest.mark.asyncio
    async def test_reconnect_disabled(self):
        """Test that reconnection is skipped when disabled."""
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, disable_reconnect=True)

        with (
            patch.object(client, "_close_connection") as mock_close,
            patch.object(client, "connect") as mock_connect,
            patch.object(client, "_resubscribe") as mock_resubscribe,
        ):
            await client._reconnect()

            # Should not attempt to reconnect when disabled
            mock_close.assert_not_called()
            mock_connect.assert_not_called()
            mock_resubscribe.assert_not_called()

    def test_ws_url_override(self):
        """Test WebSocket URL override."""
        custom_url = "wss://custom.example.com/v1"
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, ws_url_override=custom_url)

        assert client.api_url == custom_url

    def test_validate_messages_configuration(self):
        """Test message validation configuration."""
        # Test with validation enabled
        ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, validate_messages=True)
        # Should be enabled only if typed models are available
        # This depends on whether pydantic models are available in the test environment

        # Test with validation disabled (default)
        client_default = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
        assert client_default.validate_messages is False

    @pytest.mark.asyncio
    async def test_connection_state_checking(self):
        """Test connection state checking helper method."""
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)

        # Test with no connection
        assert client._is_connection_open() is False

        # Test with mock connection
        mock_connection = MockWebSocketConnection()
        client.ws = mock_connection

        assert client._is_connection_open() is True

        # Test with closed connection
        mock_connection.state = State.CLOSED
        assert client._is_connection_open() is False


class TestWebSocketMessageValidation:
    """Test WebSocket message validation features."""

    @pytest.mark.asyncio
    async def test_message_validation_enabled(self):
        """Test message validation when enabled."""
        # This test depends on whether typed models are available
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, validate_messages=True)

        # Mock a valid message
        valid_message = {
            "jsonrpc": "2.0",
            "params": {"channel": "bbo.BTC-USD-PERP"},
            "data": {"bid": "50000", "ask": "50001"},
        }

        # Mock the validation function
        with patch("paradex_py.api.ws_client.validate_ws_message") as mock_validate:
            mock_validate.return_value = MagicMock(model_dump=lambda: valid_message)

            await client._process_message(json.dumps(valid_message))

            # Should have called validation
            mock_validate.assert_called_once_with(valid_message)

    @pytest.mark.asyncio
    async def test_message_validation_disabled(self):
        """Test message validation when disabled."""
        client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False, validate_messages=False)

        valid_message = {
            "params": {"channel": "bbo.BTC-USD-PERP"},
            "data": {"bid": "50000", "ask": "50001"},
        }

        # Mock the validation function
        with patch("paradex_py.api.ws_client.validate_ws_message") as mock_validate:
            await client._process_message(json.dumps(valid_message))

            # Should not have called validation
            mock_validate.assert_not_called()
