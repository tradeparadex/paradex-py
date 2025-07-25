import asyncio
import json
import logging
import time
import traceback
from enum import Enum
from typing import Callable, Dict, Optional

import websockets
from websockets import ClientConnection, State

from paradex_py.account.account import ParadexAccount
from paradex_py.constants import WS_READ_TIMEOUT
from paradex_py.environment import Environment


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
    ORDER_BOOK = "order_book.{market}@{depth}@{refresh_rate}@{price_tick]"
    POSITIONS = "positions"
    TRADES = "trades.{market}"
    TRADEBUSTS = "tradebusts"
    TRANSACTIONS = "transaction"
    TRANSFERS = "transfers"


def _paradex_channel_prefix(value: str) -> str:
    return value.split(".")[0]


def _get_ws_channel_from_name(message_channel: str) -> Optional[ParadexWebsocketChannel]:
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

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET)
        >>> paradex.ws_client.connect()
    """

    classname: str = "ParadexWebsocketClient"

    def __init__(
        self,
        env: Environment,
        logger: Optional[logging.Logger] = None,
    ):
        self.env = env
        self.api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        self.logger = logger or logging.getLogger(__name__)
        self.ws: Optional[ClientConnection] = None
        self.account: Optional[ParadexAccount] = None
        self.callbacks: Dict[str, Callable] = {}
        self.subscribed_channels: Dict[str, bool] = {}
        asyncio.get_event_loop().create_task(self._read_messages())

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
            self.ws = await websockets.connect(
                self.api_url,
                additional_headers=extra_headers,
            )
            self.logger.info(f"{self.classname}: Connected to {self.api_url}")
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
        return bool(self.ws is not None and self.ws.state == State.OPEN)

    async def _close_connection(self):
        try:
            if self.ws:
                self.logger.info(f"{self.classname}: Closing connection...")
                await self.ws.close()
                self.logger.info(f"{self.classname}: Connection closed")
            else:
                self.logger.info(f"{self.classname}: No connection to close")
        except Exception:
            self.logger.exception(f"{self.classname}: Error thrown when closing connection {traceback.format_exc()}")

    async def _reconnect(self):
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
        websocket: ClientConnection,
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
            channel_subscribed: Optional[str] = message.get("result", {}).get("channel")
            if channel_subscribed:
                self.logger.info(f"{self.classname}: Subscribed to channel:{channel_subscribed}")
                self.subscribed_channels[channel_subscribed] = True

    async def _read_messages(self):
        while True:
            if self.ws and self.ws.state == State.OPEN:
                try:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=WS_READ_TIMEOUT)
                    message = json.loads(response)
                    self._check_subscribed_channel(message)
                    if "params" not in message:
                        self.logger.debug(f"{self.classname}: Non-actionable message:{message}")
                    else:
                        message_channel = message["params"].get("channel")
                        ws_channel: Optional[ParadexWebsocketChannel] = _get_ws_channel_from_name(message_channel)
                        if ws_channel is None:
                            self.logger.debug(
                                f"{self.classname}: unregistered channel:{message_channel} message:{message}"
                            )
                        elif message_channel in self.callbacks:
                            self.logger.debug(
                                f"{self.classname}: channel:{message_channel}"
                                f" callback:{self.callbacks[message_channel]}"
                                f" message:{message}"
                            )
                            await self.callbacks[message_channel](ws_channel, message)
                        else:
                            self.logger.info(f"{self.classname}: Non-callback channel:{message_channel}")
                    # yield message
                except (
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK,
                ):
                    self.logger.exception(f"{self.classname}: Connection closed traceback:{traceback.format_exc()}")
                    await self._reconnect()
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    self.logger.exception(f"{self.classname}: Connection failed traceback:{traceback.format_exc()}")
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(1)

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
        params: Optional[dict] = None,
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
