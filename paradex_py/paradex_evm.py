import logging

from paradex_py._client_base import _ClientBase
from paradex_py.account.evm_account import EvmAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.auth_level import AuthLevel
from paradex_py.environment import Environment, _validate_env
from paradex_py.utils import raise_value_error

__all__ = ["ParadexEvm"]


class ParadexEvm(_ClientBase):
    """Paradex client authenticated via EVM (Ethereum) key using SIWE (ERC-4361).

    The Starknet address is derived deterministically from the EVM address.
    This client provides ``AuthLevel.AUTHENTICATED`` — it can call all
    authenticated REST endpoints but cannot sign orders directly (no Starknet
    signing key). For trading, register a subkey with :meth:`api_client.create_subkey`
    and use :class:`~paradex_py.ParadexSubkey`.

    Args:
        env (Environment): Environment
        evm_address (str): Ethereum address (checksummed or lowercase hex).
        evm_private_key (str): Ethereum private key (hex string with 0x prefix).
        logger (logging.Logger, optional): Logger. Defaults to None.
        ws_timeout (int, optional): WebSocket read timeout in seconds. Defaults to None.
        ws_enabled (bool, optional): Whether to create a WebSocket client. Defaults to True.
            Set to False for REST-only use cases.
        ws_sbe_enabled (bool, optional): Enable SBE encoding on WebSocket. Defaults to False.

    Examples:
        >>> from paradex_py import ParadexEvm
        >>> from paradex_py.environment import Environment
        >>> paradex = ParadexEvm(
        ...     env=Environment.TESTNET,
        ...     evm_address="0x...",
        ...     evm_private_key="0x...",
        ... )
        >>> paradex.api_client.fetch_balances()
        >>> # List and create subkeys
        >>> paradex.api_client.fetch_subkeys()
        >>> paradex.api_client.create_subkey({
        ...     "name": "trading-bot",
        ...     "public_key": "0x...",
        ...     "state": "active",
        ... })
    """

    def __init__(
        self,
        env: Environment,
        evm_address: str,
        evm_private_key: str,
        logger: logging.Logger | None = None,
        ws_timeout: int | None = None,
        ws_enabled: bool = True,
        ws_sbe_enabled: bool = False,
    ):
        _validate_env(env, "ParadexEvm")

        if not evm_address:
            raise_value_error(f"ParadexEvm: EVM address is required, got {evm_address!r}")
        if not evm_private_key:
            raise_value_error("ParadexEvm: EVM private key is required")

        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)

        self.api_client = ParadexApiClient(env=env, logger=logger)
        self.ws_client: ParadexWebsocketClient | None = (
            ParadexWebsocketClient(
                env=env,
                logger=logger,
                ws_timeout=ws_timeout,
                api_client=self.api_client,
                sbe_enabled=ws_sbe_enabled,
            )
            if ws_enabled
            else None
        )
        self.config = self.api_client.fetch_system_config()

        self.account = EvmAccount(
            config=self.config,
            env=env,
            evm_address=evm_address,
            evm_private_key=evm_private_key,
        )

        self.api_client.init_account_evm(self.account)

    @property
    def auth_level(self) -> AuthLevel:
        """``AuthLevel.AUTHENTICATED`` — JWT present, no Starknet signing key."""
        return AuthLevel.AUTHENTICATED

    @property
    def is_authenticated(self) -> bool:
        """Always ``True`` — credentials were provided at construction."""
        return True

    @property
    def can_trade(self) -> bool:
        """Always ``False`` — no Starknet L2 signing key; use a registered subkey."""
        return False

    @property
    def can_withdraw(self) -> bool:
        """Always ``False`` — no Starknet L2 signing key."""
        return False
