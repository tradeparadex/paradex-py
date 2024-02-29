import logging
from typing import Optional

from paradex_py.api.environment import Environment
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import (
    AccountSummary,
    AccountSummarySchema,
    AuthSchema,
    SystemConfig,
    SystemConfigSchema,
)


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

    async def __aexit__(self):
        await self.client.close()

    def load_system_config(self) -> SystemConfig:
        api_url = f"https://api.{self.env}.paradex.trade/v1"
        ws_api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        res = self.request(
            url=f"{api_url}/system/config",
            http_method=HttpMethod.GET,
        )
        res.update({"api_url": api_url, "ws_api_url": ws_api_url})
        self.logger.info(f"ParadexApiClient: /system/config:{res}")
        self.config = SystemConfigSchema().load(res)
        self.logger.info(f"ParadexApiClient: SystemConfig:{self.config}")
        return self.config

    def onboarding(self, headers: dict, payload: dict):
        self.post(
            path="onboarding",
            headers=headers,
            payload=payload,
        )

    def auth(self, headers: dict):
        res = self.post(path="auth", headers=headers)
        data = AuthSchema().load(res)
        self.client.headers.update({"Authorization": f"Bearer {data.jwt_token}"})
        self.logger.info(f"ParadexApiClient: JWT:{data.jwt_token}")

    # PRIVATE GET METHODS
    def fetch_orders(self, market: str) -> list:
        params = {"market": market} if market else {}
        response = self.get(path="orders", params=params)
        return response.get("results") if response else None

    def fetch_account_summary(self) -> AccountSummary:
        res = self.get(path="account")
        return AccountSummarySchema().load(res)

    def fetch_balances(self) -> list:
        """Fetch all balances for the account"""
        response = self.get(path="balance")
        return response.get("results") if response else None

    def fetch_positions(self) -> list:
        """Fetch all derivs positions for the account"""
        response = self.get(path="positions")
        return response.get("results") if response else None

    # PUBLIC GET METHODS
    def fetch_markets(self) -> list:
        """Public RestAPI call to fetch all markets"""
        response = self.get(path="markets")
        return response.get("results") if response else None

    def fetch_markets_summary(self, market: str) -> list:
        """Public RestAPI call to fetch market summary"""
        response = self.get(
            path="markets/summary",
            params={"market": market},
        )
        return response.get("results") if response else None

    def fetch_orderbook(self, market: str) -> dict:
        return self.get(path=f"orderbook/{market}")

    def submit_order(self, order_payload: dict) -> dict:
        response = None
        try:
            response = self.post(path="orders", payload=order_payload)
        except Exception as err:
            self.logger.error(f"submit_order payload:{order_payload} exception:{err}")
        return response
