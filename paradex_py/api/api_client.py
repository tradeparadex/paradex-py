import logging
from typing import Any, Dict, List, Optional

from paradex_py.api.environment import Environment
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import AccountSummary, AccountSummarySchema, AuthSchema, SystemConfig, SystemConfigSchema


class ParadexApiClient(HttpClient):
    api_url: str
    env: Environment

    def __init__(
        self,
        env: Environment,
        logger: Optional[logging.Logger] = None,
    ):
        self.env = env
        self.logger = logger or logging.getLogger(__name__)
        super().__init__()
        self.api_url = f"https://api.{self.env}.paradex.trade/v1"
        self.jwt: str = ""

    async def __aexit__(self):
        await self.client.close()

    def load_system_config(self) -> SystemConfig:
        res = self.request(
            url=f"{self.api_url}/system/config",
            http_method=HttpMethod.GET,
        )
        self.logger.info(f"ParadexApiClient: /system/config:{res}")
        config = SystemConfigSchema().load(res)
        self.logger.info(f"ParadexApiClient: SystemConfig:{config}")
        return config

    def onboarding(self, headers: dict, payload: dict):
        self.post(
            api_url=self.api_url,
            path="onboarding",
            headers=headers,
            payload=payload,
        )

    def auth(self, headers: dict) -> str:
        res = self.post(api_url=self.api_url, path="auth", headers=headers)
        data = AuthSchema().load(res)
        self.jwt = data.jwt_token
        self.client.headers.update({"Authorization": f"Bearer {self.jwt}"})
        self.logger.info(f"ParadexApiClient: JWT:{self.jwt}")
        return self.jwt

    # PRIVATE GET METHODS
    def fetch_orders(self, market: str) -> Optional[List]:
        params = {"market": market} if market else {}
        response = self.get(api_url=self.api_url, path="orders", params=params)
        return response.get("results") if response else None

    def fetch_orders_history(self, market: str = "") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self.get(api_url=self.api_url, path="orders-history", params=params)
        return response.get("results") if response else None

    def fetch_order(self, order_id: str) -> Optional[Dict]:
        path: str = f"orders/{order_id}"
        return self.get(api_url=self.api_url, path=path)

    def fetch_order_by_client_id(self, client_order_id: str) -> Optional[Dict]:
        path: str = f"orders/by_client_id/{client_order_id}"
        return self.get(api_url=self.api_url, path=path)

    def fetch_fills(self, market: str = "") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self.get(api_url=self.api_url, path="fills", params=params)
        return response.get("results") if response else None

    def fetch_funding_payments(self, market: str = "ALL") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self.get(api_url=self.api_url, path="funding/payments", params=params)
        return response.get("results") if response else None

    def fetch_transactions(self) -> Optional[List]:
        response = self.get(api_url=self.api_url, path="transactions")
        return response.get("results") if response else None

    def fetch_account_summary(self) -> AccountSummary:
        res = self.get(api_url=self.api_url, path="account")
        return AccountSummarySchema().load(res)

    def fetch_balances(self) -> Optional[List]:
        """Fetch all balances for the account"""
        response = self.get(api_url=self.api_url, path="balance")
        return response.get("results") if response else None

    def fetch_positions(self) -> Optional[List]:
        """Fetch all derivs positions for the account"""
        response = self.get(api_url=self.api_url, path="positions")
        return response.get("results") if response else None

    # PUBLIC GET METHODS
    def fetch_markets(self) -> Optional[List]:
        """Public RestAPI call to fetch all markets"""
        response = self.get(api_url=self.api_url, path="markets")
        return response.get("results") if response else None

    def fetch_markets_summary(self, market: str) -> Optional[List]:
        """Public RestAPI call to fetch market summary"""
        response = self.get(
            api_url=self.api_url,
            path="markets/summary",
            params={"market": market},
        )
        return response.get("results") if response else None

    def fetch_orderbook(self, market: str) -> dict:
        return self.get(api_url=self.api_url, path=f"orderbook/{market}")

    def fetch_insurance_fund(self) -> Optional[Dict[Any, Any]]:
        return self.get(api_url=self.api_url, path="insurance")

    def fetch_trades(self, market: str) -> Optional[List]:
        response = self.get(api_url=self.api_url, path="trades", params={"market": market})
        return response.get("results") if response else None

    # order helper functions
    def submit_order(self, order_payload: dict) -> Optional[Dict]:
        response = None
        try:
            response = self.post(api_url=self.api_url, path="orders", payload=order_payload)
        except Exception as err:
            self.logger.error(f"submit_order payload:{order_payload} exception:{err}")
        return response

    def cancel_order(self, order_id: str) -> Optional[Dict]:
        return self.delete(api_url=self.api_url, path=f"orders/{order_id}")

    def cancel_order_by_client_id(self, client_order_id: str) -> Optional[Dict]:
        return self.delete(api_url=self.api_url, path=f"orders/by_client_id/{client_order_id}")
