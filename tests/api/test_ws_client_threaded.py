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


# ── End to end through the real async client ─────────────────────────────
#
# Only the socket is faked: the threaded wrapper drives a real
# ParadexWebsocketClient on its own thread, so a callback the client cannot
# await, or a queue the two sides both consume, shows up as missing messages.

import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from websockets import State  # noqa: E402

from paradex_py.api.ws_client import ParadexWebsocketChannel  # noqa: E402
from tests.api.test_sbe_codec import _make_ms_frame  # noqa: E402


class _FakeSocket:
    """Delivers its frames once something has subscribed, then stays quiet."""

    def __init__(self, frames: list):
        self.frames = list(frames)
        self.state = State.OPEN
        self.sent: list[str] = []
        self.closed = False

    async def recv(self):
        while not self.sent or not self.frames:
            await asyncio.sleep(0.01)
        return self.frames.pop(0)

    async def send(self, message: str):
        self.sent.append(message)

    async def close(self):
        self.closed = True
        self.state = State.CLOSED


def _subscribed_channels(sock: _FakeSocket) -> list[str]:
    return [json.loads(m)["params"]["channel"] for m in sock.sent]


def _run_threaded(frames: list, subscribe) -> tuple[_FakeSocket, list[WSMessage]]:
    sock = _FakeSocket(frames)
    with patch("websockets.connect", new=AsyncMock(return_value=sock)):
        client = ThreadedParadexWebsocketClient(env=TESTNET)
        assert client.connect(timeout=5)
        subscribe(client)
        got = []
        deadline = time.monotonic() + 5
        while (len(got) < len(frames) or not sock.sent) and time.monotonic() < deadline:
            msg = client.get_updates(timeout=0.2)
            if msg:
                got.append(msg)
        client.close()
        assert not client._ws_thread.is_alive()
    return sock, got


def test_threaded_client_delivers_sbe_frames(caplog):
    with caplog.at_level(logging.ERROR):
        sock, got = _run_threaded(
            [_make_ms_frame(), _make_ms_frame(b"ETH-USD-PERP")],
            lambda c: c.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY),
        )
    # The async client awaits callbacks: a plain function still runs, but every
    # frame then raises in the reader, which logs it and backs off for a second.
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert [m.channel for m in got] == ["markets_summary.ALL", "markets_summary.ALL"]
    assert all(isinstance(m.channel, str) for m in got)
    assert [m.data["params"]["data"]["market"] for m in got] == ["BTC-USD-PERP", "ETH-USD-PERP"]
    assert got[0].data["encoding"] == "sbe"
    assert sock.closed


def test_threaded_client_keeps_running_after_a_bad_subscribe():
    """BBO needs a market; the failure must not take the other channels down."""
    sock, got = _run_threaded(
        [_make_ms_frame()],
        lambda c: (c.subscribe(ParadexWebsocketChannel.BBO), c.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY)),
    )
    assert _subscribed_channels(sock) == ["markets_summary.ALL"]
    assert len(got) == 1


def test_threaded_subscribe_passes_params():
    sock, _ = _run_threaded(
        [],
        lambda c: c.subscribe(ParadexWebsocketChannel.BBO, params={"market": "BTC-USD-PERP"}),
    )
    assert _subscribed_channels(sock) == ["bbo.BTC-USD-PERP"]


def test_get_updates_does_not_swallow_a_pending_subscribe():
    """Subscribe requests used to share the message queue, so a get_updates
    racing the background loop could take the request and drop it."""

    def subscribe_then_poll(c):
        c.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY)
        assert c.get_updates(timeout=0) is None

    sock, got = _run_threaded([_make_ms_frame()], subscribe_then_poll)
    assert _subscribed_channels(sock) == ["markets_summary.ALL"]
    assert len(got) == 1


def test_full_queue_drops_instead_of_blocking_the_loop():
    client = ThreadedParadexWebsocketClient(env=TESTNET)
    client.message_queue = __import__("queue").Queue(maxsize=1)
    frames = [_make_ms_frame()] * 3
    sock = _FakeSocket(frames)
    with patch("websockets.connect", new=AsyncMock(return_value=sock)):
        assert client.connect(timeout=5)
        client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY)
        deadline = time.monotonic() + 5
        while sock.frames and time.monotonic() < deadline:
            time.sleep(0.02)
        try:
            assert not sock.frames, "the loop stopped reading once the queue was full"
            assert client.message_queue.qsize() == 1
        finally:
            # Drain so a loop blocked on put() can finish and the thread can exit.
            while not client.message_queue.empty():
                client.message_queue.get_nowait()
            client.close()
    assert not client._ws_thread.is_alive()


def test_connect_reports_a_failed_connection():
    """connect() used to return True as soon as the thread started."""
    client = ThreadedParadexWebsocketClient(env=TESTNET)
    with patch("websockets.connect", new=AsyncMock(side_effect=OSError("refused"))):
        assert client.connect(timeout=5) is False
        client.close()
    assert not client._ws_thread.is_alive()
