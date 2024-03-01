import logging
from typing import Optional

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import Environment

# from paradex_py.message.order import build_order_message


class Paradex:
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
        self.ws_client = ParadexWebsocketClient(env=env, logger=logger)
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
        self.api_client.init_account(self.account)
        self.ws_client.init_account(self.account)
