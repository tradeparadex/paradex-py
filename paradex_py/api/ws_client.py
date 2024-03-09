import asyncio
import json
import logging
import time
import traceback
from decimal import Decimal
from enum import Enum
from typing import Callable, Dict, Literal, Optional

import websockets

from paradex_py.account.account import ParadexAccount
from paradex_py.common.order import Order, OrderSide, OrderStatus, OrderType
from paradex_py.environment import Environment


def order_from_ws_message(msg: dict) -> Order:
    """
    Creates an Order object from a Paradex websocket message.
    """
    client_id = msg["client_id"] if msg["client_id"] else msg["id"]
    order = Order(
        market=msg["market"],
        order_type=OrderType(msg["type"]),
        order_side=OrderSide(msg["side"]),
        size=Decimal(msg["size"]),
        limit_price=Decimal(msg["price"]),
        client_id=client_id,
        instruction=msg.get("instruction", "GTC"),
        reduce_only=bool("REDUCE_ONLY" in msg.get("flags", [])),
    )
    order.id = msg["id"]
    order.status = OrderStatus(msg["status"])
    order.account = msg["account"]
    order.remaining = Decimal(msg["remaining_size"])
    order.created_at = int(msg["created_at"])
    order.cancel_reason = msg["cancel_reason"]
    return order


class ParadexWebsocketChannel(Enum):
    """ParadexWebsocketChannel Enum class to define the channels for Paradex WS API.

    Attributes:
        ACCOUNT (str): Account channel
        BALANCE_EVENTS (str): Balance events channel
        BBO (str): Best Bid Offer channel
        FILLS (str): Fills channel
        FUNDING_DATA (str): Funding data channel
        FUNDING_PAYMENTS (str): Funding payments channel
        MARKETS_SUMMARY (str): Markets summary channel
        ORDERS (str): Orders channel
        ORDER_BOOK (str): Order book snapshots channel
        ORDER_BOOK_DELTAS (str): Order book deltas channel
        POINTS_DATA (str): Points data channel
        POSITIONS (str): Positions channel
        TRADES (str): Trades channel
        TRADEBUSTS (str): Tradebusts channel
        TRANSACTIONS (str): Transactions channel
        TRANSFERS (str): Transfers channel
    """

    ACCOUNT = "account"
    BALANCE_EVENTS = "balance_events"
    BBO = "bbo.{market}"
    FILLS = "fills.{market}"
    FUNDING_DATA = "funding_data.{market}"
    FUNDING_PAYMENTS = "funding_payments.{market}"
    MARKETS_SUMMARY = "markets_summary"
    ORDERS = "orders.{market}"
    ORDER_BOOK = "order_book.{market}.snapshot@15@100ms"
    ORDER_BOOK_DELTAS = "order_book.{market}.deltas"
    POINTS_DATA = "points_data.{market}.{program}"
    POSITIONS = "positions"
    TRADES = "trades.{market}"
    TRADEBUSTS = "tradebusts"
    TRANSACTIONS = "transaction"
    TRANSFERS = "transfers"


def paradex_channel_prefix(value: str) -> str:
    return value.split(".")[0]


def paradex_channel_suffix(value: str) -> str:
    return value.split(".")[-1]


def paradex_channel_market(value: str) -> Optional[str]:
    value_split = value.split(".")
    if len(value_split) > 1:
        return value_split[1]
    return None


def get_ws_channel_from_name(message_channel: str) -> Optional[ParadexWebsocketChannel]:
    for channel in ParadexWebsocketChannel:
        if message_channel.startswith(paradex_channel_prefix(channel.value)):
            return channel
    return None


PointsProgram = Literal["LiquidityProvider", "Trader"]


