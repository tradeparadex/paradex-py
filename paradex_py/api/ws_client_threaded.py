"""
Thread-based WebSocket client wrapper (built on sv/ws-reconnect).

This enhancement wraps the reconnect-aware async client in a background thread,
providing the simple synchronous interface requested in Issue #55.

Works seamlessly with the reconnection logic from sv/ws-reconnect branch.
"""

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass

from paradex_py.api.ws_client import ParadexWebsocketChannel, ParadexWebsocketClient
from paradex_py.environment import Environment


@dataclass
class WSMessage:
    """Message from WebSocket."""

    channel: str
    data: dict


class ThreadedParadexWebsocketClient:
    """
    Synchronous wrapper around async ParadexWebsocketClient.

    Solves Issue #55: Makes WebSocket easier to use without asyncio knowledge.

    Usage:
        client = ThreadedParadexWebsocketClient(env=Environment.TESTNET)
        with client:
            client.subscribe(ParadexWebsocketChannel.ACCOUNT)
            msg = client.get_updates(timeout=1.0)
    """

    def __init__(self, env: Environment, log_messages: bool = True):
        self.env = env
        self.log_messages = log_messages
        self.message_queue: queue.Queue = queue.Queue(maxsize=1000)

        self._ws_client: ParadexWebsocketClient | None = None
        self._ws_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()
        self.logger = logging.getLogger(__name__)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to WebSocket in background thread."""
        self._stop_event.clear()
        self._connected_event.clear()

        self._ws_thread = threading.Thread(
            target=self._run_event_loop,
            daemon=False,
        )
        self._ws_thread.start()

        return self._connected_event.wait(timeout=timeout)

    def subscribe(self, channel: ParadexWebsocketChannel) -> None:
        """Subscribe to a WebSocket channel."""
        self.message_queue.put(("_subscribe", channel))

    def get_updates(self, timeout: float | None = None) -> WSMessage | None:
        """Get next message (blocking)."""
        try:
            msg_type, data = self.message_queue.get(timeout=timeout)
        except queue.Empty:
            return None
        else:
            if msg_type.startswith("_"):
                return self.get_updates(timeout=timeout)
            return WSMessage(channel=msg_type, data=data)

    def close(self) -> None:
        """Close connection and cleanup."""
        self._stop_event.set()
        if self._ws_thread:
            self._ws_thread.join(timeout=5.0)

    def _run_event_loop(self) -> None:
        """Run asyncio event loop in background thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._async_loop())
        finally:
            loop.close()

    async def _async_loop(self) -> None:
        """Main async loop using the reconnect-aware client."""
        try:
            self._ws_client = ParadexWebsocketClient(
                env=self.env,
                log_messages=self.log_messages,
            )

            self._connected_event.set()

            while not self._stop_event.is_set():
                try:
                    # Check for commands
                    try:
                        cmd, channel = self.message_queue.get_nowait()
                        if cmd == "_subscribe":
                            await self._ws_client.subscribe(channel)
                    except queue.Empty:
                        pass

                    # Receive messages (benefits from their reconnect logic)
                    msg = await asyncio.wait_for(
                        self._ws_client.receive_message(),
                        timeout=1.0,
                    )
                    if msg:
                        self.message_queue.put((msg.get("channel"), msg))

                except asyncio.TimeoutError:
                    continue

        finally:
            if self._ws_client:
                await self._ws_client.close()
