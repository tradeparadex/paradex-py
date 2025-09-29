import logging
from typing import TYPE_CHECKING

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import Environment
from paradex_py.utils import raise_value_error

if TYPE_CHECKING:
    from paradex_py.api.http_client import HttpClient
    from paradex_py.api.ws_client import WebSocketConnector


class Paradex:
    """Paradex class to interact with Paradex REST API.

    Args:
        env (Environment): Environment
        l1_address (str, optional): L1 address. Defaults to None.
        l1_private_key (str, optional): L1 private key. Defaults to None.
        l2_private_key (str, optional): L2 private key. Defaults to None.
        logger (logging.Logger, optional): Logger. Defaults to None.
        ws_timeout (int, optional): WebSocket read timeout in seconds. Defaults to None (uses default).
        http_client (HttpClient, optional): Custom HTTP client for injection. Defaults to None.
        api_base_url (str, optional): Custom API base URL override. Defaults to None.
        auto_start_ws_reader (bool, optional): Whether to automatically start WS message reader. Defaults to True.
        ws_connector (WebSocketConnector, optional): Custom WebSocket connector for injection. Defaults to None.
        ws_url_override (str, optional): Custom WebSocket URL override. Defaults to None.
        ws_reader_sleep_on_error (float, optional): WebSocket reader sleep duration after errors. Defaults to 1.0.
        ws_reader_sleep_on_no_connection (float, optional): WebSocket reader sleep when no connection. Defaults to 1.0.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET)
        >>> # With custom timeout
        >>> paradex = Paradex(env=Environment.TESTNET, ws_timeout=30)
        >>> # With simulator-friendly injection (high-frequency, no sleeps)
        >>> paradex = Paradex(env=Environment.TESTNET, auto_start_ws_reader=False,
        ...                   http_client=custom_client, ws_connector=custom_connector,
        ...                   ws_reader_sleep_on_error=0, ws_reader_sleep_on_no_connection=0)
    """

    def __init__(
        self,
        env: Environment,
        l1_address: str | None = None,
        l1_private_key: str | None = None,
        l2_private_key: str | None = None,
        logger: logging.Logger | None = None,
        ws_timeout: int | None = None,
        http_client: "HttpClient | None" = None,
        api_base_url: str | None = None,
        auto_start_ws_reader: bool = True,
        ws_connector: "WebSocketConnector | None" = None,
        ws_url_override: str | None = None,
        ws_reader_sleep_on_error: float = 1.0,
        ws_reader_sleep_on_no_connection: float = 1.0,
    ):
        if env is None:
            return raise_value_error("Paradex: Invalid environment")
        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)

        # Load api client and system config with optional injection
        self.api_client = ParadexApiClient(env=env, logger=logger, http_client=http_client, api_base_url=api_base_url)

        # Initialize WebSocket client with optional injection
        self.ws_client = ParadexWebsocketClient(
            env=env,
            logger=logger,
            ws_timeout=ws_timeout,
            auto_start_reader=auto_start_ws_reader,
            connector=ws_connector,
            ws_url_override=ws_url_override,
            reader_sleep_on_error=ws_reader_sleep_on_error,
            reader_sleep_on_no_connection=ws_reader_sleep_on_no_connection,
        )

        self.config = self.api_client.fetch_system_config()
        self.account: ParadexAccount | None = None

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
        l1_private_key: str | None = None,
        l2_private_key: str | None = None,
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
        )
        self.api_client.init_account(self.account)
        self.ws_client.init_account(self.account)
