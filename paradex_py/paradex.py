import asyncio
import logging
from typing import TYPE_CHECKING

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import Environment
from paradex_py.utils import raise_value_error

if TYPE_CHECKING:
    from paradex_py.api.http_client import HttpClient
    from paradex_py.api.models import SystemConfig
    from paradex_py.api.protocols import (
        AuthProvider,
        RequestHook,
        RetryStrategy,
        Signer,
        WebSocketConnector,
    )


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
        default_timeout (float, optional): Default HTTP request timeout in seconds. Defaults to None.
        retry_strategy (RetryStrategy, optional): Custom retry/backoff strategy. Defaults to None.
        request_hook (RequestHook, optional): Hook for request/response observability. Defaults to None.
        auto_start_ws_reader (bool, optional): Whether to automatically start WS message reader. Defaults to True.
        ws_connector (WebSocketConnector, optional): Custom WebSocket connector for injection. Defaults to None.
        ws_url_override (str, optional): Custom WebSocket URL override. Defaults to None.
        ws_reader_sleep_on_error (float, optional): WebSocket reader sleep duration after errors. Defaults to 1.0.
        ws_reader_sleep_on_no_connection (float, optional): WebSocket reader sleep when no connection. Defaults to 1.0.
        validate_ws_messages (bool, optional): Enable JSON-RPC message validation. Defaults to False.
        ping_interval (float, optional): WebSocket ping interval in seconds. Defaults to None.
        disable_reconnect (bool, optional): Disable automatic WebSocket reconnection. Defaults to False.
        auto_auth (bool, optional): Whether to automatically handle onboarding/auth. Defaults to True.
        auth_provider (AuthProvider, optional): Custom authentication provider. Defaults to None.
        signer (Signer, optional): Custom order signer for submit/modify/batch operations. Defaults to None.
        rpc_version (str, optional): RPC version (e.g., "v0_9"). If provided, constructs URL as {base_url}/rpc/{rpc_version}. Defaults to None.
        config (SystemConfig, optional): System configuration. If provided, uses this config instead of fetching from API. Defaults to None.

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
        # HTTP client injection and configuration
        http_client: "HttpClient | None" = None,
        api_base_url: str | None = None,
        default_timeout: float | None = None,
        retry_strategy: "RetryStrategy | None" = None,
        request_hook: "RequestHook | None" = None,
        # WebSocket client injection and configuration
        auto_start_ws_reader: bool = True,
        ws_connector: "WebSocketConnector | None" = None,
        ws_url_override: str | None = None,
        ws_reader_sleep_on_error: float = 1.0,
        ws_reader_sleep_on_no_connection: float = 1.0,
        validate_ws_messages: bool = False,
        ping_interval: float | None = None,
        disable_reconnect: bool = False,
        # Auth configuration
        auto_auth: bool = True,
        auth_provider: "AuthProvider | None" = None,
        # Signing configuration
        signer: "Signer | None" = None,
        # RPC configuration
        rpc_version: str | None = None,
        config: "SystemConfig | None" = None,
    ):
        if env is None:
            return raise_value_error("Paradex: Invalid environment")
        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)

        # Create enhanced HTTP client if needed
        if http_client is None and (default_timeout or retry_strategy or request_hook):
            from paradex_py.api.http_client import HttpClient

            http_client = HttpClient(
                default_timeout=default_timeout,
                retry_strategy=retry_strategy,
                request_hook=request_hook,
            )

        # Load api client and system config with all optional injection
        self.api_client = ParadexApiClient(
            env=env,
            logger=logger,
            http_client=http_client,
            api_base_url=api_base_url,
            auto_auth=auto_auth,
            auth_provider=auth_provider,
            signer=signer,
        )

        # Initialize WebSocket client with all optional injection
        self.ws_client = ParadexWebsocketClient(
            env=env,
            logger=logger,
            ws_timeout=ws_timeout,
            auto_start_reader=auto_start_ws_reader,
            connector=ws_connector,
            ws_url_override=ws_url_override,
            reader_sleep_on_error=ws_reader_sleep_on_error,
            reader_sleep_on_no_connection=ws_reader_sleep_on_no_connection,
            validate_messages=validate_ws_messages,
            ping_interval=ping_interval,
            disable_reconnect=disable_reconnect,
        )

        if config is not None:
            self.config = config
        else:
            self.config = self.api_client.fetch_system_config()
        self.account: ParadexAccount | None = None

        # Initialize account if private key is provided
        if l1_address and (l2_private_key is not None or l1_private_key is not None):
            self.init_account(
                l1_address=l1_address,
                l1_private_key=l1_private_key,
                l2_private_key=l2_private_key,
                rpc_version=rpc_version,
            )

    def init_account(
        self,
        l1_address: str,
        l1_private_key: str | None = None,
        l2_private_key: str | None = None,
        rpc_version: str | None = None,
    ):
        """Initialize paradex account with l1 or l2 private keys.
        Cannot be called if account is already initialized.

        Args:
            l1_address (str): L1 address
            l1_private_key (str): L1 private key
            l2_private_key (str): L2 private key
            rpc_version (str, optional): RPC version (e.g., "v0_9"). If provided, constructs URL as {base_url}/rpc/{rpc_version}. Defaults to None.
        """
        if self.account is not None:
            return raise_value_error("Paradex: Account already initialized")
        self.account = ParadexAccount(
            config=self.config,
            l1_address=l1_address,
            l1_private_key=l1_private_key,
            l2_private_key=l2_private_key,
            rpc_version=rpc_version,
        )
        self.api_client.init_account(self.account)
        self.ws_client.init_account(self.account)

    async def close(self):
        """Close all connections and clean up resources.

        This method should be called when done using the Paradex instance
        to properly clean up websocket connections and background tasks.

        Examples:
            >>> import asyncio
            >>> from paradex_py import Paradex
            >>> from paradex_py.environment import Environment
            >>> async def main():
            ...     paradex = Paradex(env=Environment.TESTNET)
            ...     try:
            ...         # Use paradex instance
            ...         pass
            ...     finally:
            ...         await paradex.close()
            >>> asyncio.run(main())
        """
        if self.ws_client:
            await self.ws_client.close()

        if self.api_client and hasattr(self.api_client, "client"):
            self.api_client.client.close()

    def __del__(self):
        """Cleanup when Paradex instance is destroyed.

        Attempts to cancel websocket reader task if event loop is still running.
        """
        if (
            hasattr(self, "ws_client")
            and self.ws_client
            and hasattr(self.ws_client, "_reader_task")
            and self.ws_client._reader_task
        ):
            # Try to cancel the reader task if it exists and event loop is running
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running() and not self.ws_client._reader_task.done():
                    self.ws_client._reader_task.cancel()
            except (RuntimeError, AttributeError):
                # Event loop not available or already closed, ignore
                pass
