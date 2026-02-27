import logging

from paradex_py._client_base import _ClientBase
from paradex_py.account.subkey_account import SubkeyAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.auth_level import AuthLevel
from paradex_py.environment import Environment, _validate_env
from paradex_py.utils import raise_value_error

__all__ = ["ParadexL2"]


class ParadexL2(_ClientBase):
    """L2-key authentication: l2_private_key + explicit l2_address.

    Covers main accounts using only an L2 key, registered subkeys,
    and any account where the signing key differs from the address derivation key.

    Args:
        env (Environment): Environment
        l2_private_key (str): L2 private key (required)
        l2_address (str): L2 address of the account that owns this key.
            For a main-account key, this is the account's own address.
            For a registered subkey (``ParadexSubkey``), this must be the
            *main account* address the subkey is registered under — not
            the subkey's own derived address.
        logger (logging.Logger, optional): Logger. Defaults to None.
        ws_timeout (int, optional): WebSocket read timeout in seconds. Defaults to None (uses default).
        ws_enabled (bool, optional): Whether to create a WebSocket client. Defaults to True.
            Set to False for REST-only use cases to avoid starting background connection machinery.

    Examples:
        >>> from paradex_py import ParadexL2
        >>> from paradex_py.environment import Environment
        >>> paradex = ParadexL2(
        ...     env=Environment.TESTNET,
        ...     l2_private_key="0x...",
        ...     l2_address="0x..."
        ... )
    """

    def __init__(
        self,
        env: Environment,
        l2_private_key: str,
        l2_address: str,
        logger: logging.Logger | None = None,
        ws_timeout: int | None = None,
        ws_enabled: bool = True,
    ):
        _validate_env(env, "ParadexL2")

        if not l2_private_key:
            raise_value_error(f"ParadexL2: L2 private key is required, got {l2_private_key!r}")
        if not l2_address:
            raise_value_error(f"ParadexL2: L2 address is required, got {l2_address!r}")

        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)

        self.api_client = ParadexApiClient(env=env, logger=logger)
        self.ws_client: ParadexWebsocketClient | None = (
            ParadexWebsocketClient(env=env, logger=logger, ws_timeout=ws_timeout, api_client=self.api_client)
            if ws_enabled
            else None
        )
        self.config = self.api_client.fetch_system_config()

        self.account = SubkeyAccount(
            config=self.config,
            l2_private_key=l2_private_key,
            l2_address=l2_address,
        )

        self.api_client.init_account(self.account)
        if self.ws_client is not None:
            self.ws_client.init_account(self.account)

    @property
    def auth_level(self) -> AuthLevel:
        """``AuthLevel.FULL`` — main account L2 key, orders and withdrawals available."""
        return AuthLevel.FULL

    @property
    def is_authenticated(self) -> bool:
        """Always ``True`` — credentials were provided at construction."""
        return True

    @property
    def can_trade(self) -> bool:
        """Always ``True`` — L2 signing key is available."""
        return True

    @property
    def can_withdraw(self) -> bool:
        """Always ``True`` — full account key, all on-chain operations available (deposit, withdraw, transfer)."""
        return True