class ParadexWebsocketClient:
    """ParadexWebsocketChannel class to interact with Paradex WS API.
    Initialized along with Paradex class.

    Args:
        env (Environment): Environment
        logger (Optional[logging.Logger], optional): Logger. Defaults to None.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET)
        >>> paradex.ws_client.connect()
    """

    classname: str = "Paradex-WS"

    def __init__(
        self,
        env: Environment,
        logger: Optional[logging.Logger] = None,
    ):
        self.env = env
        self.api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        self.logger = logger or logging.getLogger(__name__)
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.callbacks: Dict[str, Callable] = {}
        self.subscribed_channels: Dict[str, bool] = {}
        asyncio.get_event_loop().create_task(self.read_messages())

    async def __aexit__(self):
        await self.close_connection()

    def init_account(self, account: ParadexAccount) -> None:
        self.account = account

    async def connect(self) -> None:
        try:
            self.subscribed_channels = {}
            extra_headers = {}
            if self.account:
                extra_headers.update({"Authorization": f"Bearer {self.account.jwt_token}"})
            self.ws = await websockets.connect(
                self.api_url,
                extra_headers=extra_headers,
            )
            self.logger.info(f"{self.classname} Connected to {self.api_url}")
            if self.account:
                await self.send_auth_id(self.ws, self.account.jwt_token)
                self.logger.info(f"{self.classname} Authenticated to {self.api_url}")
        except (
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosed,
        ) as e:
            self.logger.info(f"{self.classname} connection already closed:{e}")
            self.ws = None
        except Exception as e:
            # Reduced from error to warning to avoid flood on Sentry
            self.logger.warning(f"error:{e} traceback:{traceback.format_exc()}")
            self.ws = None

    async def close_connection(self):
        try:
            if self.ws:
                self.logger.info(f"{self.classname} Closing connection...")
                await self.ws.close()
                self.logger.info(f"{self.classname} Connection closed")
            else:
                self.logger.info(f"{self.classname} No connection to close")
        except Exception:
            self.logger.exception(f"{self.classname} Error thrown when closing connection {traceback.format_exc()}")

    async def reconnect(self):
        try:
            self.logger.info("{self.classname} to reconnect websocket...")
            await self.close_connection()
            await self.connect()
            await self.re_subscribe()
        except Exception:
            self.logger.exception(f"{self.classname} reconnect failed {traceback.format_exc()}")

    async def re_subscribe(self):
        if self.ws and self.ws.open:
            for channel_name in self.callbacks:
                await self._subscribe_to_channel_by_name(channel_name)
        else:
            self.logger.warning(f"{self.classname} re_subscribe - No connection.")

    async def send_auth_id(
        self,
        websocket: websockets.WebSocketClientProtocol,
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

    def check_susbcribed_channel(self, message: dict) -> None:
        if "id" in message:
            channel_subscribed: Optional[str] = message.get("result", {}).get("channel")
            if channel_subscribed:
                self.logger.info(f"{self.classname} subscribed to channel:{channel_subscribed}")
                self.subscribed_channels[channel_subscribed] = True

    async def read_messages(self, read_timeout=5, backoff=0.1):
        FN = f"{self.classname} read_messages"
        while True:
            if self.ws and self.ws.open:
                try:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=read_timeout)
                    message = json.loads(response)
                    self.check_susbcribed_channel(message)
                    if "params" not in message:
                        self.logger.debug(f"{FN} Non-actionable message:{message}")
                    else:
                        message_channel = message["params"].get("channel")
                        ws_channel: Optional[ParadexWebsocketChannel] = get_ws_channel_from_name(message_channel)
                        if ws_channel is None:
                            self.logger.debug(
                                f"{FN} Non-registered ParadexWebsocketChannel:{message_channel} {message}"
                            )
                        elif message_channel in self.callbacks:
                            self.logger.debug(
                                f"{FN} Channel:{message_channel}"
                                f" callback:{self.callbacks[message_channel]}"
                                f" message:{message}"
                            )
                            await self.callbacks[message_channel](ws_channel, message)
                        else:
                            self.logger.info(f"{FN} Non callback channel:{message_channel}")
                    # yield message
                except (
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK,
                ):
                    self.logger.exception(f"{FN} connection closed {traceback.format_exc()}")
                    await self.reconnect()
                except asyncio.TimeoutError:
                    await asyncio.sleep(backoff)
                except Exception:
                    self.logger.exception(f"{FN} connection failed {traceback.format_exc()}")
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(1)

    async def _send(self, message: str):
        try:
            if self.ws:
                await self.ws.send(message)
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.info(f"{self.classname} _send() Restarted connection {e}")
            await self.reconnect()
            if self.ws:
                await self.ws.send(message)
        except Exception:
            self.logger.exception(f"{self.classname} send failed {traceback.format_exc()}")
            await self.reconnect()

    async def subscribe(
        self,
        channel: ParadexWebsocketChannel,
        callback: Callable,
        params: Optional[dict] = None,
    ) -> None:
        FN = f"{self.classname} subscribe"
        if params is None:
            params = {}
        channel_name = channel.value.format(**params)
        self.callbacks[channel_name] = callback
        self.logger.info(f"{FN} {channel}/{params} name:{channel_name} callback:{callback}")
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
