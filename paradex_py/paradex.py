import logging
from typing import TYPE_CHECKING

from paradex_py._client_base import _ClientBase
from paradex_py.account.account import ParadexAccount
from paradex_py.account.utils import derive_l2_address_starknet, resolve_l2_keypair
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.protocols import DefaultRetryStrategy
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.auth_level import AuthLevel
from paradex_py.environment import Environment, _validate_env
from paradex_py.utils import raise_value_error

__all__ = ["Paradex"]

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

_UNSET: "RetryStrategy | None" = object()  # type: ignore[assignment]


class Paradex(_ClientBase):
    """Paradex class to interact with Paradex REST API.

    Args:
        env (Environment): Environment
        l1_address (str, optional): L1 address. Defaults to None.
        l1_private_key (str, optional): L1 private key. Defaults to None.
        l1_private_key_from_ledger (bool, optional): Derive L2 key from Ledger hardware wallet. Defaults to False.
        l2_private_key (str, optional): L2 private key. Defaults to None.
        logger (logging.Logger, optional): Logger. Defaults to None.
        ws_timeout (int, optional): WebSocket read timeout in seconds. Defaults to None (uses default).
        http_client (HttpClient, optional): Custom HTTP client for injection. Defaults to None.
        api_base_url (str, optional): Custom API base URL override. Defaults to None.
        default_timeout (float, optional): Default HTTP request timeout in seconds. Defaults to None.
        retry_strategy (RetryStrategy, optional): Custom retry/backoff strategy.
            Defaults to DefaultRetryStrategy (rate-limit-aware retries). Pass None to disable retries.
        request_hook (RequestHook, optional): Hook for request/response observability. Defaults to None.
        enable_http_compression (bool, optional): Enable HTTP compression (gzip, deflate, br). Defaults to True.
        auto_start_ws_reader (bool, optional): Whether to automatically start WS message reader. Defaults to True.
        ws_connector (WebSocketConnector, optional): Custom WebSocket connector for injection. Defaults to None.
        ws_url_override (str, optional): Custom public WebSocket URL override. Defaults to None.
        ws_direct_url_override (str, optional): Custom direct (authenticated) WebSocket URL override. Defaults to None.
        ws_reader_sleep_on_error (float, optional): WebSocket reader sleep duration after errors. Defaults to 1.0.
        ws_reader_sleep_on_no_connection (float, optional): WebSocket reader sleep when no connection. Defaults to 1.0.
        validate_ws_messages (bool, optional): Enable JSON-RPC message validation. Defaults to False.
        ping_interval (float, optional): WebSocket ping interval in seconds. Defaults to None.
        disable_reconnect (bool, optional): Disable automatic WebSocket reconnection. Defaults to False.
        enable_ws_compression (bool, optional): Enable WebSocket per-message compression (RFC 7692). Defaults to True.
        ws_sbe_enabled (bool, optional): Enable SBE binary encoding on the WebSocket connection. Defaults to False.
        auto_auth (bool, optional): Whether to automatically handle onboarding/auth. Defaults to True.
        auth_provider (AuthProvider, optional): Custom authentication provider. Defaults to None.
        auth_params (dict, optional): Extra query parameters sent with every ``/auth`` request
            (initial and refresh). For example, ``{"token_usage": "interactive"}`` for 0-fee JWT. Defaults to None.
        signer (Signer, optional): Custom order signer for submit/modify/batch operations. Defaults to None.
        rpc_version (str, optional): RPC version (e.g., "v0_9"). If provided, constructs URL as {base_url}/rpc/{rpc_version}. Defaults to None.
        config (SystemConfig, optional): System configuration. If provided, uses this config instead of fetching from API. Defaults to None.
        server_derive_address (bool, optional): When True, fetch the L2 address from ``GET /onboarding`` instead of
            computing it locally from class hashes. Also caches the ``exists`` flag so ``POST /onboarding`` is skipped
            when the account is already onboarded. Defaults to False (local ``compute_address`` path unchanged).

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
        l1_private_key_from_ledger: bool = False,
        l2_private_key: str | None = None,
        logger: logging.Logger | None = None,
        ws_timeout: int | None = None,
        # HTTP client injection and configuration
        http_client: "HttpClient | None" = None,
        api_base_url: str | None = None,
        default_timeout: float | None = None,
        retry_strategy: "RetryStrategy | None" = _UNSET,
        request_hook: "RequestHook | None" = None,
        enable_http_compression: bool = True,
        # WebSocket client injection and configuration
        auto_start_ws_reader: bool = True,
        ws_connector: "WebSocketConnector | None" = None,
        ws_url_override: str | None = None,
        ws_direct_url_override: str | None = None,
        ws_reader_sleep_on_error: float = 1.0,
        ws_reader_sleep_on_no_connection: float = 1.0,
        validate_ws_messages: bool = False,
        ping_interval: float | None = None,
        disable_reconnect: bool = False,
        enable_ws_compression: bool = True,
        ws_sbe_enabled: bool = False,
        # Auth configuration
        auto_auth: bool = True,
        auth_provider: "AuthProvider | None" = None,
        auth_params: dict | None = None,
        # Signing configuration
        signer: "Signer | None" = None,
        # RPC configuration
        rpc_version: str | None = None,
        config: "SystemConfig | None" = None,
        # Onboarding configuration
        server_derive_address: bool = False,
    ):
        _validate_env(env, "Paradex")
        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)
        self.server_derive_address = server_derive_address

        # Create enhanced HTTP client if needed (retry_strategy is handled by ParadexApiClient directly)
        if http_client is None and (default_timeout or request_hook or not enable_http_compression):
            from paradex_py.api.http_client import HttpClient

            http_client = HttpClient(
                default_timeout=default_timeout,
                request_hook=request_hook,
                enable_compression=enable_http_compression,
            )

        effective_retry = DefaultRetryStrategy() if retry_strategy is _UNSET else retry_strategy

        # Load api client and system config with all optional injection
        self.api_client = ParadexApiClient(
            env=env,
            logger=logger,
            http_client=http_client,
            api_base_url=api_base_url,
            auto_auth=auto_auth,
            auth_provider=auth_provider,
            auth_params=auth_params,
            signer=signer,
            retry_strategy=effective_retry,
        )

        # Public endpoint (default): ws-public.api.{env}.paradex.trade
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
            enable_compression=enable_ws_compression,
            api_client=self.api_client,
        )
        # Direct endpoint (opt-in): ws.api.{env}.paradex.trade
        self.ws_direct_client = ParadexWebsocketClient(
            env=env,
            logger=logger,
            ws_timeout=ws_timeout,
            auto_start_reader=auto_start_ws_reader,
            connector=ws_connector,
            ws_url_override=ws_direct_url_override,
            reader_sleep_on_error=ws_reader_sleep_on_error,
            reader_sleep_on_no_connection=ws_reader_sleep_on_no_connection,
            validate_messages=validate_ws_messages,
            ping_interval=ping_interval,
            disable_reconnect=disable_reconnect,
            enable_compression=enable_ws_compression,
            api_client=self.api_client,
            sbe_enabled=ws_sbe_enabled,
            direct=True,
        )

        if config is not None:
            self.config = config
        else:
            self.config = self.api_client.fetch_system_config()
        self.account: ParadexAccount | None = None

        # Initialize account if private key is provided
        if l1_address and (l2_private_key is not None or l1_private_key is not None or l1_private_key_from_ledger):
            self.init_account(
                l1_address=l1_address,
                l1_private_key=l1_private_key,
                l1_private_key_from_ledger=l1_private_key_from_ledger,
                l2_private_key=l2_private_key,
                rpc_version=rpc_version,
            )

    def init_account(
        self,
        l1_address: str,
        l1_private_key: str | None = None,
        l1_private_key_from_ledger: bool = False,
        l2_private_key: str | None = None,
        rpc_version: str | None = None,
    ):
        """Initialize paradex account with l1 or l2 private keys.
        Cannot be called if account is already initialized.

        Args:
            l1_address (str): L1 address
            l1_private_key (str): L1 private key
            l1_private_key_from_ledger (bool, optional): Derive L2 key from Ledger hardware wallet. Defaults to False.
            l2_private_key (str): L2 private key
            rpc_version (str, optional): RPC version (e.g., "v0_9"). If provided, constructs URL as {base_url}/rpc/{rpc_version}. Defaults to None.
        """
        if self.account is not None:
            raise_value_error("Paradex: Account already initialized")

        # Resolve the L2 keypair once, up-front. This avoids double-triggering the EIP-712
        # stark-key signature (or worse: a second Ledger prompt) when the account
        # constructor would otherwise re-resolve from the same credentials.
        key_pair = resolve_l2_keypair(
            config=self.config,
            l1_address=l1_address,
            l1_private_key=l1_private_key,
            l1_private_key_from_ledger=l1_private_key_from_ledger,
            l2_private_key=l2_private_key,
        )

        # Derive the L2 address outside the account constructor — either from the server
        # (GET /onboarding) or from the shared local helper. Both paths converge to a
        # single downstream ParadexAccount(...) call with a pre-resolved address.
        # getattr fallback protects callers that bypass __init__ via Paradex.__new__(...).
        is_onboarded: bool | None = None
        if getattr(self, "server_derive_address", False):
            info = self.api_client.fetch_onboarding(
                {
                    "account_signer_type": "starknet",
                    "public_key": hex(key_pair.public_key),
                }
            )
            l2_address_hex: str = info["address"]
            exists = info.get("exists")
            is_onboarded = bool(exists) if exists is not None else None
        else:
            l2_address_hex = hex(derive_l2_address_starknet(self.config, key_pair.public_key))

        self.account = ParadexAccount(
            config=self.config,
            l1_address=l1_address,
            l2_private_key=hex(key_pair.private_key),
            l2_address=l2_address_hex,
            is_onboarded=is_onboarded,
            rpc_version=rpc_version,
        )
        self.api_client.init_account(self.account)
        if self.ws_client is not None:
            self.ws_client.init_account(self.account)

    @property
    def auth_level(self) -> AuthLevel:
        """Reflects the current authentication state.

        Returns ``AuthLevel.FULL`` when an account is initialized, ``AuthLevel.AUTHENTICATED``
        when only an ``auth_provider`` is set (token present, no signing key), or
        ``AuthLevel.UNAUTHENTICATED`` when neither is available.

        ``Paradex`` can be constructed without keys and initialized later via
        ``init_account()``, so this property reflects the current state.
        """
        if self.account is not None:
            return AuthLevel.FULL
        if self.api_client.auth_provider is not None:
            return AuthLevel.AUTHENTICATED
        return AuthLevel.UNAUTHENTICATED

    @property
    def is_authenticated(self) -> bool:
        """``True`` when an account is initialized or an ``auth_provider`` is set."""
        return self.account is not None or self.api_client.auth_provider is not None

    @property
    def can_trade(self) -> bool:
        """``True`` when account is initialized — L2 key is available for signing."""
        return self.account is not None

    @property
    def can_withdraw(self) -> bool:
        """``True`` when account is initialized — full account key, all on-chain operations
        available (deposit, withdraw, transfer)."""
        return self.account is not None

    @property
    def is_onboarded(self) -> bool | None:
        """Cached onboarding state from ``GET /onboarding``.

        Returns ``True`` / ``False`` when ``server_derive_address=True`` populated the cache at
        account initialization, ``None`` otherwise (local derivation path — the SDK learns
        onboarding status lazily via the ``NOT_ONBOARDED`` auth-retry flow)."""
        return self.account.is_onboarded if self.account is not None else None
