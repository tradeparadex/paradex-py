import logging
from typing import Optional

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import Environment


class Paradex:
    """Paradex class to interact with Paradex REST API.

    Args:
        env (Environment): Environment
        l1_address (str, optional): L1 address. Defaults to None.
        l1_private_key (str, optional): L1 private key. Defaults to None.
        l2_private_key (str, optional): L2 private key. Defaults to None.
        logger (logging.Logger, optional): Logger. Defaults to None.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET)
    """

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
        self.config = self.api_client.fetch_system_config()
        self.account: Optional[ParadexAccount] = None

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
        """Initialize paradex account with l1 or l2 private keys.
        Cannot be called if account is already initialized.

        Args:
            l1_address (str): L1 address
            l1_private_key (str): L1 private key
            l2_private_key (str): L2 private key
        """
        if self.account is not None:
            raise ValueError("Paradex: Account already initialized")
        self.account = ParadexAccount(
            config=self.config,
            l1_address=l1_address,
            l1_private_key=l1_private_key,
            l2_private_key=l2_private_key,
        )
        self.api_client.init_account(self.account)
        self.ws_client.init_account(self.account)
