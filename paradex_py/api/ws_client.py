import asyncio
import contextlib
import json
import logging
import time
import traceback
from collections.abc import Callable
from enum import Enum
from typing import Any, Protocol

import websockets
from pydantic import BaseModel
from websockets import ClientConnection, State

from paradex_py.account.account import ParadexAccount
from paradex_py.constants import WS_TIMEOUT
from paradex_py.environment import Environment

# Optional typed message models
try:
    from paradex_py.api.ws_models import validate_ws_message

    TYPED_MODELS_AVAILABLE = True
except ImportError:
    TYPED_MODELS_AVAILABLE = False

    def validate_ws_message(message_data: dict[str, Any]) -> BaseModel | None:
        return None


class WebSocketConnection(Protocol):
    """Protocol for WebSocket-like connections."""

    async def send(self, data: str) -> None:
        """Send data to the connection."""
        ...

    async def recv(self) -> str:
        """Receive data from the connection."""
        ...

    async def close(self) -> None:
        """Close the connection."""
        ...

    @property
    def state(self) -> Any:
        """Connection state."""
        ...


class WebSocketConnector(Protocol):
    """Protocol for WebSocket connector factories."""

    async def __call__(self, url: str, headers: dict[str, str]) -> WebSocketConnection:
        """Create a WebSocket connection."""
        ...


class ParadexWebsocketChannel(Enum):
    """Enum class to define the channels for Paradex Websocket API.

    Attributes:
        ACCOUNT (str): Private websocket channel for receiving updates of account status
        BALANCE_EVENTS (str): Private websocket channel to receive PnL calculation data
        BBO (str): Public websocket channel for tick updates of orderbook best bid/ask prices and amounts
        FILLS (str): Private websocket channel to receive details of fills for specific account
        FUNDING_DATA (str): Public websocket channel to receive funding data updates
        FUNDING_PAYMENTS (str): Private websocket channel to receive funding payments of an account
        FUNDING_RATE_COMPARISON (str): Public websocket channel for funding rate comparisons across exchanges
        MARKETS_SUMMARY (str): Public websocket channel for updates of available markets
        ORDERS (str): Private websocket channel to receive order updates
        ORDER_BOOK (str): Public websocket channel for orderbook snapshot updates of depth 15 at most every 50ms or 100ms, optionally grouped by price tick
        POSITIONS (str): Private websocket channel to receive updates when position is changed
        TRADES (str): Public websocket channel to receive updates on trades in particular market
        TRADEBUSTS (str): Private websocket channel to receive fills that are busted by a blockchain
        TRANSACTIONS (str): Private websocket channel for receiving transaction details of fills
        TRANSFERS (str): Websocket channel for receiving transfer updates
    """

    ACCOUNT = "account"
    BALANCE_EVENTS = "balance_events"
    BBO = "bbo.{market}"
    FILLS = "fills.{market}"
    FUNDING_DATA = "funding_data.{market}"
    FUNDING_PAYMENTS = "funding_payments.{market}"
    FUNDING_RATE_COMPARISON = "funding_rate_comparison.{market}"
    MARKETS_SUMMARY = "markets_summary.{market}"
    ORDERS = "orders.{market}"
    ORDER_BOOK = "order_book.{market}.snapshot@{depth}@{refresh_rate}@{price_tick}"
    POSITIONS = "positions"
    TRADES = "trades.{market}"
    TRADEBUSTS = "tradebusts"
    TRANSACTIONS = "transaction"
    TRANSFERS = "transfers"


def _paradex_channel_prefix(value: str) -> str:
    return value.split(".")[0]


def _get_ws_channel_from_name(message_channel: str) -> ParadexWebsocketChannel | None:
    for channel in ParadexWebsocketChannel:
        if message_channel.startswith(_paradex_channel_prefix(channel.value)):
            return channel
    return None


