import asyncio
import json
import logging
import time
import traceback
from typing import Optional

import websockets

from paradex_py.api.environment import Environment


class ParadexWebsocketClient:
    api_url: str
    env: Environment

    def __init__(
        self,
        env: Environment,
        logger: Optional[logging.Logger] = None,
    ):
        self.env = env
        self.api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        self.logger = logger or logging.getLogger(__name__)
        self.jwt: str = ""
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    async def connect(self, jwt: Optional[str] = None) -> None:
        if jwt:
            self.jwt = jwt
        try:
            self.ws = await websockets.connect(
                self.api_url,
                extra_headers={"Authorization": f"Bearer {self.jwt}"},
            )
            self.logger.info(f"Paradex_WS: Connected to {self.api_url}")
            await self.send_auth_id(self.ws, self.jwt)
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

    async def subscribe(self, channel: str) -> None:
        await self.send(
            json.dumps(
                {
                    "id": int(time.time() * 1_000_000),
                    "jsonrpc": "2.0",
                    "method": "subscribe",
                    "params": {"channel": channel},
                }
            )
        )
        self.logger.info(f"Paradex_WS: sent subscription for:{channel}")

    async def read_ws_messages(self, read_timeout=0.1, backoff=0.1):
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

    async def send(self, message: str):
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

    async def __aexit__(self):
        await self.close_connection()

    async def subscribe_to_orderbook(self, market: str) -> None:
        await self.subscribe(f"order_book.{market}.snapshot@15@100ms")

    async def subscribe_to_all_orders(self) -> None:
        await self.subscribe("orders.ALL")

    async def subscribe_to_markets_summary(self) -> None:
        await self.subscribe("markets_summary")

    async def subscribe_to_trades(self, market: str) -> None:
        await self.subscribe(f"trades.{market}")

    async def subscribe_to_positions(self) -> None:
        await self.subscribe("positions")

    async def subscribe_to_account(self) -> None:
        await self.subscribe("account")

    async def subscribe_to_all_fills(self) -> None:
        await self.subscribe("fills.ALL")
