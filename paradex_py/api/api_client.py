import asyncio
import json
import logging
import time
import traceback
from typing import Any, Dict, List, Optional

import websockets

from paradex_py.api.environment import Environment
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import AccountSummary, AccountSummarySchema, AuthSchema, SystemConfig, SystemConfigSchema


class ParadexWSClient:
    def __init__(
        self,
        ws_api_url: str,
        logger: Optional[logging.Logger] = None,
    ):
        self.ws_api_url = ws_api_url
        self.logger = logger or logging.getLogger(__name__)
        self.jwt: str = ""
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    async def connect(self, jwt: Optional[str] = None) -> None:
        if jwt:
            self.jwt = jwt
        try:
            self.ws = await websockets.connect(
                self.ws_api_url,
                extra_headers={"Authorization": f"Bearer {self.jwt}"},
            )
            self.logger.info(f"Paradex_WS: Connected to {self.ws_api_url}")
            await self.send_auth_id(self.ws, self.jwt)
            self.logger.info(f"Paradex_WS: Authenticated to {self.ws_api_url}")
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
        self.logger.info(f"Paradex_WS: subscribed to {channel}")

    async def read_ws_messages(self, read_timeout=0.1, backoff=0.1):
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=read_timeout)
                message = json.loads(response)
                if "id" in message:
                    channel_subscribed: str = message.get("result", {}).get("channel", "N/A")
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


class ParadexApiClient(HttpClient):
    env: Environment
    config: SystemConfig

    def __init__(
        self,
        env: Environment,
        logger: Optional[logging.Logger] = None,
    ):
        if env is None:
            raise ValueError("Paradex: Invalid environment")
        self.env = env
        self.logger = logger or logging.getLogger(__name__)
        super().__init__()
        self.api_url = f"https://api.{self.env}.paradex.trade/v1"
        self.ws_api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        self.ws_client = ParadexWSClient(ws_api_url=self.ws_api_url, logger=self.logger)
        self.jwt: str = ""

    async def __aexit__(self):
        await self.client.close()

    def load_system_config(self) -> SystemConfig:
        res = self.request(
            url=f"{self.api_url}/system/config",
            http_method=HttpMethod.GET,
        )
        res.update({"api_url": self.api_url, "ws_api_url": self.ws_api_url})
        self.logger.info(f"ParadexApiClient: /system/config:{res}")
        self.config = SystemConfigSchema().load(res)
        self.logger.info(f"ParadexApiClient: SystemConfig:{self.config}")
        return self.config

    def onboarding(self, headers: dict, payload: dict):
        self.post(
            api_url=self.config.api_url,
            path="onboarding",
            headers=headers,
            payload=payload,
        )

    def auth(self, headers: dict):
        res = self.post(api_url=self.config.api_url, path="auth", headers=headers)
        data = AuthSchema().load(res)
        self.jwt = data.jwt_token
        self.client.headers.update({"Authorization": f"Bearer {self.jwt}"})
        self.logger.info(f"ParadexApiClient: JWT:{self.jwt}")

    async def connect_ws(self):
        await self.ws_client.connect(jwt=self.jwt)

    # PRIVATE GET METHODS
    def fetch_orders(self, market: str) -> Optional[List]:
        params = {"market": market} if market else {}
        response = self.get(api_url=self.config.api_url, path="orders", params=params)
        return response.get("results") if response else None

    def fetch_orders_history(self, market: str = "") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self.get(api_url=self.config.api_url, path="orders-history", params=params)
        return response.get("results") if response else None

    def fetch_order(self, order_id: str) -> Optional[Dict]:
        path: str = f"orders/{order_id}"
        return self.get(api_url=self.config.api_url, path=path)

    def fetch_order_by_client_id(self, client_order_id: str) -> Optional[Dict]:
        path: str = f"orders/by_client_id/{client_order_id}"
        return self.get(api_url=self.config.api_url, path=path)

    def fetch_fills(self, market: str = "") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self.get(api_url=self.config.api_url, path="fills", params=params)
        return response.get("results") if response else None

    def fetch_funding_payments(self, market: str = "ALL") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self.get(api_url=self.config.api_url, path="funding/payments", params=params)
        return response.get("results") if response else None

    def fetch_transactions(self) -> Optional[List]:
        response = self.get(api_url=self.config.api_url, path="transactions")
        return response.get("results") if response else None

    def fetch_account_summary(self) -> AccountSummary:
        res = self.get(api_url=self.config.api_url, path="account")
        return AccountSummarySchema().load(res)

    def fetch_balances(self) -> Optional[List]:
        """Fetch all balances for the account"""
        response = self.get(api_url=self.config.api_url, path="balance")
        return response.get("results") if response else None

    def fetch_positions(self) -> Optional[List]:
        """Fetch all derivs positions for the account"""
        response = self.get(api_url=self.config.api_url, path="positions")
        return response.get("results") if response else None

    # PUBLIC GET METHODS
    def fetch_markets(self) -> Optional[List]:
        """Public RestAPI call to fetch all markets"""
        response = self.get(api_url=self.config.api_url, path="markets")
        return response.get("results") if response else None

    def fetch_markets_summary(self, market: str) -> Optional[List]:
        """Public RestAPI call to fetch market summary"""
        response = self.get(
            api_url=self.config.api_url,
            path="markets/summary",
            params={"market": market},
        )
        return response.get("results") if response else None

    def fetch_orderbook(self, market: str) -> dict:
        return self.get(api_url=self.config.api_url, path=f"orderbook/{market}")

    def fetch_insurance_fund(self) -> Optional[Dict[Any, Any]]:
        return self.get(api_url=self.config.api_url, path="insurance")

    def fetch_trades(self, market: str) -> Optional[List]:
        response = self.get(api_url=self.config.api_url, path="trades", params={"market": market})
        return response.get("results") if response else None

    # order helper functions
    def submit_order(self, order_payload: dict) -> Optional[Dict]:
        response = None
        try:
            response = self.post(api_url=self.config.api_url, path="orders", payload=order_payload)
        except Exception as err:
            self.logger.error(f"submit_order payload:{order_payload} exception:{err}")
        return response

    def cancel_order(self, order_id: str) -> Optional[Dict]:
        return self.delete(api_url=self.config.api_url, path=f"orders/{order_id}")

    def cancel_order_by_client_id(self, client_order_id: str) -> Optional[Dict]:
        return self.delete(api_url=self.config.api_url, path=f"orders/by_client_id/{client_order_id}")