class ParadexWebsocketClient:
    """Class to interact with Paradex WebSocket JSON-RPC API.
        Initialized along with `Paradex` class.

    Args:
        env (Environment): Environment
        logger (Optional[logging.Logger], optional): Logger. Defaults to None.
        ws_timeout (Optional[int], optional): WebSocket read timeout in seconds. Defaults to 20s.
        auto_start_reader (bool, optional): Whether to automatically start the message reader. Defaults to True.
        connector (Optional[WebSocketConnector], optional): Custom WebSocket connector for injection. Defaults to None.
        ws_url_override (Optional[str], optional): Custom WebSocket URL override. Defaults to None.
        reader_sleep_on_error (float, optional): Sleep duration after connection errors. Set to 0 for no sleep. Defaults to 1.0.
        reader_sleep_on_no_connection (float, optional): Sleep duration when no connection. Set to 0 for no sleep. Defaults to 1.0.
        validate_messages (bool, optional): Enable pydantic message validation. Requires pydantic. Defaults to False.
        ping_interval (float, optional): WebSocket ping interval in seconds. None uses websockets default. Defaults to None.
        disable_reconnect (bool, optional): Disable automatic reconnection for tight simulation control. Defaults to False.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET)
        >>> paradex.ws_client.connect()
        >>> # With custom timeout
        >>> from paradex_py.api.ws_client import ParadexWebsocketClient
        >>> ws_client = ParadexWebsocketClient(env=Environment.TESTNET, ws_timeout=30)
        >>> # With manual pumping disabled
        >>> ws_client = ParadexWebsocketClient(env=Environment.TESTNET, auto_start_reader=False)
        >>> # High-frequency simulator mode (no sleeps)
        >>> ws_client = ParadexWebsocketClient(env=Environment.TESTNET,
        ...                                   reader_sleep_on_error=0, reader_sleep_on_no_connection=0)
        >>> # With typed message validation
        >>> ws_client = ParadexWebsocketClient(env=Environment.TESTNET, validate_messages=True)
    """

    classname: str = "ParadexWebsocketClient"

    def __init__(
        self,
        env: Environment,
        logger: logging.Logger | None = None,
        ws_timeout: int | None = None,
        auto_start_reader: bool = True,
        connector: WebSocketConnector | None = None,
        ws_url_override: str | None = None,
        reader_sleep_on_error: float = 1.0,
        reader_sleep_on_no_connection: float = 1.0,
        validate_messages: bool = False,
        ping_interval: float | None = None,
        disable_reconnect: bool = False,
    ):
        self.env = env
        self.api_url = ws_url_override or f"wss://ws.api.{self.env}.paradex.trade/v1"
        self.logger = logger or logging.getLogger(__name__)
        self.ws: WebSocketConnection | ClientConnection | None = None
        self.account: ParadexAccount | None = None
        self.callbacks: dict[str, Callable] = {}
        self.subscribed_channels: dict[str, bool] = {}
        self.ws_timeout = ws_timeout if ws_timeout is not None else WS_TIMEOUT
        self.connector = connector
        self.auto_start_reader = auto_start_reader
        self._reader_task: asyncio.Task | None = None

        # Configurable sleep durations for simulator-friendly behavior
        self.reader_sleep_on_error = reader_sleep_on_error
        self.reader_sleep_on_no_connection = reader_sleep_on_no_connection

        # Heartbeat and reconnection control
        self.ping_interval = ping_interval
        self.disable_reconnect = disable_reconnect

        # Optional message validation
        self.validate_messages = validate_messages and TYPED_MODELS_AVAILABLE

        if auto_start_reader:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    self._reader_task = loop.create_task(self._read_messages())
                else:
                    # Event loop exists but not running, don't start task yet
                    self._reader_task = None
            except RuntimeError:
                # No event loop running, will start reader when connect() is called
                self._reader_task = None

    async def __aexit__(self):
        await self._close_connection()

    def init_account(self, account: ParadexAccount) -> None:
        self.account = account

    async def connect(self) -> bool:
        """Connect to Paradex WebSocket API.

        Returns:
            bool: True if connection is successful.

        Examples:
            >>> from paradex_py import Paradex
            >>> from paradex_py.environment import TESTNET
            >>> async def main():
            ...     paradex = Paradex(env=TESTNET)
            ...     await paradex.ws_client.connect()
            >>> import asyncio
            >>> asyncio.run(main())
        """

        try:
            self.subscribed_channels = {}
            extra_headers = {}
            if self.account:
                extra_headers.update({"Authorization": f"Bearer {self.account.jwt_token}"})

            # Use custom connector if provided, otherwise use default websockets.connect
            if self.connector is not None:
                self.ws = await self.connector(self.api_url, extra_headers)
            else:
                connect_kwargs: dict[str, Any] = {
                    "additional_headers": extra_headers,
                }
                if self.ping_interval is not None:
                    connect_kwargs["ping_interval"] = int(self.ping_interval)

                self.ws = await websockets.connect(self.api_url, **connect_kwargs)

            self.logger.info(f"{self.classname}: Connected to {self.api_url}")

            # Start reader task if auto_start_reader is enabled and not already running
            if self.auto_start_reader and self._reader_task is None:
                self._reader_task = asyncio.create_task(self._read_messages())

            if self.account:
                await self._send_auth_id(self.ws, self.account.jwt_token)
                self.logger.info(f"{self.classname}: Authenticated to {self.api_url}")
        except (
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosed,
        ):
            self.logger.exception(f"{self.classname}: Connection already closed")
            self.ws = None
        except Exception:
            self.logger.exception(f"{self.classname}: traceback:{traceback.format_exc()}")
            self.ws = None

        # Check connection state - handle both websockets.State and custom connection states
        is_connected = False
        if self.ws is not None:
            is_connected = self.ws.state == State.OPEN if hasattr(self.ws.state, "value") else hasattr(self.ws, "state")

        return is_connected

    async def close(self):
        """Close the WebSocket connection and clean up resources.

        This method should be called when done using the WebSocket client
        to properly clean up connections and background tasks.

        Examples:
            >>> import asyncio
            >>> from paradex_py.api.ws_client import ParadexWebsocketClient
            >>> from paradex_py.environment import Environment
            >>> async def main():
            ...     ws_client = ParadexWebsocketClient(env=Environment.TESTNET)
            ...     try:
            ...         await ws_client.connect()
            ...         # Use websocket client
            ...     finally:
            ...         await ws_client.close()
            >>> asyncio.run(main())
        """
        await self._close_connection()

    async def _close_connection(self):
        try:
            # Cancel reader task if it exists
            if self._reader_task and not self._reader_task.done():
                self._reader_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._reader_task
                self._reader_task = None

            if self.ws:
                self.logger.info(f"{self.classname}: Closing connection...")
                await self.ws.close()
                self.logger.info(f"{self.classname}: Connection closed")
            else:
                self.logger.info(f"{self.classname}: No connection to close")
        except Exception:
            self.logger.exception(f"{self.classname}: Error thrown when closing connection {traceback.format_exc()}")

    async def _reconnect(self):
        if self.disable_reconnect:
            self.logger.info(f"{self.classname}: Reconnection disabled, skipping...")
            return

        try:
            self.logger.info(f"{self.classname}: Reconnect websocket...")
            await self._close_connection()
            await self.connect()
            await self._resubscribe()
        except Exception:
            self.logger.exception(f"{self.classname}: Reconnect failed {traceback.format_exc()}")

    async def _resubscribe(self):
        if self.ws and self.ws.state == State.OPEN:
            for channel_name in self.callbacks:
                await self._subscribe_to_channel_by_name(channel_name)
        else:
            self.logger.warning(f"{self.classname}: Resubscribe - No connection")

    async def _send_auth_id(
        self,
        websocket: WebSocketConnection | ClientConnection,
        paradex_jwt: str,
    ) -> None:
        """
        Sends an authentication message to the Paradex WebSocket.
        """
        await websocket.send(
            json.dumps(
                {
                    "id": int(time.time() * 1_000_000),
                    "jsonrpc": "2.0",
                    "method": "auth",
                    "params": {"bearer": paradex_jwt},
                }
            )
        )

    def _check_subscribed_channel(self, message: dict) -> None:
        if "id" in message:
            channel_subscribed: str | None = message.get("result", {}).get("channel")
            if channel_subscribed:
                self.logger.info(f"{self.classname}: Subscribed to channel:{channel_subscribed}")
                self.subscribed_channels[channel_subscribed] = True

    def _is_connection_open(self) -> bool:
        """Check if WebSocket connection is open - handle both websockets and custom connections."""
        if not self.ws:
            return False

        if hasattr(self.ws.state, "value"):
            # websockets.State enum
            return self.ws.state == State.OPEN
        else:
            # Custom connection - check if state indicates open
            state_val = getattr(self.ws.state, "value", None) if hasattr(self.ws, "state") else None
            return state_val == "OPEN" or (state_val is None and hasattr(self.ws, "recv"))

    async def _receive_and_process_message(self) -> None:
        """Receive and process a single WebSocket message."""
        if self.ws is None:
            raise RuntimeError("WebSocket connection must be established before receiving messages")
        response = await asyncio.wait_for(self.ws.recv(), timeout=self.ws_timeout)
        if isinstance(response, bytes):
            response = response.decode("utf-8")
        await self._process_message(response)

    async def _handle_message_receive_error(self, error: Exception) -> None:
        """Handle errors that occur while receiving messages."""
        if isinstance(error, (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK)):
            self.logger.exception(f"{self.classname}: Connection closed traceback:{traceback.format_exc()}")
            await self._reconnect()
        elif isinstance(error, asyncio.TimeoutError):
            pass
        elif isinstance(error, asyncio.CancelledError):
            self.logger.info(f"{self.classname}: Reader task cancelled")
            raise
        else:
            self.logger.exception(f"{self.classname}: Connection failed traceback:{traceback.format_exc()}")
            if self.reader_sleep_on_error > 0:
                await asyncio.sleep(self.reader_sleep_on_error)

    async def _read_messages(self) -> None:
        try:
            while True:
                if self._is_connection_open() and self.ws is not None:
                    try:
                        await self._receive_and_process_message()
                    except Exception as e:
                        await self._handle_message_receive_error(e)
                elif self.reader_sleep_on_no_connection > 0:
                    await asyncio.sleep(self.reader_sleep_on_no_connection)
        except asyncio.CancelledError:
            # Re-raise cancellation to allow proper cleanup
            self.logger.info(f"{self.classname}: Reader task cancelled, cleaning up")
            raise
        except Exception:
            self.logger.exception(f"{self.classname}: Unexpected error in reader task: {traceback.format_exc()}")
            raise

    async def _process_message(self, response: str) -> None:
        """Process a single WebSocket message."""
        message = json.loads(response)
        self._check_subscribed_channel(message)
        if "params" not in message:
            self.logger.debug(f"{self.classname}: Non-actionable message:{message}")
        else:
            message_channel = message["params"].get("channel")
            ws_channel: ParadexWebsocketChannel | None = _get_ws_channel_from_name(message_channel)

            # Optional WebSocket RPC message validation
            if self.validate_messages:
                validated_message = validate_ws_message(message)
                if validated_message is not None:
                    # Use validated message structure
                    message = validated_message.model_dump() if hasattr(validated_message, "model_dump") else message
                    self.logger.debug(f"{self.classname}: WebSocket RPC message validated")
                else:
                    self.logger.warning(f"{self.classname}: WebSocket RPC message validation failed")

            if ws_channel is None:
                self.logger.debug(f"{self.classname}: unregistered channel:{message_channel} message:{message}")
            elif message_channel in self.callbacks:
                self.logger.debug(
                    f"{self.classname}: channel:{message_channel}"
                    f" callback:{self.callbacks[message_channel]}"
                    f" message:{message}"
                )
                await self.callbacks[message_channel](ws_channel, message)
            else:
                self.logger.info(f"{self.classname}: Non-callback channel:{message_channel}")

    async def pump_once(self) -> bool:
        """Manually pump one message from the WebSocket connection.

        Returns:
            bool: True if a message was processed, False if no message available or connection closed.
        """
        if not self.ws:
            return False

        try:
            # Try to receive with a very short timeout to avoid blocking
            response = await asyncio.wait_for(self.ws.recv(), timeout=0.001)
        except asyncio.TimeoutError:
            return False
        except Exception:
            self.logger.exception(f"{self.classname}: Error in pump_once: {traceback.format_exc()}")
            return False
        else:
            if isinstance(response, bytes):
                response = response.decode("utf-8")
            await self._process_message(response)
            return True

    async def inject(self, message: str) -> None:
        """Inject a raw message string into the message processing pipeline.

        Args:
            message: Raw JSON string to process as if received from WebSocket.
        """
        try:
            await self._process_message(message)
        except Exception:
            self.logger.exception(f"{self.classname}: Error in inject: {traceback.format_exc()}")

    async def _send(self, message: str):
        try:
            if self.ws:
                await self.ws.send(message)
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.info(f"{self.classname}: Restarted connection error:{e}")
            await self._reconnect()
            if self.ws:
                await self.ws.send(message)
        except Exception:
            self.logger.exception(f"{self.classname}: Send failed traceback:{traceback.format_exc()}")
            await self._reconnect()

    async def subscribe(
        self,
        channel: ParadexWebsocketChannel,
        callback: Callable,
        params: dict | None = None,
    ) -> None:
        """Subscribe to a websocket channel with optional parameters.
            Callback function is invoked when a message is received.

        Args:
            channel (ParadexWebsocketChannel): Channel to subscribe
            callback (Callable): Callback function
            params (Optional[dict], optional): Parameters for the channel. Defaults to None.

        Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import TESTNET
        >>> from paradex_py.api.ws_client import ParadexWebsocketChannel, ParadexWebsocketClient
        >>> async def main():
        ...     async def on_message(ws_channel, message):
        ...         print(ws_channel, message)
        ...     paradex = Paradex(env=TESTNET)
        ...     await paradex.ws_client.connect()
        ...     await paradex.ws_client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY, callback=on_message)
        >>> import asyncio
        >>> asyncio.run(main())
        """
        if params is None:
            params = {}
        # Note: Set default to all markets if no params are provided which
        # allows backward compatibility with old market_summary where
        # no params were required.
        if channel == ParadexWebsocketChannel.MARKETS_SUMMARY and not params:
            params = {"market": "ALL"}
        channel_name = channel.value.format(**params)
        self.callbacks[channel_name] = callback
        self.logger.info(f"{self.classname}: Subscribe channel:{channel_name} params:{params} callback:{callback}")
        await self._subscribe_to_channel_by_name(channel_name)

    async def subscribe_by_name(
        self,
        channel_name: str,
        callback: Callable | None = None,
    ) -> None:
        """Subscribe to a channel by exact name string.

        This is useful for simulation tooling where you want to subscribe
        to channels with exact names without using the enum formatting.

        Args:
            channel_name: Exact channel name (e.g., "bbo.BTC-USD-PERP")
            callback: Optional callback function. If provided, registers the callback.
        """
        if callback is not None:
            self.callbacks[channel_name] = callback
            self.logger.info(f"{self.classname}: Subscribe by name channel:{channel_name} callback:{callback}")

        await self._subscribe_to_channel_by_name(channel_name)

    async def unsubscribe_by_name(self, channel_name: str) -> None:
        """Unsubscribe from a channel by exact name string.

        Symmetric with subscribe_by_name for complete channel lifecycle control.

        Args:
            channel_name: Exact channel name (e.g., "bbo.BTC-USD-PERP")
        """
        # Remove from subscribed channels and callbacks
        self.subscribed_channels.pop(channel_name, None)
        self.callbacks.pop(channel_name, None)

        self.logger.info(f"{self.classname}: Unsubscribe by name channel:{channel_name}")

        # Send unsubscribe message
        unsubscribe_message = {
            "jsonrpc": "2.0",
            "method": "unsubscribe",
            "params": {"channel": channel_name},
            "id": str(int(time.time() * 1_000_000)),
        }
        await self._send(json.dumps(unsubscribe_message))

    def get_subscriptions(self) -> dict[str, bool]:
        """Get current subscription map.

        Returns:
            Dictionary mapping channel names to subscription status
        """
        return self.subscribed_channels.copy()

    async def pump_until(self, predicate: Callable[[dict], bool], timeout_s: float = 10.0) -> int:
        """Deterministic consumption helper for simulators.

        Pumps messages until predicate returns True or timeout is reached.
        Useful for waiting for specific message conditions in tests.

        Args:
            predicate: Function that takes a message dict and returns True to stop
            timeout_s: Maximum time to wait in seconds

        Returns:
            Number of messages processed before predicate was satisfied or timeout

        Examples:
            # Wait for BBO message with specific price
            count = await ws_client.pump_until(
                lambda msg: msg.get('params', {}).get('channel', '').startswith('bbo')
                           and float(msg.get('data', {}).get('bid', 0)) > 50000,
                timeout_s=5.0
            )
        """
        start_time = time.time()
        message_count = 0
        last_message = None

        # Set up temporary message capture
        def capture_message(channel: str, message: dict):
            nonlocal last_message
            last_message = message

        # Store original callbacks to restore later
        original_callbacks = self.callbacks.copy()

        try:
            while time.time() - start_time < timeout_s:
                # Try to pump one message
                if await self.pump_once():
                    message_count += 1
                    # Check if predicate is satisfied with the last message
                    if last_message and predicate(last_message):
                        break
                    else:
                        # Continue processing if predicate not satisfied
                        pass
                else:
                    # No message available, small delay to avoid busy waiting
                    await asyncio.sleep(0.001)
        finally:
            # Restore original callbacks
            self.callbacks = original_callbacks

        return message_count

    async def _subscribe_to_channel_by_name(
        self,
        channel_name: str,
    ) -> None:
        await self._send(
            json.dumps(
                {
                    "id": int(time.time() * 1_000_000),
                    "jsonrpc": "2.0",
                    "method": "subscribe",
                    "params": {"channel": channel_name},
                }
            )
        )
