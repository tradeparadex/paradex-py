import logging
from decimal import Decimal
from typing import Dict, Literal, Optional

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.environment import Environment
from paradex_py.api.models import (
    SystemConfig,
)
from paradex_py.common.order import Order, OrderSide, OrderType

# from paradex_py.message.order import build_order_message


class Paradex:
    account: ParadexAccount
    api_client: ParadexApiClient
    config: SystemConfig
    env: Environment

    def __init__(
        self,
        env: Environment,
        l1_address: Optional[str] = None,
        l1_private_key: Optional[str] = None,
        l2_private_key: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        if env is None:
            raise ValueError("Paradex: Invalid environment")
        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)
        # Load api client and system config
        self.api_client = ParadexApiClient(env=env, logger=logger)
        self.config = self.api_client.load_system_config()
        self.logger.info(f"Paradex: SystemConfig:{self.config}")

        # Initialize account if private key is provided
        if l1_address and (l2_private_key is not None or l1_private_key is not None):
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

    # SEND, CANCEL ORDERS
    def submit_order(self, order: Order) -> dict:
        response = None
        # order.signature_timestamp = int(time.time() * 1_000)
        order.signature = self.account.sign_order(order)
        order_payload = order.dump_to_dict()
        try:
            response = self.api_client.submit_order(order_payload)
        except Exception as err:
            self.logger.error(f"submit_order payload:{order_payload} exception:{err}")
        return response

    def send_order(
        self,
        market: str,
        order_type: OrderType,
        order_side: OrderSide,
        size: Decimal,
        limit_price: Decimal,
        client_id: str = "",
        instruction: Literal["GTC", "IOC", "POST_ONLY"] = "GTC",
        reduce_only: bool = False,
    ) -> dict:
        order = Order(
            market=market,
            order_type=order_type,
            order_side=order_side,
            size=size,
            limit_price=limit_price,
            client_id=client_id,
            instruction=instruction,
            reduce_only=reduce_only,
        )
        return self.submit_order(order=order)

    def cancel_order(self, order_id: str) -> Optional[Dict]:
        return self.api_client.cancel_order(order_id)

    def cancel_order_by_client_id(self, client_order_id: str) -> Optional[Dict]:
        return self.api_client.cancel_order_by_client_id(client_order_id)
