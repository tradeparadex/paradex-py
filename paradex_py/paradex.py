import logging
from typing import Optional

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.environment import Environment
from paradex_py.api.models import (
    AccountSummary,
    AccountSummarySchema,
    SystemConfig,
)
from paradex_py.common.order import Order

# from paradex_py.message.order import build_order_message


class Paradex:
    account: ParadexAccount
    api_client: ParadexApiClient
    config: SystemConfig
    env: Environment

    def __init__(
        self,
        env: Environment,
        l1_address: str,
        l1_private_key: Optional[str] = None,
        l2_private_key: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        if env is None:
            raise ValueError("Paradex: Invalid environment")
        self.env = env
        self.logger = logger
        # Load api client and system config
        self.api_client = ParadexApiClient(env=env, logger=logger)
        self.config = self.api_client.load_system_config()
        self.logger.info(f"Paradex: SystemConfig:{self.config}")

        # Initialize account if private key is provided
        if l2_private_key is not None or l1_private_key is not None:
            self.init_account(
                l1_address=l1_address,
                l1_private_key=l1_private_key,
                l2_private_key=l2_private_key,
            )

    def init_account(
        self,
        l1_address: str,
        l1_private_key: Optional[str] = None,
        l2_private_key: Optional[str] = None,
    ):
        self.account = ParadexAccount(
            config=self.config,
            l1_address=l1_address,
            l1_private_key=l1_private_key,
            l2_private_key=l2_private_key,
        )
        self.account_onboarding()
        self.account_auth()

    def account_onboarding(self):
        if self.account is None:
            raise ValueError("Paradex: Account not initialized")
        headers = self.account.onboarding_headers()
        payload = {"public_key": hex(self.account.l2_public_key)}
        self.logger.info(f"Paradex: Onboarding {payload}")
        self.api_client.onboarding(headers=headers, payload=payload)

    def account_auth(self):
        if self.account is None:
            raise ValueError("Paradex: Account not initialized")
        headers = self.account.auth_headers()
        self.api_client.auth(headers=headers)

    # PRIVATE GET METHODS
    def fetch_orders(self, market: str) -> list:
        params = {"market": market} if market else {}
        response = self.api_client.private_get(path="orders", params=params)
        return response.get("results") if response else None

    def fetch_account_summary(self) -> AccountSummary:
        res = self.api_client.private_get(path="account")
        return AccountSummarySchema().load(res)

    def fetch_balances(self) -> list:
        """Fetch all balances for the account"""
        response = self.api_client.private_get(path="balance")
        return response.get("results") if response else None

    def fetch_positions(self) -> list:
        """Fetch all derivs positions for the account"""
        response = self.api_client.private_get(path="positions")
        return response.get("results") if response else None

    # PUBLIC GET METHODS
    def fetch_markets(self) -> list:
        """Public RestAPI call to fetch all markets"""
        response = self.api_client.get(path="markets")
        return response.get("results") if response else None

    def fetch_markets_summary(self, market: str) -> list:
        """Public RestAPI call to fetch market summary"""
        response = self.api_client.get(
            path="markets/summary",
            params={"market": market},
        )
        return response.get("results") if response else None

    def fetch_orderbook(self, market: str) -> dict:
        return self.api_client.get(path=f"orderbook/{market}")

    # SEND, CANCEL ORDERS
    def send_order(self, order: Order) -> dict:
        response = None
        # order.signature_timestamp = int(time.time() * 1_000)
        order.signature = self.account.sign_order(order)
        order_payload = order.dump_to_dict()
        try:
            response = self.api_client.post(path="orders", payload=order_payload)
        except Exception as err:
            logging.error(f"send_order payload:{order_payload} exception:{err}")
        return response
