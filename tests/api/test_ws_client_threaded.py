"""Tests for threaded WebSocket client."""

from paradex_py.api.ws_client_threaded import (
    ThreadedParadexWebsocketClient,
    WSMessage,
)
from paradex_py.environment import TESTNET


class TestThreadedParadexWebsocketClient:
    """Test cases for threaded WebSocket client."""

    def test_instantiate(self):
        """Test basic instantiation."""
        client = ThreadedParadexWebsocketClient(env=TESTNET)
        assert client is not None

    def test_message_dataclass(self):
        """Test WSMessage dataclass."""
        msg = WSMessage(channel="test", data={"key": "value"})
        assert msg.channel == "test"
        assert msg.data == {"key": "value"}

    def test_queue_isolation(self):
        """Test that each client has isolated message queue."""
        client1 = ThreadedParadexWebsocketClient(env=TESTNET)
        client2 = ThreadedParadexWebsocketClient(env=TESTNET)
        assert client1.message_queue is not client2.message_queue
