import logging
from typing import Optional

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import Environment
from paradex_py.utils import raise_value_error


class Paradex:
    """Paradex class to interact with Paradex REST API.

    Args:
        env (Environment): Environment
        l1_address (str, optional): L1 address. Defaults to None.
        l1_private_key (str, optional): L1 private key. Defaults to None.
        l2_private_key (str, optional): L2 private key. Defaults to None.
        l2_address (str, optional): L2 address. Defaults to None.
        logger (logging.Logger, optional): Logger. Defaults to None.
        ws_timeout (int, optional): WebSocket read timeout in seconds. Defaults to None (uses default).

    Note:
        - If only L2 private key is provided, the account will be authenticated directly (L2-only mode)
        - For subkeys, L2 address of the main accountmust be provided.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> # L1+L2 authentication (traditional)
        >>> paradex = Paradex(env=Environment.TESTNET, l1_address="0x...", l1_private_key="0x...")
        >>> # L2-only authentication (subkey)
        >>> paradex = Paradex(env=Environment.TESTNET, l2_private_key="0x...", l2_address="0x...")
        >>> # With custom timeout
        >>> paradex = Paradex(env=Environment.TESTNET, l2_private_key="0x...", ws_timeout=30)
    """

    def __init__(
        self,
        env: Environment,
        l1_address: Optional[str] = None,
        l1_private_key: Optional[str] = None,
        l2_private_key: Optional[str] = None,
        l2_address: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        ws_timeout: Optional[int] = None,
    ):
        if env is None:
            return raise_value_error("Paradex: Invalid environment")
        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)
        # Load api client and system config
        self.api_client = ParadexApiClient(env=env, logger=logger)
        self.ws_client = ParadexWebsocketClient(env=env, logger=logger, ws_timeout=ws_timeout)
        self.config = self.api_client.fetch_system_config()
        self.account: Optional[ParadexAccount] = None

        # Initialize account if private key is provided
        if l2_private_key is not None or l1_private_key is not None:
            self.init_account(
                l1_address=l1_address,
                l1_private_key=l1_private_key,
                l2_private_key=l2_private_key,
                l2_address=l2_address,
            )

    def init_account(
        self,
        l1_address: Optional[str] = None,
        l1_private_key: Optional[str] = None,
        l2_private_key: Optional[str] = None,
        l2_address: Optional[str] = None,
    ):
        """Initialize paradex account with l1 or l2 private keys.
        Cannot be called if account is already initialized.

        Args:
            l1_address (str): L1 address
            l1_private_key (str): L1 private key
            l2_private_key (str): L2 private key
        """
        if self.account is not None:
            return raise_value_error("Paradex: Account already initialized")
        self.account = ParadexAccount(
            config=self.config,
            l1_address=l1_address,
            l1_private_key=l1_private_key,
            l2_private_key=l2_private_key,
            l2_address=l2_address,
        )
        self.api_client.init_account(self.account)
        self.ws_client.init_account(self.account)
