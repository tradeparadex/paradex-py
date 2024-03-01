import logging
import time
from typing import Any, Dict, List, Optional, Union

from paradex_py.account.account import ParadexAccount
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import AccountSummary, AccountSummarySchema, AuthSchema, SystemConfig, SystemConfigSchema
from paradex_py.common.order import Order
from paradex_py.environment import Environment


class ParadexApiClient(HttpClient):
    def __init__(
        self,
        env: Environment,
        logger: Optional[logging.Logger] = None,
    ):
        self.env = env
        self.logger = logger or logging.getLogger(__name__)
        super().__init__()
        self.api_url = f"https://api.{self.env}.paradex.trade/v1"

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

    def init_account(self, account: ParadexAccount):
        self.account = account
        self.onboarding()
        self.auth()

    def onboarding(self):
        headers = self.account.onboarding_headers()
        payload = {"public_key": hex(self.account.l2_public_key)}
        self.post(api_url=self.api_url, path="onboarding", headers=headers, payload=payload)

    def auth(self):
        headers = self.account.auth_headers()
        res = self.post(api_url=self.api_url, path="auth", headers=headers)
        data = AuthSchema().load(res)
        self.auth_timestamp = time.time()
        self.account.set_jwt_token(data.jwt_token)
        self.client.headers.update({"Authorization": f"Bearer {data.jwt_token}"})
        self.logger.info(f"ParadexApiClient: JWT:{data.jwt_token}")

    def _validate_auth(self):
        if self.account is None:
            raise ValueError("ParadexApiClient: Account not found")
        # Refresh JWT if it's older than 4 minutes
        if time.time() - self.auth_timestamp > 4 * 60:
            self.auth(headers=self.account.auth_headers())

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        return self.get(api_url=self.api_url, path=path, params=params)

    def _get_authorized(self, path: str, params: Optional[dict] = None) -> dict:
        self._validate_auth()
        return self._get(path=path, params=params)

    def _post_authorized(
        self,
        path: str,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        self._validate_auth()
        return self.post(api_url=self.api_url, path=path, payload=payload, params=params, headers=headers)

    def _delete_authorized(self, path: str) -> dict:
        self._validate_auth()
        return self.delete(api_url=self.api_url, path=path)

    # PRIVATE GET METHODS
    def fetch_orders(self, market: str) -> Optional[List]:
        params = {"market": market} if market else {}
        response = self._get_authorized(path="orders", params=params)
        return response.get("results") if response else None

    def fetch_orders_history(self, market: str = "") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self._get_authorized(path="orders-history", params=params)
        return response.get("results") if response else None

    def fetch_order(self, order_id: str) -> Optional[Dict]:
        path: str = f"orders/{order_id}"
        return self._get_authorized(path=path)

    def fetch_order_by_client_id(self, client_id: str) -> Optional[Dict]:
        path: str = f"orders/by_client_id/{client_id}"
        return self._get_authorized(path=path)

    def fetch_fills(self, market: str = "") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self._get_authorized(path="fills", params=params)
        return response.get("results") if response else None

    def fetch_funding_payments(self, market: str = "ALL") -> Optional[List]:
        params = {"market": market} if market else {}
        response = self._get_authorized(path="funding/payments", params=params)
        return response.get("results") if response else None

    def fetch_transactions(self) -> Optional[List]:
        response = self._get_authorized(path="transactions")
        return response.get("results") if response else None

    def fetch_account_summary(self) -> AccountSummary:
        res = self._get_authorized(path="account")
        return AccountSummarySchema().load(res)

    def fetch_balances(self) -> Optional[List]:
        """Fetch all balances for the account"""
        response = self._get_authorized(path="balance")
        return response.get("results") if response else None

    def fetch_positions(self) -> Optional[List]:
        """Fetch all positions for the account"""
        response = self._get_authorized(path="positions")
        return response.get("results") if response else None

    # PUBLIC GET METHODS
    def fetch_markets(self) -> Optional[List]:
        """Public RestAPI call to fetch all markets"""
        response = self._get(path="markets")
        return response.get("results") if response else None

    def fetch_markets_summary(self, market: str) -> Optional[List]:
        """Public RestAPI call to fetch market summary"""
        response = self._get(path="markets/summary", params={"market": market})
        return response.get("results") if response else None

    def fetch_orderbook(self, market: str) -> dict:
        return self._get(path=f"orderbook/{market}")

    def fetch_insurance_fund(self) -> Optional[Dict[Any, Any]]:
        return self._get(path="insurance")

    def fetch_trades(self, market: str) -> Optional[List]:
        response = self._get(path="trades", params={"market": market})
        return response.get("results") if response else None

    # order helper functions
    def submit_order(self, order: Order) -> Optional[Dict]:
        response = None
        order.signature = self.account.sign_order(order)
        order_payload = order.dump_to_dict()
        try:
            response = self._post_authorized(path="orders", payload=order_payload)
        except Exception as err:
            self.logger.error(f"submit_order payload:{order_payload} exception:{err}")
        return response

    def cancel_order(self, order_id: str) -> Optional[Dict]:
        return self._delete_authorized(path=f"orders/{order_id}")

    def cancel_order_by_client_id(self, client_id: str) -> Optional[Dict]:
        return self._delete_authorized(path=f"orders/by_client_id/{client_id}")
