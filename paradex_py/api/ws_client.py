import asyncio
import json
import logging
import time
import traceback
from enum import Enum
from typing import Optional

import websockets

from paradex_py.account.account import ParadexAccount
from paradex_py.environment import Environment


class ParadexWebsocketChannel(Enum):
    """ParadexWebsocketChannel Enum class to define the channels for Paradex WS API.

    Attributes:
        FILLS (str): Fills channel
        ACCOUNT (str): Account channel
        MARKETS_SUMMARY (str): Markets summary channel
        ORDERS (str): Orders channel
        ORDER_BOOK (str): Order book channel
        POSITIONS (str): Positions channel
        TRADES (str): Trades channel
        TRADEBUSTS (str): Tradebusts channel
        TRANSACTIONS (str): Transactions channel
        BALANCE_EVENTS (str): Balance events channel
        FUNDING_DATA (str): Funding data channel
    """

    FILLS = "fills.{market}"
    ACCOUNT = "account"
    MARKETS_SUMMARY = "markets_summary"
    ORDERS = "orders.{market}"
    ORDER_BOOK = "order_book.{market}.snapshot@15@100ms"
    POSITIONS = "positions"
    TRADES = "trades.{market}"
    TRADEBUSTS = "tradebusts"
    TRANSACTIONS = "transaction"
    BALANCE_EVENTS = "balance_events"
    FUNDING_DATA = "funding_data.{market}"

    def prefix(self) -> str:
        return self.value.split(".")[0]


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

    def __init__(
        self,
        env: Environment,
        logger: Optional[logging.Logger] = None,
    ):
        self.env = env
        self.api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        self.logger = logger or logging.getLogger(__name__)
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    async def __aexit__(self):
        await self.close_connection()

    def init_account(self, account: ParadexAccount) -> None:
        self.account = account

    async def connect(self) -> None:
        try:
            extra_headers = {}
            if self.account:
                extra_headers.update({"Authorization": f"Bearer {self.account.jwt_token}"})
            self.ws = await websockets.connect(
                self.api_url,
                extra_headers=extra_headers,
            )
            self.logger.info(f"Paradex_WS: Connected to {self.api_url}")
            if self.account:
                await self.send_auth_id(self.ws, self.account.jwt_token)
                self.logger.info(f"Paradex_WS: Authenticated to {self.api_url}")
        except (
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosed,
        ) as e:
            self.logger.info(f"Paradex_WS connection already closed:{e}")
            self.ws = None
        except Exception as e:
            # Reduced from error to warning to avoid flood on Sentry
            self.logger.warning(f"error:{e} traceback:{traceback.format_exc()}")
            self.ws = None

    async def close_connection(self):
        try:
            if self.ws:
                self.logger.info("Paradex_WS Closing connection...")
                await self.ws.close()
                self.logger.info("Connection closed")
            else:
                self.logger.info("Paradex_WS: No connection to close")
        except Exception:
            self.logger.exception(f"Error thrown when closing connection {traceback.format_exc()}")

    async def reconnect(self):
        self.logger.info("Paradex_WS to reconnect websocket...")
        await self.close_connection()
        await self.connect()

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

    async def read_messages(self, read_timeout=0.1, backoff=0.1):
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=read_timeout)
                message = json.loads(response)
                if "id" in message:
                    channel_subscribed: Optional[str] = message.get("result", {}).get("channel")
                    if channel_subscribed:
                        self.logger.info(f"Paradex_WS: subscribed to channel:{channel_subscribed}")
                yield message
            except (
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
            ):
                self.logger.exception(f"Paradex_WS: connection closed {traceback.format_exc()}")
                await self.reconnect()
            except asyncio.TimeoutError:
                await asyncio.sleep(backoff)
            except Exception:
                self.logger.exception(f"Paradex_WS: connection failed {traceback.format_exc()}")
                await asyncio.sleep(1)

    async def _send(self, message: str):
        try:
            if self.ws:
                await self.ws.send(message)
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.info(f"Paradex_WS: Restarted connection {e}")
            await self.reconnect()
            if self.ws:
                await self.ws.send(message)
        except Exception:
            self.logger.exception(f"Paradex_WS: send failed {traceback.format_exc()}")
            await self.reconnect()

    async def subscribe(
        self,
        channel: ParadexWebsocketChannel,
        market: Optional[str] = None,
    ) -> None:
        channel_name = channel.value.format(market=market)
        self.logger.info(f"Paradex_WS: subscribe {channel}/{market} name:{channel_name}")
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
